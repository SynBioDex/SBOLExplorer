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
graph (FROM, GRAPH, SERVICE), write (INSERT, DELETE, LOAD, ...) or reach
Virtuoso internals (DEFINE, bif:, sql:) are refused before they are sent:
SynBioHub's Virtuoso endpoint accepts writes, so the endpoint itself is not a
safeguard.

Run: uv run --script mcp/sbolexplorer_mcp.py
Settings (environment): EXPLORER_URL, SPARQL_ENDPOINT, PUBLIC_GRAPH.
"""
import os
import re

import requests
from mcp.server.mcpserver import MCPServer

EXPLORER_URL = os.environ.get('EXPLORER_URL', 'http://localhost:13162').rstrip('/')
SPARQL_ENDPOINT = os.environ.get('SPARQL_ENDPOINT', 'http://localhost:8890/sparql')
PUBLIC_GRAPH = os.environ.get('PUBLIC_GRAPH', 'https://synbiohub.org/public')

MAX_ROWS = 200
TIMEOUT_SECONDS = 30

server = MCPServer('sbolexplorer')


# ---------------------------------------------------------------- SPARQL guard

QUERY_FORMS = {'SELECT', 'ASK', 'CONSTRUCT', 'DESCRIBE'}

# Keywords refused anywhere outside IRIs, strings and comments. A word right
# after ?, $ or : is a variable (?graph) or a prefixed name (ex:from), not a
# keyword, so it is allowed.
FORBIDDEN = re.compile(
    r'(?<![?$:\w])(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|ADD|MOVE|COPY|WITH|USING'  # updates
    r'|FROM|GRAPH|SERVICE'                                              # other datasets
    r'|DEFINE)\b'                                                       # Virtuoso pragmas
    r'|\b(bif|sql):',                                                   # Virtuoso built-ins
    re.IGNORECASE)

IRI = re.compile(r'<[^<>"{}|^`\\\s]*>')
STRING = re.compile(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
COMMENT = re.compile(r'#[^\n]*')
PROLOGUE = re.compile(r'^\s*(?:(?:PREFIX\s+[\w.-]*:|BASE)\s*)', re.IGNORECASE)


def check_read_only(sparql: str) -> None:
    """Raises ValueError unless sparql is a read-only query over the default dataset."""
    # IRIs and strings may contain '#' and keywords; blank them first, then comments.
    code = STRING.sub('""', IRI.sub('<>', sparql))
    code = COMMENT.sub(' ', code)

    match = FORBIDDEN.search(code)
    if match:
        raise ValueError(f'"{match.group(0)}" is not allowed: only read-only queries over the '
                         f'public graph can be run (no FROM, GRAPH, SERVICE, updates or Virtuoso pragmas).')

    rest = code
    while True:  # skip PREFIX/BASE declarations (IRIs are already blanked to <>)
        stripped = PROLOGUE.match(rest)
        if not stripped:
            break
        rest = rest[stripped.end():].lstrip()
        rest = rest[2:] if rest.startswith('<>') else rest
    form = rest.lstrip().split(None, 1)[0].upper() if rest.strip() else ''
    if form not in QUERY_FORMS:
        raise ValueError(f'Query must be one of {", ".join(sorted(QUERY_FORMS))}, not "{form or "empty"}".')


def run_sparql(sparql: str) -> dict:
    check_read_only(sparql)
    response = requests.post(
        SPARQL_ENDPOINT,
        data={
            'query': sparql,
            'default-graph-uri': PUBLIC_GRAPH,
            'named-graph-uri': PUBLIC_GRAPH,
            'timeout': str(TIMEOUT_SECONDS * 1000),  # Virtuoso's own limit, in ms
        },
        headers={'Accept': 'application/sparql-results+json'},
        timeout=TIMEOUT_SECONDS + 5)
    if not response.ok:
        raise ValueError(f'SPARQL endpoint returned {response.status_code}: {response.text[:500]}')
    return response.json()


def format_results(results: dict) -> str:
    if 'boolean' in results:
        return str(results['boolean']).lower()
    columns = results['head']['vars']
    rows = results['results']['bindings']
    lines = ['\t'.join(columns)]
    for row in rows[:MAX_ROWS]:
        lines.append('\t'.join(row.get(c, {}).get('value', '') for c in columns))
    if len(rows) > MAX_ROWS:
        lines.append(f'... {len(rows) - MAX_ROWS} more rows not shown; add LIMIT/OFFSET or aggregate.')
    lines.append(f'({len(rows)} rows)')
    return '\n'.join(lines)


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
        return format_results(run_sparql(query))
    except ValueError as e:
        return f'Error: {e}'


SCHEMA = '''SynBioHub stores SBOL2 as RDF. Useful prefixes (declare the ones you use):
PREFIX sbol2: <http://sbols.org/v2#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX sbh: <http://wiki.synbiohub.org/wiki/Terms/synbiohub#>
PREFIX so: <http://identifiers.org/so/SO:>   # write so:0000141 (Virtuoso rejects so:SO:0000141)
PREFIX biopax: <http://www.biopax.org/release/biopax-level3.owl#>

Top-level objects: ?x sbh:topLevel ?x . Types: sbol2:ComponentDefinition (parts and
devices), sbol2:ModuleDefinition (systems), sbol2:Collection, sbol2:Sequence.
Common properties: sbol2:displayId, dcterms:title, dcterms:description, sbol2:version.

Parts (ComponentDefinition):
  sbol2:type biopax:DnaRegion (DNA), sbol2:role a Sequence Ontology term, e.g.
    so:0000167 promoter, so:0000139 ribosome entry site (RBS),
    so:0000316 CDS, so:0000141 terminator, so:0000804 engineered region.
  Composition: ?device sbol2:component ?c . ?c sbol2:definition ?subpart .
  Position: ?device sbol2:sequenceAnnotation ?a . ?a sbol2:component ?c ;
            sbol2:location ?l . ?l sbol2:start ?start ; sbol2:end ?end .
  Sequence: ?part sbol2:sequence ?s . ?s sbol2:elements ?dna .
Collections: ?collection sbol2:member ?part .
Provenance: ?part prov:wasDerivedFrom ?source .
Systems (ModuleDefinition), where present: sbol2:module, sbol2:functionalComponent,
  sbol2:interaction ?i . ?i sbol2:type ?interactionType ;
  sbol2:participation ?p . ?p sbol2:role ?participantRole ; sbol2:participant ?fc .

Examples:
# How many terminators are there?
SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p a sbol2:ComponentDefinition ; sbol2:role so:0000141 . }

# Terminators shorter than 50 bp
SELECT ?p ?id (STRLEN(?dna) AS ?bp) WHERE {
  ?p sbol2:role so:0000141 ; sbol2:displayId ?id ; sbol2:sequence ?s . ?s sbol2:elements ?dna .
  FILTER(STRLEN(?dna) < 50) } ORDER BY ?bp

# Ordered sub-parts of a device
SELECT ?subId ?start ?end WHERE {
  <https://synbiohub.org/public/igem/BBa_E0240/1> sbol2:sequenceAnnotation ?a .
  ?a sbol2:component ?c ; sbol2:location ?l . ?c sbol2:definition ?sub .
  ?sub sbol2:displayId ?subId . ?l sbol2:start ?start ; sbol2:end ?end . } ORDER BY ?start

# Which promoters are used in the most devices?
SELECT ?id (COUNT(DISTINCT ?d) AS ?uses) WHERE {
  ?p sbol2:role so:0000167 ; sbol2:displayId ?id .
  ?d sbol2:component ?c . ?c sbol2:definition ?p . } GROUP BY ?id ORDER BY DESC(?uses) LIMIT 10

Role IRIs may also appear as http://purl.obolibrary.org/obo/SO_0000141 or as iGEM
terms (http://wiki.synbiohub.org/wiki/Terms/igem#partType/Terminator); if a role
query returns nothing, list the roles in use first:
SELECT ?role (COUNT(*) AS ?n) WHERE { ?p sbol2:role ?role } GROUP BY ?role ORDER BY DESC(?n)
'''


@server.tool()
def sparql_schema() -> str:
    """Prefixes, SBOL data model and example queries for writing sparql_query queries."""
    return SCHEMA


if __name__ == '__main__':
    server.run()
