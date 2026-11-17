"""
Graph retrieval for GraphRAG over the SynBioHub knowledge graph.

The SBOL data in Virtuoso is already a curated knowledge graph, so unlike
text-based GraphRAG there is no LLM entity-extraction step. Retrieval is:

  1. seeds   -- Elasticsearch text search (the same match /search uses,
                weighted by pagerank) finds the parts the question names;
  2. expand  -- SPARQL walks the SBOL relations around each seed
                (roles, sub-parts, parent designs, collections, provenance);
  3. prune   -- hub nodes (a terminator used by thousands of designs, a
                collection with thousands of members) are cut to the
                highest-pagerank neighbours;
  4. context -- the subgraph is returned as triples and as plain text an
                LLM can be given, with URIs so answers can cite them.

This module only retrieves; it never calls an LLM.
"""
from typing import Dict, Iterable, List, Optional

import facets
import query
import search
from configManager import ConfigManager
from elasticsearchManager import ElasticsearchManager
from logger import Logger

config_manager = ConfigManager()
elasticsearch_manager = ElasticsearchManager(config_manager)
logger_ = Logger()

SBOL2 = 'http://sbols.org/v2#'

# Top-level types worth answering about; Sequences are reached through their
# part, not as seeds.
SEED_TYPES = [SBOL2 + 'ComponentDefinition', SBOL2 + 'ModuleDefinition', SBOL2 + 'Collection']

# Relation name -> SPARQL pattern binding ?n, with $S standing for the node
# being expanded. 'expand' marks relations whose neighbours are themselves
# parts or collections and so can be walked on the next hop; roles and types
# are ontology terms and are not walked.
RELATIONS = {
    'role':         {'pattern': '$S sbol2:role ?n .', 'expand': False},
    'sbol_type':    {'pattern': '$S sbol2:type ?n .', 'expand': False},
    'has_subpart':  {'pattern': '$S sbol2:component ?c . ?c sbol2:definition ?n .', 'expand': True},
    'subpart_of':   {'pattern': '?n sbol2:component ?c . ?c sbol2:definition $S .', 'expand': True},
    'has_module':   {'pattern': '$S sbol2:module ?m . ?m sbol2:definition ?n .', 'expand': True},
    'has_functional_component': {'pattern': '$S sbol2:functionalComponent ?f . ?f sbol2:definition ?n .', 'expand': True},
    'member_of':    {'pattern': '?n sbol2:member $S .', 'expand': True},
    'has_member':   {'pattern': '$S sbol2:member ?n .', 'expand': True},
    'derived_from': {'pattern': '$S prov:wasDerivedFrom ?n .', 'expand': True},
    'derived_into': {'pattern': '?n prov:wasDerivedFrom $S .', 'expand': True},
}

# Rows fetched per relation before pagerank pruning. Virtuoso cannot order by
# our pagerank, so a hub's neighbours are sampled up to this cap and the best
# max_neighbors of the sample are kept; the response flags the cut.
FETCH_CAP = 500


def graph_clause(graphs: List[str]) -> str:
    """
    SPARQL counterpart of facets.graph_filter: the caller's graphs, or with
    none given every graph except users' private ones.
    """
    if graphs:
        return 'VALUES ?g { %s }' % ' '.join(f'<{g}>' for g in graphs)
    return 'FILTER(!CONTAINS(STR(?g), "/user/"))'


def seed_filter(graphs: List[str]) -> Dict:
    return {'bool': {'filter': [facets.graph_filter(graphs), {'terms': {'type.keyword': SEED_TYPES}}]}}


def text_hits(question: str, graphs: List[str], size: int) -> List[Dict]:
    """Keyword search, as /search ranks it (text score x pagerank)."""
    body = {
        'size': size,
        'query': {
            'function_score': {
                'query': {
                    'bool': {
                        'must': [search.text_query(question)],
                        # A part named by its ID ("what is in BBa_B0015?") must
                        # beat fuzzy matches such as BBa_B0012 and BBa_B0010.
                        'should': [{'match': {'displayId': {'query': question, 'boost': 20}}}],
                        'filter': [seed_filter(graphs)]
                    }
                },
                'script_score': {
                    'script': {'source': "_score * Math.log(doc['pagerank'].value + 1)"}
                }
            }
        },
        '_source': {'excludes': ['embedding']}
    }
    index_name = config_manager.load_config()['elasticsearch_index_name']
    return elasticsearch_manager.get_es().search(index=index_name, body=body)['hits']['hits']


def vector_hits(question: str, graphs: List[str], size: int) -> List[Dict]:
    """Nearest parts by meaning (the vector_search embeddings)."""
    import embedding  # loads the ONNX model only when vector search is on
    body = {
        'knn': {
            'field': embedding.FIELD,
            'query_vector': embedding.embed([question])[0].tolist(),
            'k': size,
            'num_candidates': max(100, 10 * size),
            'filter': seed_filter(graphs)
        },
        'size': size,
        '_source': {'excludes': [embedding.FIELD]}
    }
    index_name = config_manager.load_config()['elasticsearch_index_name']
    return elasticsearch_manager.get_es().search(index=index_name, body=body)['hits']['hits']


def vector_search_enabled() -> bool:
    return bool(config_manager.load_config().get('vector_search', False))


def interleave(rankings: Dict[str, List[Dict]], k: int) -> List[Dict]:
    """
    The first k distinct hits taking turns between rankings (text 1, vector 1,
    text 2, ...); each entry records every ranking that has the hit.

    Interleaving rather than reciprocal rank fusion: the text ranking is right
    for names and IDs ("GFP" must give GFP itself, not the devices containing
    it nor YFP) and the vector ranking for parts described in other words
    ("stops transcription" -> terminators). RRF lifts hits found by both and so
    pushed GFP to third and YFP out of the top 5; taking turns keeps the text
    top hit first and still gives the vector ranking seats among the seeds.
    """
    found = {}
    for source, hits in rankings.items():
        for hit in hits:
            found.setdefault(hit['_id'], {'hit': hit, 'matched_by': []})['matched_by'].append(source)
    out, seen = [], set()
    for rank in range(max((len(h) for h in rankings.values()), default=0)):
        for hits in rankings.values():
            if rank < len(hits) and hits[rank]['_id'] not in seen and len(out) < k:
                seen.add(hits[rank]['_id'])
                out.append(found[hits[rank]['_id']])
    return out


def find_seeds(question: str, graphs: List[str], k: int = 5) -> List[Dict]:
    """
    The k best-matching top-level parts/collections for the question: keyword
    search fused with vector search when it is turned on, else keywords only.
    """
    # k from each ranking always holds k distinct hits to take turns over
    rankings = {'text': text_hits(question, graphs, k)}
    if vector_search_enabled():
        try:
            rankings['vector'] = vector_hits(question, graphs, k)
        except Exception as e:  # e.g. index built before embeddings were added
            logger_.log(f'[ERROR] graphrag vector search failed, using keywords only: {e}')
    return [{
        'uri': e['hit']['_source']['subject'],
        'displayId': e['hit']['_source'].get('displayId'),
        'name': e['hit']['_source'].get('name'),
        'description': e['hit']['_source'].get('description'),
        'type': e['hit']['_source'].get('type'),
        'graph': e['hit']['_source'].get('graph'),
        'rank': rank,
        'matched_by': e['matched_by'],
    } for rank, e in enumerate(interleave(rankings, k), start=1)]


def run_sparql(sparql: str) -> List[Dict]:
    return query.send_query(f'{query.QUERY_PREFIX} {sparql}', config_manager.load_config()['sparql_endpoint'])


def node_details(uris: Iterable[str], graphs: List[str]) -> Dict[str, Dict]:
    """Title, description, type and sequence length of each node."""
    uris = list(uris)
    if not uris:
        return {}
    rows = run_sparql(f'''
    SELECT ?s ?type ?displayId ?title ?description (MAX(STRLEN(?elements)) AS ?length) WHERE {{
        VALUES ?s {{ {' '.join(f'<{u}>' for u in uris)} }}
        GRAPH ?g {{
            ?s a ?type .
            OPTIONAL {{ ?s sbol2:displayId ?displayId . }}
            OPTIONAL {{ ?s dcterms:title ?title . }}
            OPTIONAL {{ ?s dcterms:description ?description . }}
            OPTIONAL {{ ?s sbol2:sequence ?seq . ?seq sbol2:elements ?elements . }}
        }}
        {graph_clause(graphs)}
    }} GROUP BY ?s ?type ?displayId ?title ?description''')
    details = {}
    for row in rows:
        node = details.setdefault(row['s'], {})
        for key in ('type', 'displayId', 'title', 'description', 'length'):
            if row.get(key) and key not in node:
                node[key] = row[key]
    return details


def neighbours(uri: str, relation: str, graphs: List[str]) -> List[Dict]:
    """Up to FETCH_CAP + 1 neighbours of uri along one relation, with labels."""
    pattern = RELATIONS[relation]['pattern'].replace('$S', f'<{uri}>')
    rows = run_sparql(f'''
    SELECT DISTINCT ?n ?displayId ?title WHERE {{
        GRAPH ?g {{
            {pattern}
            OPTIONAL {{ ?n sbol2:displayId ?displayId . }}
            OPTIONAL {{ ?n dcterms:title ?title . }}
        }}
        {graph_clause(graphs)}
    }} LIMIT {FETCH_CAP + 1}''')
    seen = {}
    for row in rows:
        node = seen.setdefault(row['n'], {'uri': row['n']})
        if row.get('title') and 'title' not in node:
            node['title'] = row['title']
        if row.get('displayId') and 'displayId' not in node:
            node['displayId'] = row['displayId']
    return list(seen.values())


def label(node: Dict, relation: Optional[str] = None) -> str:
    if relation in ('role', 'sbol_type'):
        return facets.role_label(node['uri'])
    return node.get('title') or node.get('displayId') or facets.short_name(node['uri'])


def retrieve(question: str, graphs: Optional[List[str]] = None, k: int = 5, hops: int = 1,
             max_neighbors: int = 10, max_nodes: int = 60, uri2rank: Optional[Dict[str, float]] = None) -> Dict:
    """
    Retrieves the subgraph around the parts a question is about.

    Arguments:
        question -- natural-language question or keywords
        graphs -- graph URIs the caller may see; empty means public graphs only
        k -- number of seed parts from the text search
        hops -- how many relation steps to walk from the seeds (1 or 2)
        max_neighbors -- neighbours kept per node and relation, by pagerank
        max_nodes -- stop expanding once the subgraph holds this many nodes
        uri2rank -- pagerank per URI, used to prune hub neighbours

    Returns:
        {'question', 'seeds', 'nodes', 'triples', 'truncated', 'context'}
    """
    graphs = graphs or []
    uri2rank = uri2rank or {}
    seeds = find_seeds(question, graphs, k)

    nodes = {s['uri']: {'uri': s['uri'], 'displayId': s['displayId'], 'title': s['name'], 'seed': True} for s in seeds}
    triples, truncated = [], []
    frontier = list(nodes)
    for hop in range(hops):
        next_frontier = []
        for uri in frontier:
            for relation, spec in RELATIONS.items():
                found = neighbours(uri, relation, graphs)
                if len(found) > max_neighbors:
                    truncated.append({'uri': uri, 'relation': relation, 'kept': max_neighbors,
                                      'found': f'>{FETCH_CAP}' if len(found) > FETCH_CAP else len(found)})
                    found.sort(key=lambda n: uri2rank.get(n['uri'], 0), reverse=True)
                    found = found[:max_neighbors]
                for n in found:
                    triples.append({'subject': uri, 'predicate': relation, 'object': n['uri'],
                                    'object_label': label(n, relation)})
                    if not spec['expand'] or n['uri'] in nodes:
                        continue
                    if len(nodes) >= max_nodes:
                        continue
                    nodes[n['uri']] = {**n, 'seed': False}
                    next_frontier.append(n['uri'])
        frontier = next_frontier

    for uri, extra in node_details(nodes, graphs).items():
        if uri in nodes:
            nodes[uri].update({key: value for key, value in extra.items() if not nodes[uri].get(key)})
    for seed in seeds:
        nodes[seed['uri']].update(rank=seed['rank'], matched_by=seed['matched_by'])

    return {
        'question': question,
        'seeds': [s['uri'] for s in seeds],
        'nodes': list(nodes.values()),
        'triples': triples,
        'truncated': truncated,
        'context': to_context(seeds, nodes, triples, truncated),
    }


def to_context(seeds: List[Dict], nodes: Dict[str, Dict], triples: List[Dict], truncated: List[Dict]) -> str:
    """The subgraph as plain text for an LLM prompt, one block per node."""
    by_subject = {}
    for t in triples:
        by_subject.setdefault(t['subject'], {}).setdefault(t['predicate'], []).append(t)
    cut = {(t['uri'], t['relation']): t for t in truncated}

    def block(uri: str) -> List[str]:
        node = nodes[uri]
        kind = facets.short_name(node.get('type', '')) or 'Node'
        head = f"[{kind}] {label(node)} <{uri}>"
        if node.get('length'):
            head += f" ({node['length']} bp)"
        lines = [head]
        if node.get('description'):
            lines.append(f"  description: {' '.join(node['description'].split())[:400]}")
        for relation, rows in by_subject.get(uri, {}).items():
            objects = ', '.join(
                t['object_label'] if relation in ('role', 'sbol_type') else f"{t['object_label']} <{t['object']}>"
                for t in rows)
            note = cut.get((uri, relation))
            more = f" (top {note['kept']} of {note['found']} by pagerank)" if note else ''
            lines.append(f"  {relation}{more}: {objects}")
        return lines

    seed_uris = [s['uri'] for s in seeds]
    out = ['# Matched parts'] + [line for uri in seed_uris for line in block(uri)]
    others = [uri for uri in nodes if uri not in seed_uris and uri in by_subject]
    if others:
        out += ['', '# Related nodes'] + [line for uri in others for line in block(uri)]
    return '\n'.join(out)
