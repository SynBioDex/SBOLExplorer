# Text embeddings for vector (kNN) search.
#
# all-MiniLM-L6-v2 through fastembed (ONNX Runtime, no PyTorch): 384
# dimensions, ~90 MB model, ~200 MB of RAM while embedding. Measured locally
# on real parts it was 3-4x faster than bge-small-en-v1.5 at similar quality.
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
