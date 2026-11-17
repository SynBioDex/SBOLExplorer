import unittest
from unittest import mock

import graphrag

SEED = 'https://synbiohub.org/public/igem/BBa_E0040/1'
PROMOTER = 'http://identifiers.org/so/SO:0000167'


def seed(uri=SEED):
    return {'uri': uri, 'displayId': uri.split('/')[-2], 'name': 'GFP', 'description': 'green',
            'type': graphrag.SBOL2 + 'ComponentDefinition', 'graph': 'https://synbiohub.org/public', 'rank': 1, 'matched_by': ['text']}


class GraphClauseTests(unittest.TestCase):
    def test_no_graphs_means_public_only(self):
        self.assertIn('!CONTAINS(STR(?g), "/user/")', graphrag.graph_clause([]))

    def test_given_graphs_are_the_only_ones_queried(self):
        clause = graphrag.graph_clause(['https://a/public', 'https://a/user/me'])
        self.assertEqual(clause, 'VALUES ?g { <https://a/public> <https://a/user/me> }')


class RetrieveTests(unittest.TestCase):
    def run_retrieve(self, graph, **kwargs):
        """graph: {(uri, relation): [neighbour uris]}"""
        def neighbours(uri, relation, graphs):
            return [{'uri': n, 'title': n.split('/')[-2]} for n in graph.get((uri, relation), [])]

        with mock.patch('graphrag.find_seeds', return_value=[seed()]), \
                mock.patch('graphrag.neighbours', side_effect=neighbours), \
                mock.patch('graphrag.node_details', return_value={}):
            return graphrag.retrieve('gfp', **kwargs)

    def test_hub_neighbours_are_pruned_by_pagerank(self):
        parents = [f'https://x/p{i}/1' for i in range(30)]
        uri2rank = {p: i for i, p in enumerate(parents)}
        result = self.run_retrieve({(SEED, 'subpart_of'): parents}, max_neighbors=3, uri2rank=uri2rank)

        kept = [t['object'] for t in result['triples'] if t['predicate'] == 'subpart_of']
        self.assertEqual(kept, parents[-1:-4:-1])
        self.assertEqual(result['truncated'], [{'uri': SEED, 'relation': 'subpart_of', 'kept': 3, 'found': 30}])
        self.assertIn('subpart_of (top 3 of 30 by pagerank)', result['context'])

    def test_ontology_terms_are_labelled_and_not_walked(self):
        result = self.run_retrieve({(SEED, 'role'): [PROMOTER]}, hops=2)
        role = [t for t in result['triples'] if t['predicate'] == 'role']
        self.assertEqual(role[0]['object_label'], 'promoter')
        self.assertNotIn(PROMOTER, [n['uri'] for n in result['nodes']])

    def test_second_hop_walks_parts_and_respects_max_nodes(self):
        child, grandchild = 'https://x/child/1', 'https://x/grandchild/1'
        graph = {(SEED, 'has_subpart'): [child], (child, 'has_subpart'): [grandchild]}

        one_hop = self.run_retrieve(graph, hops=1)
        self.assertNotIn(grandchild, [t['object'] for t in one_hop['triples']])

        two_hops = self.run_retrieve(graph, hops=2)
        self.assertIn({'subject': child, 'predicate': 'has_subpart', 'object': grandchild,
                       'object_label': 'grandchild'}, two_hops['triples'])

        capped = self.run_retrieve(graph, hops=2, max_nodes=1)
        self.assertEqual([n['uri'] for n in capped['nodes']], [SEED])


def hit(uri):
    return {'_id': uri, '_source': {'subject': uri, 'displayId': uri}}


class FindSeedsTests(unittest.TestCase):
    def test_seed_search_is_graph_filtered_and_boosts_exact_ids(self):
        es = mock.Mock()
        es.search.return_value = {'hits': {'hits': []}}
        with mock.patch.object(graphrag.elasticsearch_manager, 'get_es', return_value=es), \
                mock.patch('graphrag.vector_search_enabled', return_value=False):
            graphrag.find_seeds('BBa_B0015', [], 5)
        self.assertEqual(es.search.call_count, 1)
        inner = es.search.call_args.kwargs['body']['query']['function_score']['query']['bool']
        self.assertIn({'bool': {'must_not': {'wildcard': {'graph': '*/user/*'}}}}, inner['filter'][0]['bool']['filter'])
        self.assertEqual(inner['should'][0]['match']['displayId']['query'], 'BBa_B0015')

    def test_rankings_take_turns_and_keep_the_text_top_hit_first(self):
        rankings = {'text': [hit('gfp'), hit('gfp_device'), hit('yfp')],
                    'vector': [hit('gfp_device'), hit('terminator'), hit('gfp')]}
        seeds = graphrag.interleave(rankings, 4)
        self.assertEqual([s['hit']['_id'] for s in seeds], ['gfp', 'gfp_device', 'terminator', 'yfp'])
        self.assertEqual(seeds[0]['matched_by'], ['text', 'vector'])
        self.assertEqual(seeds[2]['matched_by'], ['vector'])

    def test_vector_failure_falls_back_to_keywords(self):
        with mock.patch('graphrag.text_hits', return_value=[hit('gfp')]), \
                mock.patch('graphrag.vector_search_enabled', return_value=True), \
                mock.patch('graphrag.vector_hits', side_effect=RuntimeError('no embedding field')):
            seeds = graphrag.find_seeds('gfp', [], 3)
        self.assertEqual([(s['uri'], s['matched_by']) for s in seeds], [('gfp', ['text'])])


if __name__ == '__main__':
    unittest.main()
