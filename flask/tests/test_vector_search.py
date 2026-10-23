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

    def test_selected_facets_narrow_the_knn_filter(self):
        with mock.patch('vector_search.embedding.embed', return_value=[np.ones(embedding.DIMENSIONS, dtype=np.float32)]), \
                mock.patch.object(vector_search.config_manager, 'load_config', return_value={'elasticsearch_index_name': 'part'}), \
                mock.patch.object(vector_search.elasticsearch_manager, 'get_es') as get_es:
            vector_search.vector_search_es('rbs', [], 5, {'role': ['SO:1'], 'type': []})
        self.assertEqual(get_es.return_value.search.call_args.kwargs['body']['knn']['filter'], {'bool': {'filter': [
            {'bool': {'must_not': {'wildcard': {'graph': '*/user/*'}}}},
            {'terms': {'facet_role': ['SO:1']}},
        ]}})

    def test_filter_is_the_callers_graphs_and_public_only_without_them(self):
        self.assertEqual(self.search([], 5)['knn']['filter'], {'bool': {'must_not': {'wildcard': {'graph': '*/user/*'}}}})
        self.assertEqual(self.search(['https://synbiohub.org/user/alice'], 5)['knn']['filter'],
                         {'terms': {'graph': ['https://synbiohub.org/user/alice']}})


class VectorSearchFacetTests(unittest.TestCase):
    def hit(self, **fields):
        return {'_source': fields}

    def count(self, hits, facet_by):
        with mock.patch.object(vector_search.config_manager, 'load_config', return_value={'elasticsearch_index_name': 'part'}), \
                mock.patch.object(vector_search.elasticsearch_manager, 'get_es') as get_es, \
                mock.patch('vector_search.facets.visible_collections', side_effect=lambda es, index, values, visible: values):
            get_es.return_value.search.return_value = {'hits': {'hits': []}}
            return vector_search.facets_for_hits(hits, facet_by, [])

    def test_counts_each_value_over_the_hits_most_frequent_first(self):
        hits = [
            self.hit(facet_type=['https://x/ComponentDefinition']),
            self.hit(facet_type=['https://x/ComponentDefinition', 'https://x/Collection']),
            self.hit(facet_type=['https://x/ComponentDefinition']),
        ]
        result = self.count(hits, ['type'])
        self.assertEqual(result['type'], [
            {'value': 'https://x/ComponentDefinition', 'label': 'ComponentDefinition', 'count': 3},
            {'value': 'https://x/Collection', 'label': 'Collection', 'count': 1},
        ])

    def test_missing_field_counts_nothing(self):
        self.assertEqual(self.count([self.hit(name='rbs')], ['role'])['role'], [])

    def test_role_gets_its_so_label(self):
        hits = [self.hit(facet_role=['http://identifiers.org/so/SO:0000139'])]
        self.assertEqual(self.count(hits, ['role'])['role'][0]['label'], 'ribosome_entry_site')


if __name__ == '__main__':
    unittest.main()
