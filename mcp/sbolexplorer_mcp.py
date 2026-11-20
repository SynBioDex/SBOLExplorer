# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=2.3,<3", "requests>=2.32"]
# ///
"""
MCP server that lets an LLM client (e.g. Claude Code) answer questions from
SynBioHub data through SBOLExplorer.

Tools:
  graphrag_retrieve -- SBOLExplorer's /graphrag: the parts a question is about
                       and their SBOL relations, as text context
  sparql_query      -- a read-only SPARQL query over the public graph, for
                       counts, filters and anything /graphrag does not cover
  sparql_schema     -- prefixes, data model and example queries to write
                       sparql_query queries from

Only public data is exposed. Every SPARQL query is sent with the public graph
as its default and only named graph, and queries that could name another
graph, write or reach Virtuoso internals are refused before they are sent
(flask/readonly_sparql.py): SynBioHub's Virtuoso endpoint accepts writes, so
the endpoint itself is not a safeguard.

Run: uv run --script mcp/sbolexplorer_mcp.py
Settings (environment): EXPLORER_URL, SPARQL_ENDPOINT, PUBLIC_GRAPH.
"""
import os
import sys

import requests
from mcp.server.mcpserver import MCPServer

# The read-only guard and schema are shared with SBOLExplorer's /ask.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'flask'))
import readonly_sparql  # noqa: E402

EXPLORER_URL = os.environ.get('EXPLORER_URL', 'http://localhost:13162').rstrip('/')
SPARQL_ENDPOINT = os.environ.get('SPARQL_ENDPOINT', 'http://localhost:8890/sparql')
PUBLIC_GRAPH = os.environ.get('PUBLIC_GRAPH', readonly_sparql.DEFAULT_PUBLIC_GRAPH)

server = MCPServer('sbolexplorer')


# ---------------------------------------------------------------------- tools

@server.tool()
def graphrag_retrieve(question: str, k: int = 5, hops: int = 1, max_neighbors: int = 10) -> str:
    """Find the SynBioHub parts a question is about and their SBOL relations.

    Use this first for questions about specific parts, devices or collections
    ("what is BBa_B0015?", "which designs use GFP?", "parts that stop
    transcription"). Seeds come from keyword plus semantic search; their roles,
    sub-parts, parent designs, collections and provenance are read from the
    knowledge graph. Answer from this context and cite the <URIs>. Lists marked
    "top N of M by pagerank" are cut; use sparql_query for complete lists or counts.

    Args:
        question: the question or keywords
        k: number of seed parts (1-20)
        hops: relation steps from the seeds, 1 or 2 (2 is slower and larger)
        max_neighbors: neighbours kept per part and relation (1-50)
    """
    response = requests.get(f'{EXPLORER_URL}/graphrag', params={
        'query': question, 'k': k, 'hops': hops, 'max_neighbors': max_neighbors,
    }, timeout=60)
    if response.status_code == 404:
        return f'{EXPLORER_URL}/graphrag not found: SBOLExplorer is not running the graphrag branch (restart it).'
    response.raise_for_status()
    result = response.json()
    seeds = ', '.join(f"{n.get('displayId')} [{'+'.join(n.get('matched_by', []))}]"
                      for n in result['nodes'] if n.get('seed'))
    return f"Seeds (matched by): {seeds}\n\n{result['context']}"


@server.tool()
def sparql_query(query: str) -> str:
    """Run a read-only SPARQL query over SynBioHub's public graph.

    Use for counts, filters, complete lists and multi-step joins that
    graphrag_retrieve does not answer. Call sparql_schema first for prefixes,
    the data model and examples. Only SELECT, ASK, CONSTRUCT and DESCRIBE are
    allowed; FROM, GRAPH and SERVICE are refused (the query already runs over
    the public graph). Results are tab-separated, at most 200 rows shown.
    """
    try:
        return readonly_sparql.format_results(readonly_sparql.run(query, [PUBLIC_GRAPH], SPARQL_ENDPOINT))
    except ValueError as e:
        return f'Error: {e}'


@server.tool()
def sparql_schema() -> str:
    """Prefixes, SBOL data model and example queries for writing sparql_query queries."""
    return readonly_sparql.SCHEMA


if __name__ == '__main__':
    server.run()
