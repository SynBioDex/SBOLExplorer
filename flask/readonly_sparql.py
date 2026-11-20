"""
Read-only SPARQL for LLM-written queries, scoped to the caller's graphs.

Used by /ask (ask.py) and the MCP server (mcp/sbolexplorer_mcp.py), which run
SPARQL that a model wrote. SynBioHub's Virtuoso endpoint accepts SPARQL
UPDATE, and a query that names a graph itself (FROM <g>, GRAPH <g>) reads it
whatever default-graph-uri says, so check_read_only refuses both before
anything is sent. Every query then runs with the caller's graphs as its
default and only named graphs.
"""
import re
from typing import Dict, List

import requests

DEFAULT_PUBLIC_GRAPH = 'https://synbiohub.org/public'
MAX_ROWS = 200
TIMEOUT_SECONDS = 30

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
                         f'given graphs can be run (no FROM, GRAPH, SERVICE, updates or Virtuoso pragmas).')

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


def run(sparql: str, graphs: List[str], endpoint: str) -> Dict:
    """Runs a checked query with graphs as the whole dataset; raises ValueError on refusal or failure."""
    check_read_only(sparql)
    if not graphs:
        raise ValueError('No graphs to query.')
    response = requests.post(
        endpoint.rstrip('?'),
        data={
            'query': sparql,
            'default-graph-uri': graphs,  # repeated keys: the union of the graphs
            'named-graph-uri': graphs,
            'timeout': str(TIMEOUT_SECONDS * 1000),  # Virtuoso's own limit, in ms
        },
        headers={'Accept': 'application/sparql-results+json'},
        timeout=TIMEOUT_SECONDS + 5)
    if not response.ok:
        raise ValueError(f'SPARQL endpoint returned {response.status_code}: {response.text[:500]}')
    return response.json()


def format_results(results: Dict) -> str:
    """Tab-separated rows, at most MAX_ROWS, with the total."""
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
