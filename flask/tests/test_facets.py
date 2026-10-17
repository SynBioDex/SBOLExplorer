import re
import unittest
from unittest import mock

import facets
import query


def fake_virtuoso(pairs):
    """
    Serves keyset-paged queries from an in-memory list of (subject, value)
    pairs, honouring the (subject, value) keyset FILTER and LIMIT like Virtuoso.
    """
    rows = sorted(set(pairs))

    def send_query(sparql, endpoint):
        limit = int(re.search(r'LIMIT (\d+)', sparql).group(1))
        keyset = re.search(r'STR\(\?subject\) > "([^"]*)".*STR\(\?value\) > "([^"]*)"', sparql)
        selected = [r for r in rows if r > keyset.groups()] if keyset else rows
        return [{'subject': s, 'value': v} for s, v in selected[:limit]]
    return send_query


class QuerySubjectValuesTests(unittest.TestCase):
    def collect(self, pairs, page_size):
        with mock.patch('query.send_query', side_effect=fake_virtuoso(pairs)):
            result = list(query.query_subject_values('?subject sbol2:role ?value .', page_size=page_size))
        subjects = [s for s, _ in result]
        self.assertEqual(len(subjects), len(set(subjects)), 'a subject was yielded twice')
        return dict(result)

    def expected(self, pairs):
        grouped = {}
        for s, v in pairs:
            grouped.setdefault(s, set()).add(v)
        return grouped

    def test_values_split_across_page_boundary_are_merged(self):
        pairs = [('a', 'r1'), ('b', 'r1'), ('b', 'r2'), ('b', 'r3'), ('c', 'r1'), ('d', 'r1'), ('d', 'r2')]
        for page_size in (2, 3, 4, 5, 100):
            with self.subTest(page_size=page_size):
                self.assertEqual(self.collect(pairs, page_size), self.expected(pairs))

    def test_subject_with_more_values_than_a_page(self):
        pairs = [('a', 'r1')] + [('b', f'r{i}') for i in range(7)] + [('c', 'r1')]
        for page_size in (2, 3):
            with self.subTest(page_size=page_size):
                self.assertEqual(self.collect(pairs, page_size), self.expected(pairs))

    def test_page_size_exact_multiple(self):
        pairs = [('a', 'r1'), ('b', 'r1'), ('c', 'r1'), ('d', 'r1')]
        self.assertEqual(self.collect(pairs, page_size=2), self.expected(pairs))

    def test_empty(self):
        self.assertEqual(self.collect([], page_size=3), {})


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
