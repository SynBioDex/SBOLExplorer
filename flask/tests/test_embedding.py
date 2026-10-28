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


class EmbedOrderTests(unittest.TestCase):
    def test_vectors_come_back_in_input_order_although_embedded_by_length(self):
        fake_model = mock.Mock()
        fake_model.embed.side_effect = lambda texts, batch_size: [np.full(2, len(t), dtype=np.float32) for t in texts]
        with mock.patch('embedding.model', return_value=fake_model):
            out = embedding.embed(['ccc', 'a', 'bb'])
        self.assertEqual(fake_model.embed.call_args.args[0], ['a', 'bb', 'ccc'])   # sorted by length
        self.assertEqual([int(v[0]) for v in out], [3, 1, 2])                        # original order


class IncrementalEmbeddingTests(unittest.TestCase):
    PARTS = [
        {'subject': 'https://synbiohub.org/user/alice/c/p1/1', 'displayId': 'p1', 'name': 'red fluorescent reporter',
         'type': 'http://sbols.org/v2#ComponentDefinition', 'role': 'http://identifiers.org/so/SO:0000167',
         'graph': 'https://synbiohub.org/user/alice'},
        {'subject': 'https://synbiohub.org/user/alice/c/p1_sequence/1', 'displayId': 'p1_sequence',
         'type': 'http://sbols.org/v2#Sequence', 'graph': 'https://synbiohub.org/user/alice'},
    ]

    def run_update(self, enabled, embed_side_effect=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        class TempCache(embedding.EmbeddingCache):
            def __init__(self):
                super().__init__(os.path.join(tmp.name, 'e.sqlite'))

        fake_embed = mock.Mock(side_effect=embed_side_effect or
                               (lambda texts: [np.ones(embedding.DIMENSIONS, dtype=np.float32) for _ in texts]))
        with mock.patch('index.vector_search_enabled', return_value=enabled), \
                mock.patch('index.embedding.EmbeddingCache', TempCache), \
                mock.patch('index.embedding.embed', fake_embed), \
                mock.patch('index.index_part') as index_part, \
                mock.patch('index.load_term_list', return_value=[]), \
                mock.patch('index.query.query_values_for_subjects', return_value={}), \
                mock.patch('index.schedule_facet_refresh'):
            index.incremental_update({'partsToAdd': [dict(p) for p in self.PARTS]}, {})
        indexed = {call.args[0]['displayId']: call.args[0] for call in index_part.call_args_list}
        return indexed, fake_embed

    def test_new_part_is_embedded_and_sequence_is_not(self):
        indexed, embed = self.run_update(enabled=True)
        self.assertEqual(len(indexed['p1'][embedding.FIELD]), embedding.DIMENSIONS)
        self.assertNotIn(embedding.FIELD, indexed['p1_sequence'])
        self.assertIn('red fluorescent reporter', embed.call_args.args[0][0])
        self.assertIn('promoter', embed.call_args.args[0][0])   # role label from the payload role

    def test_nothing_is_embedded_when_vector_search_is_off(self):
        indexed, embed = self.run_update(enabled=False)
        embed.assert_not_called()
        self.assertNotIn(embedding.FIELD, indexed['p1'])

    def test_model_failure_still_indexes_the_part(self):
        indexed, _ = self.run_update(enabled=True, embed_side_effect=RuntimeError('model missing'))
        self.assertEqual(set(indexed), {'p1', 'p1_sequence'})
        self.assertNotIn(embedding.FIELD, indexed['p1'])


if __name__ == '__main__':
    unittest.main()
