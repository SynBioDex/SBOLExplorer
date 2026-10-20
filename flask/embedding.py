# Text embeddings for vector (kNN) search.
#
# all-MiniLM-L6-v2 through fastembed (ONNX Runtime, no PyTorch): 384
# dimensions, ~90 MB model, ~200 MB of RAM while embedding. Measured locally
# on real parts it was 3-4x faster than bge-small-en-v1.5 at similar quality.
import hashlib
import sqlite3
from functools import lru_cache

import numpy as np

import facets

MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
DIMENSIONS = 384

# The dense_vector field each indexed part's embedding is stored in.
FIELD = 'embedding'

MAPPING = {
    'type': 'dense_vector',
    'dims': DIMENSIONS,
    'index': True,
    'similarity': 'cosine',
    # Better Binary Quantization: the HNSW graph searches 1-bit vectors (~32x
    # smaller than float32) and rescores the best candidates with the full
    # vectors kept on disk, so ~1M parts need little Elasticsearch memory.
    'index_options': {'type': 'bbq_hnsw'},
}

# Parts of these types get no embedding: a Sequence's only text is its
# displayId, so its vector would carry no meaning.
SKIPPED_TYPES = ['http://sbols.org/v2#Sequence']

# The document fields part_text() reads.
SOURCE_FIELDS = ['displayId', 'name', 'description', 'facet_role']

# Model files (~90 MB) are downloaded on first use into the persisted dumps/
# volume, so a container restart does not download them again.
MODEL_CACHE_DIR = 'dumps/models'
CACHE_PATH = 'dumps/embeddings.sqlite'

# Parts read from the index per round. Each round is sorted by text length
# before embedding (see embed), so a larger round gives more even batches.
BATCH_SIZE = 2048

# Texts per model call. The tokenizer pads every text in a call to the
# longest one, so short and long texts are kept apart (see embed); with
# similar lengths, 32 was faster than 64 and used ~10x less extra memory.
MODEL_BATCH_SIZE = 32


def part_text(source):
    """
    The text a part is embedded from: displayId, name (if different),
    description and the readable SO role names (e.g. 'promoter').
    """
    display_id = source.get('displayId') or ''
    name = source.get('name') or ''
    pieces = [display_id]
    if name and name != display_id:
        pieces.append(name)
    if source.get('description'):
        pieces.append(source['description'])
    roles = sorted({facets.role_label(r) for r in source.get('facet_role') or []})
    if roles:
        pieces.append(' '.join(roles))
    return ' '.join(p for p in pieces if p).strip()


@lru_cache(maxsize=1)
def model():
    # Imported here so the rest of Explorer (and its tests) do not load
    # ONNX Runtime unless vector search is used.
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL_NAME, cache_dir=MODEL_CACHE_DIR)


def embed(texts):
    """
    Embeds documents; returns float32 numpy vectors in the order given.

    Part texts are short (median ~22 tokens) but a few are long (up to ~210),
    and each model call pads all its texts to the longest. Embedding in order
    of length keeps batches even: locally ~1.6x faster and far less memory
    than the scan order, with identical vectors (padding is masked out).
    """
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    vectors = list(model().embed([texts[i] for i in order], batch_size=MODEL_BATCH_SIZE))
    result = [None] * len(texts)
    for position, i in enumerate(order):
        result[i] = vectors[position]
    return result


class EmbeddingCache:
    """
    Vectors on disk (SQLite), keyed by a hash of model + text, so a full
    rebuild only embeds parts whose text changed. ~1.5 KB per part.
    """

    def __init__(self, path=CACHE_PATH):
        # A full rebuild and an incremental update can use the cache at the
        # same time; wait for the other's write instead of failing.
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.execute('CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector BLOB)')

    @staticmethod
    def key(text):
        return hashlib.sha1(f'{MODEL_NAME}\n{text}'.encode('utf-8')).hexdigest()

    def get_many(self, keys):
        found = {}
        keys = list(keys)
        for start in range(0, len(keys), 500):  # stay below SQLite's variable limit
            chunk = keys[start:start + 500]
            rows = self.conn.execute(
                f'SELECT key, vector FROM embeddings WHERE key IN ({",".join("?" * len(chunk))})', chunk)
            for key, blob in rows:
                found[key] = np.frombuffer(blob, dtype=np.float32)
        return found

    def put_many(self, items):
        self.conn.executemany('INSERT OR REPLACE INTO embeddings VALUES (?, ?)',
                              [(key, np.asarray(vector, dtype=np.float32).tobytes()) for key, vector in items])
        self.conn.commit()

    def close(self):
        self.conn.close()


def vectors_for_texts(texts, cache, stats=None):
    """
    {id: text} -> {id: vector} for the ids with non-empty text. Cached vectors
    are reused; the rest are embedded once per distinct text and cached.
    stats, if given, counts 'cached', 'computed' and 'no_text'.
    """
    keys = {i: EmbeddingCache.key(text) for i, text in texts.items() if text}
    found = cache.get_many(set(keys.values()))
    missing = sorted({key for key in keys.values() if key not in found})
    if missing:
        text_by_key = {keys[i]: texts[i] for i in keys}
        computed = embed([text_by_key[key] for key in missing])
        cache.put_many(zip(missing, computed))
        found.update(zip(missing, computed))
    if stats is not None:
        stats['no_text'] += len(texts) - len(keys)
        stats['computed'] += len(missing)
        stats['cached'] += len(keys) - len(missing)
    return {i: found[key] for i, key in keys.items()}
