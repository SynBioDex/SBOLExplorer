import ast
from pathlib import Path
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import query
import search


class QueryProtocolTests(unittest.TestCase):
    @mock.patch("query.requests.get")
    def test_union_index_query_omits_empty_default_graph(self, get):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"results": {"bindings": []}}
        get.return_value = response

        query.send_query("SELECT ?s WHERE { ?s ?p ?o }", query.config["sparql_endpoint"])

        requested_url = get.call_args.args[0]
        parameters = parse_qs(urlsplit(requested_url).query, keep_blank_values=True)
        self.assertIn("query", parameters)
        self.assertNotIn("default-graph-uri", parameters)


class SearchDatasetTests(unittest.TestCase):
    def test_row_query_extracts_graphs_after_extended_projection(self):
        sparql = """
            SELECT DISTINCT
                ?subject
                ?type
                ?sbolType
                ?role
            FROM <http://example.test/public>
            FROM <http://example.test/user/alice>
            WHERE {
                ?subject a ?type .
                ?subject sbh:topLevel ?subject .
            }
            LIMIT 50
            OFFSET 0
        """

        _, from_clause, _, _, _, _, _ = search.extract_query(sparql)

        self.assertEqual(
            from_clause,
            "FROM <http://example.test/public> FROM <http://example.test/user/alice>",
        )

    def test_count_query_extracts_outer_graphs(self):
        sparql = """
            SELECT (sum(?tempcount) as ?count)
            FROM <http://example.test/user/alice>
            WHERE {
                {
                    SELECT (count(distinct ?subject) as ?tempcount)
                    WHERE { ?subject a ?type . }
                }
            }
        """

        _, from_clause, _, _, _, _, _ = search.extract_query(sparql)

        self.assertEqual(from_clause, "FROM <http://example.test/user/alice>")


class StartupOrderTests(unittest.TestCase):
    def test_update_index_is_defined_before_startup_is_called(self):
        source = Path(__file__).parents[1] / "explorer.py"
        module = ast.parse(source.read_text())
        update_definition = next(
            node.lineno
            for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name == "update_index"
        )
        startup_call = next(
            node.lineno
            for node in module.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "startup"
        )
        self.assertLess(update_definition, startup_call)


if __name__ == "__main__":
    unittest.main()
