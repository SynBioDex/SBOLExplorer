# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=2.3,<3", "requests>=2.32"]
# ///
"""Run: uv run --script mcp/test_sbolexplorer_mcp.py
The read-only guard itself is tested in flask/tests/test_readonly_sparql.py."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbolexplorer_mcp as m  # noqa: E402


class SparqlQueryTests(unittest.TestCase):
    def test_every_query_is_pinned_to_the_public_graph(self):
        response = mock.Mock(ok=True)
        response.json.return_value = {'head': {'vars': ['n']}, 'results': {'bindings': [{'n': {'value': '3'}}]}}
        with mock.patch('readonly_sparql.requests.post', return_value=response) as post:
            self.assertEqual(m.sparql_query('SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }'), 'n\n3\n(1 rows)')
        data = post.call_args.kwargs['data']
        self.assertEqual(data['default-graph-uri'], [m.PUBLIC_GRAPH])
        self.assertEqual(data['named-graph-uri'], [m.PUBLIC_GRAPH])

    def test_refused_query_is_never_sent(self):
        with mock.patch('readonly_sparql.requests.post') as post:
            self.assertTrue(m.sparql_query('DROP ALL').startswith('Error:'))
        post.assert_not_called()

    def test_schema_is_shared(self):
        self.assertIn('so:0000141', m.sparql_schema())


if __name__ == '__main__':
    unittest.main()
