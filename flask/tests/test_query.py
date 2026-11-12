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


class QueryPartsFreshnessTests(unittest.TestCase):
    """#187: a part added to a collection must show up in the next search."""

    @mock.patch("query.query_sparql")
    def test_repeated_query_reads_virtuoso_again(self, query_sparql):
        criteria = "<http://example.test/public/collection/1> sbol2:member ?subject ."
        query_sparql.side_effect = [
            [{"subject": "http://example.test/part1"}],
            [{"subject": "http://example.test/part1"}, {"subject": "http://example.test/part2"}],
        ]

        before = query.query_parts("FROM <http://example.test/public>", criteria)
        after = query.query_parts("FROM <http://example.test/public>", criteria)

        self.assertEqual(query_sparql.call_count, 2)
        self.assertEqual(len(before), 1)
        self.assertEqual(len(after), 2)


PUBLIC = "https://synbiohub.org/public"
ALICE = "https://synbiohub.org/user/alice"
PRIVATE_COLLECTION = ALICE + "/mine/mine_collection/1"
PUBLIC_PART = PUBLIC + "/igem/BBa_B0034/1"
PRIVATE_PART = ALICE + "/mine/part1/1"


def collection_search(text=""):
    # The shape of SynBioHub's sparql/search.sparql for "collection=<...>&<text>".
    criteria = f"<{PRIVATE_COLLECTION}> sbol2:member ?subject ."
    if text:
        criteria += f" FILTER (CONTAINS(lcase(?displayId), lcase('{text}')))"
    return f"""
        SELECT DISTINCT ?subject ?displayId ?version ?name ?description ?type ?sbolType ?role
        FROM <{PUBLIC}> FROM <{ALICE}>
        WHERE {{
            {criteria}

            ?subject a ?type .
            ?subject sbh:topLevel ?subject
        }}
        LIMIT 50 OFFSET 0
    """


def row(subject):
    return {"subject": subject, "displayId": subject.rsplit("/", 2)[-2], "version": "1",
            "name": "", "description": "", "type": "http://sbols.org/v2#ComponentDefinition"}


class PrivateCollectionSearchTests(unittest.TestCase):
    """#187: a public part in a private collection must be found by collection."""

    def fake_virtuoso(self, _from, criteria):
        # The membership triple is in Alice's graph, the public part's own triples
        # in the public graph: only a query over both graphs joins them.
        if f"FROM <{PUBLIC}>" in _from and f"FROM <{ALICE}>" in _from:
            return [row(PUBLIC_PART), row(PRIVATE_PART)]
        if f"FROM <{ALICE}>" in _from:
            return [row(PRIVATE_PART)]
        return []

    def run_search(self, sparql):
        with mock.patch("search.query.query_parts", side_effect=self.fake_virtuoso), \
             mock.patch("search.search_es_allowed_subjects") as es:
            es.side_effect = lambda text, subjects: {"hits": {"hits": [
                {"_source": {"subject": s, "displayId": "BBa_B0034", "version": "1", "name": "",
                             "description": "", "type": "", "graph": PUBLIC},
                 "_score": 1.0}
                for s in subjects]}}
            result = search.search(sparql, {}, {}, PUBLIC)
        return [b["subject"]["value"] for b in result["results"]["bindings"]]

    def test_structural_search_finds_public_part_in_private_collection(self):
        subjects = self.run_search(collection_search())

        self.assertIn(PUBLIC_PART, subjects)
        self.assertIn(PRIVATE_PART, subjects)
        self.assertEqual(len(subjects), 2)

    def test_private_results_stay_above_public(self):
        subjects = self.run_search(collection_search())

        self.assertEqual(subjects[0], PRIVATE_PART)

    def test_text_and_collection_search_finds_public_part(self):
        subjects = self.run_search(collection_search("BBa"))

        self.assertIn(PUBLIC_PART, subjects)


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
