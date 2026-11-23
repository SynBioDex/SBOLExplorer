import unittest
from types import SimpleNamespace
from unittest import mock

import ask


def text(t):
    return SimpleNamespace(type='text', text=t)


def tool_use(id_, name, tool_input):
    return SimpleNamespace(type='tool_use', id=id_, name=name, input=tool_input)


def reply(stop_reason, *content):
    return SimpleNamespace(stop_reason=stop_reason, content=list(content),
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                                                 cache_creation_input_tokens=0, cache_read_input_tokens=0))


class FakeClient:
    """Plays back replies and records each request's messages."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        self.requests.append({**kwargs, 'messages': list(kwargs['messages'])})
        return self.replies.pop(0)


CONFIG = {'sparql_endpoint': 'http://localhost:8890/sparql?', 'ask': True}


class AskTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ask.config_manager, 'load_config', return_value=CONFIG)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_tool_results_go_back_to_the_model_and_steps_are_returned(self):
        client = FakeClient(
            reply('tool_use', text('Looking it up.'), tool_use('t1', 'graphrag_retrieve', {'question': 'terminator'})),
            reply('end_turn', text('[BBa_B0015](https://synbiohub.org/public/igem/BBa_B0015/1) is a terminator.')))
        retrieved = {'context': '# Matched parts\nBBa_B0015 ...',
                     'nodes': [{'displayId': 'BBa_B0012', 'seed': True, 'rank': 2, 'matched_by': ['vector']},
                               {'displayId': 'BBa_B0010', 'seed': False},
                               {'displayId': 'BBa_B0015', 'seed': True, 'rank': 1, 'matched_by': ['text', 'vector']}]}
        context = 'Seeds (found by): BBa_B0015 [keywords + meaning], BBa_B0012 [meaning]\n\n# Matched parts\nBBa_B0015 ...'
        with mock.patch('ask.graphrag.retrieve', return_value=retrieved) as retrieve:
            result = ask.ask('What is BBa_B0015?', client=client, clock=iter(range(100)).__next__)

        retrieve.assert_called_once_with('terminator', graphs=[], k=5, hops=1, uri2rank=None)
        self.assertEqual(result['answer'], '[BBa_B0015](https://synbiohub.org/public/igem/BBa_B0015/1) is a terminator.')
        self.assertEqual(result['stop_reason'], 'end_turn')
        self.assertEqual(result['steps'], [{'tool': 'graphrag_retrieve', 'input': {'question': 'terminator'},
                                            'output': context, 'seconds': 1}])
        self.assertEqual(result['usage']['input_tokens'], 20)
        tool_result = client.requests[1]['messages'][2]['content'][0]
        self.assertEqual(tool_result, {'type': 'tool_result', 'tool_use_id': 't1', 'content': context})

    def test_sparql_runs_over_the_callers_graphs_or_the_public_graph(self):
        for graphs, expected in [([], ['https://synbiohub.org/public']),
                                 (['https://synbiohub.org/public', 'https://synbiohub.org/user/a'],
                                  ['https://synbiohub.org/public', 'https://synbiohub.org/user/a'])]:
            client = FakeClient(
                reply('tool_use', tool_use('t1', 'sparql_query', {'query': 'SELECT ?s WHERE { ?s ?p ?o }'})),
                reply('end_turn', text('done')))
            results = {'head': {'vars': ['s']}, 'results': {'bindings': []}}
            with mock.patch('ask.readonly_sparql.run', return_value=results) as run:
                ask.ask('q', graphs=graphs, client=client)
            run.assert_called_once_with('SELECT ?s WHERE { ?s ?p ?o }', expected, 'http://localhost:8890/sparql?')

    def test_refused_sparql_is_an_error_the_model_sees(self):
        client = FakeClient(
            reply('tool_use', tool_use('t1', 'sparql_query', {'query': 'DROP ALL'})),
            reply('end_turn', text('I cannot do that.')))
        with mock.patch('readonly_sparql.requests.post') as post:
            result = ask.ask('delete everything', client=client)
        post.assert_not_called()
        self.assertTrue(result['steps'][0]['error'])
        tool_result = client.requests[1]['messages'][2]['content'][0]
        self.assertTrue(tool_result['is_error'])
        self.assertTrue(tool_result['content'].startswith('Error:'))

    def test_stops_after_the_round_limit_without_running_more_tools(self):
        calls = [reply('tool_use', tool_use(f't{i}', 'graphrag_retrieve', {'question': 'x'}))
                 for i in range(ask.MAX_TOOL_ROUNDS + 1)]
        client = FakeClient(*calls)
        with mock.patch('ask.graphrag.retrieve', return_value={'context': 'c', 'nodes': []}) as retrieve:
            result = ask.ask('q', client=client)
        self.assertEqual(result['stop_reason'], 'max_tool_rounds')
        self.assertEqual(retrieve.call_count, ask.MAX_TOOL_ROUNDS)
        self.assertEqual(len(client.requests), ask.MAX_TOOL_ROUNDS + 1)
        self.assertIn('Stopped after', result['answer'])

    def test_refusal_gets_a_message(self):
        result = ask.ask('q', client=FakeClient(reply('refusal')))
        self.assertEqual(result['answer'], '_The model declined to answer this question._')

    def test_off_without_config_flag_or_key(self):
        with mock.patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'k'}):
            self.assertTrue(ask.enabled())
            with mock.patch.object(ask.config_manager, 'load_config', return_value={}):
                self.assertFalse(ask.enabled())
        with mock.patch.dict('os.environ', {}, clear=True):
            self.assertFalse(ask.enabled())
            with self.assertRaises(ask.AskUnavailable):
                ask.ask('q')


if __name__ == '__main__':
    unittest.main()
