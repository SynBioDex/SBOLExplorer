"""
Answers a question about SynBioHub data with Claude and two tools:

  graphrag_retrieve -- graphrag.retrieve: the parts the question is about and
                       their SBOL relations, as text context
  sparql_query      -- readonly_sparql.run: a read-only query over the
                       caller's graphs, for counts, filters and complete lists

The tool loop runs here, so a web page (SynBioHub's Ask tab) can use it. The
caller's graphs scope both tools; with none given only public data is used.
Every tool call is returned with the answer, so the page can show how the
answer was found.

Off unless "ask" is true in the config and ANTHROPIC_API_KEY is set: each
question is a billed API call.
"""
import logging
import os
import time
from typing import Callable, Dict, List, Optional

import graphrag
import readonly_sparql
from configManager import ConfigManager

log = logging.getLogger(__name__)
config_manager = ConfigManager()

DEFAULT_MODEL = 'claude-opus-5-5'
MAX_TOOL_ROUNDS = 8       # model turns that may call tools before we stop
MAX_TOKENS = 8000
STEP_OUTPUT_CHARS = 4000  # tool output kept per step in the response
MAX_QUESTION_CHARS = 2000

SYSTEM = '''You answer questions about the synthetic biology designs stored in a SynBioHub
repository (SBOL2: parts, devices, collections, sequences), using only what the
tools return.

Tools:
- graphrag_retrieve: start here for questions about specific parts, devices,
  functions or collections. It returns the best-matching parts and their roles,
  sub-parts, parent designs, collections and provenance. Lists marked "top N of
  M by pagerank" are cut.
- sparql_query: for counts, filters (length, role), complete lists and joins.
  The schema and examples are below. Do not use FROM, GRAPH or SERVICE; the
  query already runs over the right data.

Answer in the language of the question, briefly, in Markdown. Cite every part
you mention as a Markdown link to its URI, e.g. [BBa_B0015](https://...). If the
tools do not contain the answer, say so instead of guessing; do not use outside
knowledge about parts as if it came from this repository.

''' + readonly_sparql.SCHEMA

TOOLS = [
    {
        'name': 'graphrag_retrieve',
        'description': ('Find the parts a question is about (keyword plus semantic search) and their '
                        'SBOL relations: roles, sub-parts, parent designs, collections, provenance. '
                        'Returns text context with the parts\' URIs.'),
        'input_schema': {
            'type': 'object',
            'properties': {
                'question': {'type': 'string', 'description': 'The question or search keywords.'},
                'k': {'type': 'integer', 'description': 'Number of seed parts, 1-20 (default 5).'},
                'hops': {'type': 'integer', 'description': 'Relation steps from the seeds, 1 or 2 (default 1).'},
            },
            'required': ['question'],
        },
    },
    {
        'name': 'sparql_query',
        'description': ('Run a read-only SPARQL query (SELECT, ASK, CONSTRUCT or DESCRIBE) over the '
                        'repository. Results are tab-separated, at most 200 rows shown.'),
        'input_schema': {
            'type': 'object',
            'properties': {'query': {'type': 'string', 'description': 'The SPARQL query.'}},
            'required': ['query'],
        },
    },
]


class AskUnavailable(Exception):
    """/ask is turned off or has no API key."""


def enabled() -> bool:
    return bool(config_manager.load_config().get('ask', False)) and bool(os.environ.get('ANTHROPIC_API_KEY'))


def model() -> str:
    return config_manager.load_config().get('ask_model', DEFAULT_MODEL)


def sparql_graphs(graphs: List[str]) -> List[str]:
    """The dataset for model-written SPARQL: the caller's graphs, or the public graph."""
    return graphs or [config_manager.load_config().get('public_graph', readonly_sparql.DEFAULT_PUBLIC_GRAPH)]


def clamp(value, default: int, low: int, high: int) -> int:
    try:
        return min(max(int(value), low), high)
    except (TypeError, ValueError):
        return default


MATCH_LABELS = {'text': 'keywords', 'vector': 'meaning'}


def seed_sources(result: Dict) -> str:
    """One line naming each seed and the search that found it, as the MCP server does."""
    seeds = [n for n in result['nodes'] if n.get('seed')]
    seeds.sort(key=lambda n: n.get('rank', 0))
    return 'Seeds (found by): ' + ', '.join(
        f"{n.get('displayId')} [{' + '.join(MATCH_LABELS.get(m, m) for m in n.get('matched_by', []))}]"
        for n in seeds)


def run_tool(name: str, tool_input: Dict, graphs: List[str], uri2rank: Optional[Dict]) -> str:
    """Runs one tool call; raises ValueError for a call the model can correct."""
    if name == 'graphrag_retrieve':
        question = str(tool_input.get('question', '')).strip()
        if not question:
            raise ValueError('question is required')
        result = graphrag.retrieve(question, graphs=graphs,
                                   k=clamp(tool_input.get('k'), 5, 1, 20),
                                   hops=clamp(tool_input.get('hops'), 1, 1, 2),
                                   uri2rank=uri2rank)
        if not result['context']:
            return 'No matching parts found.'
        return f"{seed_sources(result)}\n\n{result['context']}"
    if name == 'sparql_query':
        endpoint = config_manager.load_config()['sparql_endpoint']
        return readonly_sparql.format_results(
            readonly_sparql.run(str(tool_input.get('query', '')), sparql_graphs(graphs), endpoint))
    raise ValueError(f'Unknown tool {name}')


def ask(question: str, graphs: Optional[List[str]] = None, uri2rank: Optional[Dict] = None,
        client=None, clock: Callable[[], float] = time.monotonic) -> Dict:
    """
    Returns {question, answer, steps: [{tool, input, output, error, seconds}],
    model, stop_reason, usage}.
    """
    graphs = graphs or []
    if client is None:
        if not enabled():
            raise AskUnavailable('Ask is turned off (set "ask": true in the config and ANTHROPIC_API_KEY).')
        import anthropic  # only needed when ask is on
        client = anthropic.Anthropic()

    messages = [{'role': 'user', 'content': question[:MAX_QUESTION_CHARS]}]
    steps: List[Dict] = []
    usage = {'input_tokens': 0, 'output_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}
    stop_reason = None
    answer = ''

    for round_ in range(MAX_TOOL_ROUNDS + 1):
        response = client.messages.create(
            model=model(),
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
            cache_control={'type': 'ephemeral'},  # system prompt and tools repeat every round
        )
        for key in usage:
            usage[key] += getattr(response.usage, key, 0) or 0
        stop_reason = response.stop_reason
        answer = '\n\n'.join(b.text for b in response.content if b.type == 'text').strip()

        if stop_reason == 'pause_turn':
            messages.append({'role': 'assistant', 'content': response.content})
            continue
        if stop_reason != 'tool_use':
            break  # end_turn, max_tokens, refusal: return what there is
        if round_ == MAX_TOOL_ROUNDS:
            stop_reason = 'max_tool_rounds'
            answer = (answer + '\n\n' if answer else '') + \
                f'_Stopped after {MAX_TOOL_ROUNDS} rounds of tool calls without a final answer._'
            break

        messages.append({'role': 'assistant', 'content': response.content})
        results = []
        for block in response.content:
            if block.type != 'tool_use':
                continue
            started = clock()
            step = {'tool': block.name, 'input': block.input}
            try:
                output = run_tool(block.name, block.input, graphs, uri2rank)
                results.append({'type': 'tool_result', 'tool_use_id': block.id, 'content': output})
            except ValueError as e:
                output = f'Error: {e}'
                step['error'] = True
                results.append({'type': 'tool_result', 'tool_use_id': block.id, 'content': output,
                                'is_error': True})
            step['output'] = output[:STEP_OUTPUT_CHARS]
            step['seconds'] = round(clock() - started, 2)
            steps.append(step)
        messages.append({'role': 'user', 'content': results})

    if not answer:
        answer = {'refusal': '_The model declined to answer this question._',
                  'max_tokens': '_The answer was cut off (output limit reached)._'}.get(
                      stop_reason, '_No answer was returned._')
    return {'question': question, 'answer': answer, 'steps': steps, 'model': model(),
            'stop_reason': stop_reason, 'usage': usage}
