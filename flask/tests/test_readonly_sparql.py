import unittest
from unittest import mock

import readonly_sparql

PREFIXES = 'PREFIX sbol2: <http://sbols.org/v2#>\nPREFIX so: <http://identifiers.org/so/SO:>\n'


class ReadOnlyGuardTests(unittest.TestCase):
    def assertAllowed(self, sparql):
        readonly_sparql.check_read_only(sparql)

    def assertRefused(self, sparql):
        with self.assertRaises(ValueError, msg=sparql):
            readonly_sparql.check_read_only(sparql)

    def test_query_forms_are_allowed(self):
        self.assertAllowed(PREFIXES + 'SELECT ?p WHERE { ?p sbol2:role so:0000141 } LIMIT 5')
        self.assertAllowed('select (count(*) as ?n) where { ?s ?p ?o }')
        self.assertAllowed('ASK { ?s a <http://sbols.org/v2#Collection> }')
        self.assertAllowed('CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o } LIMIT 1')
        self.assertAllowed('BASE <http://x/> DESCRIBE <a>')

    def test_keywords_inside_iris_strings_comments_and_names_are_allowed(self):
        self.assertAllowed('SELECT ?s WHERE { ?s ?p "insert delete from graph" }')
        self.assertAllowed('SELECT ?s WHERE { ?s <http://example.org/graph#from> ?o }')
        self.assertAllowed('SELECT ?s WHERE { ?s ?p ?o } # DELETE everything')
        self.assertAllowed('SELECT ?graph ?from WHERE { ?graph ?with ?from }')
        self.assertAllowed('PREFIX ex: <http://x/> SELECT ?s WHERE { ?s ex:from ex:graph }')
        self.assertAllowed('SELECT ?s WHERE { ?s ?p "a \\" DELETE" }')

    def test_updates_are_refused(self):
        for update in ['INSERT DATA { <a:a> <a:b> <a:c> }',
                       'DELETE WHERE { ?s ?p ?o }',
                       'WITH <urn:g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }',
                       'LOAD <http://evil/data.ttl>',
                       'CLEAR GRAPH <https://synbiohub.org/public>',
                       'DROP ALL',
                       'CREATE GRAPH <urn:g>',
                       'SELECT * WHERE { ?s ?p ?o } ; DELETE WHERE { ?s ?p ?o }']:
            self.assertRefused(update)

    def test_other_graphs_are_refused(self):
        self.assertRefused('SELECT * FROM <https://synbiohub.org/user/sophia> WHERE { ?s ?p ?o }')
        self.assertRefused('SELECT * FROM NAMED <https://synbiohub.org/user/x> WHERE { ?s ?p ?o }')
        self.assertRefused('SELECT * WHERE { GRAPH <https://synbiohub.org/user/sophia> { ?s ?p ?o } }')
        self.assertRefused('SELECT * WHERE { GRAPH ?g { ?s ?p ?o } }')
        self.assertRefused('SELECT * WHERE { SERVICE <http://other/sparql> { ?s ?p ?o } }')

    def test_virtuoso_pragmas_and_builtins_are_refused(self):
        self.assertRefused('define input:default-graph-uri <https://synbiohub.org/user/x> SELECT * WHERE { ?s ?p ?o }')
        self.assertRefused('SELECT * WHERE { ?s ?p ?o . FILTER(bif:exec("x")) }')
        self.assertRefused('SELECT (sql:anything() AS ?x) WHERE { }')

    def test_keyword_hidden_after_an_unclosed_looking_iri_or_comment_is_refused(self):
        # '#' inside an IRI must not comment out the rest of the line
        self.assertRefused('SELECT * WHERE { ?s <http://x/#> ?o } INSERT DATA { <a:a> <a:b> <a:c> }')
        self.assertRefused('SELECT * WHERE { ?s ?p "#" } DELETE WHERE { ?s ?p ?o }')

    def test_non_queries_are_refused(self):
        self.assertRefused('')
        self.assertRefused('PREFIX ex: <http://x/>')
        self.assertRefused('hello')


class RunTests(unittest.TestCase):
    def test_graphs_are_the_whole_dataset(self):
        response = mock.Mock(ok=True)
        response.json.return_value = {'head': {'vars': ['n']}, 'results': {'bindings': [{'n': {'value': '3'}}]}}
        graphs = ['https://synbiohub.org/public', 'https://synbiohub.org/user/a']
        with mock.patch('readonly_sparql.requests.post', return_value=response) as post:
            results = readonly_sparql.run('SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }', graphs,
                                          'http://localhost:8890/sparql?')
        self.assertEqual(readonly_sparql.format_results(results), 'n\n3\n(1 rows)')
        self.assertEqual(post.call_args.args[0], 'http://localhost:8890/sparql')
        data = post.call_args.kwargs['data']
        self.assertEqual(data['default-graph-uri'], graphs)
        self.assertEqual(data['named-graph-uri'], graphs)

    def test_refused_query_is_never_sent(self):
        with mock.patch('readonly_sparql.requests.post') as post:
            with self.assertRaises(ValueError):
                readonly_sparql.run('DROP ALL', ['https://synbiohub.org/public'], 'http://x/sparql')
        post.assert_not_called()

    def test_no_graphs_is_refused(self):
        with mock.patch('readonly_sparql.requests.post') as post:
            with self.assertRaises(ValueError):
                readonly_sparql.run('SELECT * WHERE { ?s ?p ?o }', [], 'http://x/sparql')
        post.assert_not_called()

    def test_long_results_are_cut(self):
        rows = [{'s': {'value': str(i)}} for i in range(readonly_sparql.MAX_ROWS + 5)]
        text = readonly_sparql.format_results({'head': {'vars': ['s']}, 'results': {'bindings': rows}})
        self.assertIn('5 more rows not shown', text)
        self.assertTrue(text.endswith(f'({readonly_sparql.MAX_ROWS + 5} rows)'))


if __name__ == '__main__':
    unittest.main()
