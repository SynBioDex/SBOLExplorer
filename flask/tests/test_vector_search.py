import unittest
from unittest import mock

import numpy as np

import embedding
import vector_search


class VectorSearchQueryTests(unittest.TestCase):
    def search(self, graphs, size):
        with mock.patch('vector_search.embedding.embed', return_value=[np.ones(embedding.DIMENSIONS, dtype=np.float32)]), \
                mock.patch.object(vector_search.config_manager, 'load_config', return_value={'elasticsearch_index_name': 'part'}), \
                mock.patch.object(vector_search.elasticsearch_manager, 'get_es') as get_es:
            vector_search.vector_search_es('rbs', graphs, size)
        return get_es.return_value.search.call_args.kwargs['body']

    def test_knn_on_the_embedding_field_with_the_query_vector(self):
        body = self.search([], 10)
        self.assertEqual(body['knn']['field'], embedding.FIELD)
        self.assertEqual(len(body['knn']['query_vector']), embedding.DIMENSIONS)
        self.assertEqual(body['knn']['k'], 10)
        self.assertEqual(body['size'], 10)
        self.assertGreaterEqual(body['knn']['num_candidates'], body['knn']['k'])

    def test_filter_is_the_callers_graphs_and_public_only_without_them(self):
        self.assertEqual(self.search([], 5)['knn']['filter'], {'bool': {'must_not': {'wildcard': {'graph': '*/user/*'}}}})
        self.assertEqual(self.search(['https://synbiohub.org/user/alice'], 5)['knn']['filter'],
                         {'terms': {'graph': ['https://synbiohub.org/user/alice']}})


if __name__ == '__main__':
    unittest.main()
