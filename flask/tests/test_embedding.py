import unittest
from unittest import mock

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


if __name__ == '__main__':
    unittest.main()
