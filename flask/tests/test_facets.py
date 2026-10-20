import re
import unittest
from unittest import mock

import facets
import query


def fake_virtuoso(pairs):
    """Serves OFFSET/LIMIT-paged queries from an in-memory list of (subject, value) pairs."""
    rows = list(pairs)

    def send_query(sparql, endpoint):
        limit = int(re.search(r'LIMIT (\d+)', sparql).group(1))
        offset = int(re.search(r'OFFSET (\d+)', sparql).group(1))
        return [{'subject': s, 'value': v} for s, v in rows[offset:offset + limit]]
    return send_query


class QueryValuePagesTests(unittest.TestCase):
    def pages(self, pairs, page_size):
        with mock.patch('query.send_query', side_effect=fake_virtuoso(pairs)):
            return list(query.query_value_pages('?subject sbol2:role ?value .', page_size=page_size))

    def test_every_pair_is_returned_once(self):
        pairs = [('b', 'r2'), ('a', 'r1'), ('b', 'r1'), ('c', 'r1'), ('b', 'r3')]  # unsorted, like Virtuoso
        for page_size in (1, 2, 3, 5, 100):
            with self.subTest(page_size=page_size):
                rows = [(r['subject'], r['value']) for page in self.pages(pairs, page_size) for r in page]
                self.assertEqual(rows, pairs)

    def test_page_size_exact_multiple_and_empty(self):
        self.assertEqual(len(self.pages([('a', 'r1'), ('b', 'r1')], page_size=1)), 2)
        self.assertEqual(self.pages([], page_size=3), [])


class IndexFacetFieldsTests(unittest.TestCase):
    def test_values_split_across_pages_are_merged_into_one_update(self):
        import index
        pages = [[{'subject': 'a', 'value': 'r1'}, {'subject': 'b', 'value': 'r1'}, {'subject': 'a', 'value': 'r2'}],
                 [{'subject': 'b', 'value': 'r2'}, {'subject': 'x' * 600, 'value': 'r1'}, {'subject': 'a', 'value': 'r1'}]]
        sent = []

        def streaming_bulk(es, actions, raise_on_error):
            for action in actions:
                sent.append(action)
                yield True, {'update': {}}

        with mock.patch.object(facets, 'FACETS', {'role': facets.FACETS['role']}), \
                mock.patch('index.query.query_value_pages', return_value=iter(pages)), \
                mock.patch('index.helpers.streaming_bulk', side_effect=streaming_bulk):
            index.index_facet_fields(mock.Mock(), 'part')

        # one plain partial update per part with all its values; over-long _id skipped
        self.assertEqual([(a['_id'], a['doc']) for a in sent],
                         [('a', {'facet_role': ['r1', 'r2']}), ('b', {'facet_role': ['r1', 'r2']})])


class FacetQueryTests(unittest.TestCase):
    def test_selected_filters_and_across_or_within(self):
        selected = {'role': ['r1', 'r2'], 'creator': ['alice'], 'type': []}
        self.assertEqual(facets.selected_filters(selected), [
            {'terms': {'facet_role': ['r1', 'r2']}},
            {'terms': {'facet_creator': ['alice']}},
        ])

    def test_selected_filters_excludes_own_facet(self):
        selected = {'role': ['r1'], 'creator': ['alice']}
        self.assertEqual(facets.selected_filters(selected, exclude='role'),
                         [{'terms': {'facet_creator': ['alice']}}])

    def test_no_graphs_means_public_only(self):
        self.assertEqual(facets.graph_filter([]),
                         {'bool': {'must_not': {'wildcard': {'graph': '*/user/*'}}}})
        self.assertEqual(facets.graph_filter(['g1', 'g2']), {'terms': {'graph': ['g1', 'g2']}})

    def test_role_label(self):
        self.assertEqual(facets.role_label('http://identifiers.org/so/SO:0000167'), 'promoter')
        self.assertEqual(facets.role_label('http://wiki.synbiohub.org/wiki/Terms/igem#partType/Composite'), 'Composite')


if __name__ == '__main__':
    unittest.main()
