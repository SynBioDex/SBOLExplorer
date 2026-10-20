import os
import tempfile
import unittest
from unittest import mock

import numpy as np

import embedding
import index


class EmbeddingMappingTests(unittest.TestCase):
    @mock.patch('index.elasticsearch_manager')
    def test_new_index_maps_the_embedding_field(self, manager):
        es = manager.get_es.return_value
        es.indices.exists.return_value = False

        index.create_parts_index('part')

        properties = es.indices.create.call_args.kwargs['body']['mappings']['properties']
        self.assertEqual(properties[embedding.FIELD], embedding.MAPPING)
        self.assertEqual(properties[embedding.FIELD]['dims'], embedding.DIMENSIONS)

    def test_mapping_matches_the_model(self):
        # all-MiniLM-L6-v2 produces 384-dimensional vectors; a mismatch would
        # make Elasticsearch reject every document with an embedding.
        self.assertEqual(embedding.DIMENSIONS, 384)
        self.assertEqual(embedding.MAPPING['similarity'], 'cosine')


class PartTextTests(unittest.TestCase):
    def test_text_combines_fields_and_role_labels(self):
        source = {'displayId': 'BBa_B0034', 'name': 'RBS (Elowitz 1999)', 'description': 'strong RBS',
                  'facet_role': ['http://identifiers.org/so/SO:0000139']}
        text = embedding.part_text(source)
        self.assertTrue(text.startswith('BBa_B0034 RBS (Elowitz 1999) strong RBS'))
        self.assertIn('ribosome_entry_site', text)  # SO:0000139 label from so-simplified.json

    def test_name_equal_to_display_id_is_not_repeated(self):
        self.assertEqual(embedding.part_text({'displayId': 'p1', 'name': 'p1'}), 'p1')


class EmbeddingCacheTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = embedding.EmbeddingCache(os.path.join(tmp, 'e.sqlite'))
            vec = np.arange(embedding.DIMENSIONS, dtype=np.float32)
            cache.put_many([('k1', vec)])
            got = cache.get_many(['k1', 'missing'])
            cache.close()
        self.assertEqual(list(got), ['k1'])
        np.testing.assert_array_equal(got['k1'], vec)


class IndexEmbeddingsTests(unittest.TestCase):
    def run_pass(self, hits, cache_path):
        sent = []

        def streaming_bulk(es, actions, raise_on_error):
            for action in actions:
                sent.append(action)
                yield True, {'update': {}}

        class TempCache(embedding.EmbeddingCache):
            def __init__(self):
                super().__init__(cache_path)

        fake_embed = mock.Mock(side_effect=lambda texts: [np.full(embedding.DIMENSIONS, len(t), dtype=np.float32) for t in texts])
        with mock.patch('index.embedding.EmbeddingCache', TempCache), \
                mock.patch('index.embedding.embed', fake_embed), \
                mock.patch('index.helpers.scan', return_value=iter(hits)) as scan, \
                mock.patch('index.helpers.streaming_bulk', side_effect=streaming_bulk):
            index.index_embeddings(mock.Mock(), 'part')
        return sent, fake_embed, scan

    def test_second_build_reuses_cached_vectors(self):
        hits = [{'_id': 'a', '_source': {'displayId': 'a', 'description': 'red fluorescent protein'}},
                {'_id': 'b', '_source': {'displayId': 'a', 'description': 'red fluorescent protein'}},  # same text
                {'_id': 'c', '_source': {}}]                                                           # no text
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'e.sqlite')
            sent, embed, scan = self.run_pass(hits, path)
            self.assertEqual(sorted(a['_id'] for a in sent), ['a', 'b'])     # 'c' has no text: no vector
            self.assertEqual(embed.call_count, 1)
            self.assertEqual(len(embed.call_args.args[0]), 1)                # identical text embedded once
            query = scan.call_args.kwargs['query']['query']['bool']['must_not']
            self.assertEqual(query, {'terms': {'facet_type': embedding.SKIPPED_TYPES}})

            sent2, embed2, _ = self.run_pass(hits, path)
            embed2.assert_not_called()                                       # all from cache
            self.assertEqual([a['doc'] for a in sent2], [a['doc'] for a in sent])


if __name__ == '__main__':
    unittest.main()
