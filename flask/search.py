import re
from math import log1p
from typing import List, Dict, Tuple, Optional
import query
import sequencesearch
from wor_client import WORClient
from typesenseManager import TypesenseManager
from configManager import ConfigManager
from logger import Logger

config_manager = ConfigManager()
typesense_manager = TypesenseManager(config_manager)
logger_ = Logger()


TEXT_QUERY_BY = 'subject,displayId,version,name,description,type,keywords'
TEXT_QUERY_BY_WEIGHTS = '1,3,1,1,1,1,1'
TEXT_SORT_BY = '_text_match(buckets: 10):desc,pagerank:desc'
MAX_RESULTS = 10000
TYPESENSE_PAGE_SIZE = 250

# --- Weighted-sum re-rank for the /search string endpoint ---
# Validated on the Phase 0 eval harness (see evaluation/): beats the old raw
# _text_match(buckets:10) ordering, which buried canonical high-pagerank parts
# (e.g. rbs -> BBa_B0034 went from rank ~36 to rank 1). Tuned config below.
RERANK_POOL_SORT = '_text_match(buckets: 1):desc,pagerank:desc'  # pagerank-rich candidate pool
RERANK_ALPHA = 0.3          # text vs pagerank weight (0 = pure pagerank, 1 = pure text)
RERANK_EXACT_BOOST = 0.5    # lift for exact name/displayId matches (standard part over user construct)
RERANK_PR_SCALE = 1e6       # log-compression scale for the heavy-tailed pagerank


def _backtick_list(values):
    return ','.join(f'`{v}`' for v in values)


def _search_paginated(params, max_total=MAX_RESULTS):
    """Fetches up to max_total hits by paginating Typesense calls."""
    collection_name = config_manager.get_typesense_collection_name()
    collection = typesense_manager.get_client().collections[collection_name]

    all_hits = []
    found = 0
    page = 1
    while len(all_hits) < max_total:
        page_size = min(TYPESENSE_PAGE_SIZE, max_total - len(all_hits))
        page_params = {**params, 'page': page, 'per_page': page_size}
        response = collection.documents.search(page_params)
        found = response.get('found', 0)
        hits = response.get('hits', [])
        if not hits:
            break
        all_hits.extend(hits)
        if len(hits) < page_size:
            break
        page += 1

    return {'hits': all_hits[:max_total], 'found': found}
wor_client_ = WORClient()

# Compile regex patterns
FROM_COUNT_PATTERN = re.compile(r'SELECT \(count\(distinct \?subject\) as \?tempcount\)\s*(.*)\s*WHERE {')
FROM_NORMAL_PATTERN = re.compile(r'\?type\n(.*)\s*WHERE {')
CRITERIA_PATTERN = re.compile(r'WHERE {\s*(.*)\s*\?subject a \?type \.')
OFFSET_PATTERN = re.compile(r'OFFSET (\d+)')
LIMIT_PATTERN = re.compile(r'LIMIT (\d+)')
SEQUENCE_PATTERN = re.compile(r'\s*\?subject sbol2:sequence \?seq \.\s*\?seq sbol2:elements \"([a-zA-Z]*)\"')
FLAG_PATTERN = re.compile(r'# flag_([a-zA-Z0-9._]*): ([a-zA-Z0-9./-_]*)')
KEYWORD_PATTERN = re.compile(r"CONTAINS\(lcase\(\?displayId\), lcase\('([^']*)'\)\)")


def extract_offset(sparql_query):
    offset_match = OFFSET_PATTERN.search(sparql_query)
    return int(offset_match.group(1)) if offset_match else 0

def search_es(es_query: str) -> Dict:
    """
    String query for Typesense text search with pagerank tie-breaking.
    """
    params = {
        'q': es_query,
        'query_by': TEXT_QUERY_BY,
        'query_by_weights': TEXT_QUERY_BY_WEIGHTS,
        'num_typos': '2',
        'sort_by': TEXT_SORT_BY,
    }
    try:
        return _search_paginated(params)
    except:
        logger_.log("search_es(es_query: str)")
        raise

def _weighted_rerank(hits: List[Dict], query: str) -> List[Dict]:
    """
    Re-rank Typesense hits by  alpha*norm_text + (1-alpha)*norm_pr + boost*exact.

    Mirrors evaluation/rankers.ranker_weighted_sum (validated to beat the old
    _text_match-bucket ordering on the Phase 0 gold set). Hit objects are
    preserved and only reordered, so downstream consumers are unaffected.
    """
    if not hits:
        return hits
    max_tm = max(h.get('text_match', 0) for h in hits) or 1
    pr_signals = [log1p((h['document'].get('pagerank', 0) or 0) * RERANK_PR_SCALE) for h in hits]
    max_pr = max(pr_signals) or 1
    q_lower = query.strip().lower()

    scored = []
    for h, pr_sig in zip(hits, pr_signals):
        doc = h['document']
        norm_text = h.get('text_match', 0) / max_tm
        norm_pr = pr_sig / max_pr
        name = (doc.get('name') or '').strip().lower()
        did = (doc.get('displayId') or '').strip().lower()
        exact = 1.0 if q_lower in (name, did) else 0.0
        score = RERANK_ALPHA * norm_text + (1 - RERANK_ALPHA) * norm_pr + RERANK_EXACT_BOOST * exact
        scored.append((score, h))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in scored]

def search_es_ranked(es_query: str) -> Dict:
    """
    String search for the /search endpoint: fetch a pagerank-rich candidate pool,
    then re-rank with the weighted-sum scorer. Replaces the old reliance on raw
    Typesense _text_match bucketing (search_es), which buried canonical parts.
    Leaves search_es untouched (still used by the SPARQL path, which re-sorts).
    """
    params = {
        'q': es_query,
        'query_by': TEXT_QUERY_BY,
        'query_by_weights': TEXT_QUERY_BY_WEIGHTS,
        'num_typos': '2',
        'sort_by': RERANK_POOL_SORT,
    }
    try:
        response = _search_paginated(params)
        response['hits'] = _weighted_rerank(response.get('hits', []), es_query)
        return response
    except:
        logger_.log("search_es_ranked(es_query: str)")
        raise

def empty_search_es(offset: int, limit: int, allowed_graphs: List[str]) -> Dict:
    """
    Empty search filtered by allowed graphs, sorted purely by pagerank.
    """
    if len(allowed_graphs) == 1:
        filter_by = f'graph:=`{allowed_graphs[0]}`'
    else:
        filter_by = f'graph:=[{_backtick_list(allowed_graphs)}]'

    safe_limit = max(1, min(TYPESENSE_PAGE_SIZE, limit))
    page = (offset // safe_limit) + 1 if safe_limit > 0 else 1

    params = {
        'q': '*',
        'filter_by': filter_by,
        'sort_by': 'pagerank:desc',
        'page': page,
        'per_page': safe_limit,
    }
    try:
        collection_name = config_manager.get_typesense_collection_name()
        return typesense_manager.get_client().collections[collection_name].documents.search(params)
    except:
        logger_.log("empty_search_es(offset: int, limit: int, allowed_graphs: List[str])")
        raise

def search_es_allowed_subjects(es_query: str, allowed_subjects: List[str]) -> Dict:
    """
    Text search limited to a set of allowed subject URIs.
    """
    params = {
        'q': es_query,
        'query_by': TEXT_QUERY_BY,
        'query_by_weights': TEXT_QUERY_BY_WEIGHTS,
        'num_typos': '2',
        'filter_by': f'id:=[{_backtick_list(allowed_subjects)}]',
        'sort_by': TEXT_SORT_BY,
    }
    try:
        return _search_paginated(params)
    except:
        logger_.log("search_es_allowed_subjects(es_query: str, allowed_subjects: List[str])")
        raise

def search_es_allowed_subjects_empty_string(allowed_subjects: List[str]):
    """
    Search limited purely to allowed subject URIs, sorted by pagerank.
    """
    params = {
        'q': '*',
        'filter_by': f'id:=[{_backtick_list(allowed_subjects)}]',
        'sort_by': 'pagerank:desc',
    }
    try:
        return _search_paginated(params)
    except:
        logger_.log("search_es_allowed_subjects_empty_string")
        raise
def parse_sparql_query(sparql_query, is_count_query):
    # Find FROM clause
    _from_search = FROM_COUNT_PATTERN.search(sparql_query) if is_count_query else FROM_NORMAL_PATTERN.search(sparql_query)
    _from = _from_search.group(1).strip() if _from_search else ''

    # Find criteria
    criteria_search = CRITERIA_PATTERN.search(sparql_query)
    criteria = criteria_search.group(1).strip() if criteria_search else ''
    
    # Find offset
    offset_match = OFFSET_PATTERN.search(sparql_query)
    offset = int(offset_match.group(1)) if offset_match else 0

    # Find limit
    limit_match = LIMIT_PATTERN.search(sparql_query)
    limit = int(limit_match.group(1)) if limit_match else 50

    # Find sequence
    sequence_match = SEQUENCE_PATTERN.search(sparql_query)
    sequence = sequence_match.group(1) if sequence_match else ''
    
    # Extract flags
    flags = {match.group(1): match.group(2) for match in FLAG_PATTERN.finditer(sparql_query)}

    # Extract keywords
    keywords = KEYWORD_PATTERN.findall(criteria)

    # Construct es_query
    es_query = ' '.join(keywords).strip()
    #print("Hello es_query: ", es_query)
    
    return es_query, _from, criteria, offset, limit, sequence, flags

def extract_query(sparql_query):
    """
    Extracts information from SPARQL query to be passed to ES
    
    Arguments:
        sparql_query {string} -- SPARQL query
    
    Returns:
        List -- List of information extracted
    """
    return parse_sparql_query(sparql_query, is_count_query(sparql_query))

def extract_allowed_graphs(_from: str, default_graph_uri: str) -> List[str]:
    """
    Extracts the allowed graphs to search over.
    Arguments:
        _from {string} -- Graph where search originated
        default_graph_uri {string} -- The default graph URI pulled from SBH
    
    Returns:
        List -- List of allowed graphs
    """
    allowed_graphs = [default_graph_uri] if not _from else [graph.strip()[1:-1] for graph in _from.split('FROM') if graph.strip()[1:-1]]
    if config_manager.load_config()['distributed_search']:
        allowed_graphs.extend(instance['instanceUrl'] + '/public' for instance in wor_client_.get_wor_instance())
    return allowed_graphs

def is_count_query(sparql_query: str) -> bool:
    return 'SELECT (count(distinct' in sparql_query

def create_response(count: int, bindings: List[Dict], return_count: bool) -> Dict:
    """
    Creates response to be sent back to SBH.
    
    Arguments:
        count {int} -- ?
        bindings {Dict} -- The bindings
        return_count {int} -- ?
    
    Returns:
        ? -- ?
    """
    if return_count:
        return {
            "head": {"link": [], "vars": ["count"]},
            "results": {
                "distinct": False,
                "ordered": True,
                "bindings": [{"count": {
                    "type": "typed-literal",
                    "datatype": "http://www.w3.org/2001/XMLSchema#integer",
                    "value": str(count)
                    }
                }]
            }
        }
    return {
        "head": {
            "link": [],
            "vars": ["subject", "displayId", "version", "name", "description", "type", "percentMatch", "strandAlignment", "CIGAR"]
        },
        "results": {"distinct": False, "ordered": True, "bindings": bindings}
    }

def create_binding(subject: str, displayId: Optional[str], version: Optional[int], name: Optional[str], description: Optional[str],
                   _type: Optional[str], role: Optional[str], sbol_type: Optional[str], order_by: Optional[float],
                   percentMatch: float = -1, strandAlignment: str = 'N/A', CIGAR: str = 'N/A') -> Dict:
    """
    Creates bindings to be sent to SBH.
        Arguments:
        subject {string} -- URI of part
        displayId {string} -- DisplayId of part
        version {int} -- Version of part
        name {string} -- Name of part
        description {string} -- Description of part
        _type {string} -- SBOL type of part
        role {string} -- S.O. role of part
        order_by {?} -- ?
    
    Keyword Arguments:
        percentMatch {number} -- Percent match of query part to the target part (default: {-1})
        strandAlignment {str} -- Strand alignment of the query part relatve to the target part (default: {'N/A'})
        CIGAR {str} -- Alignment of query part relative to the target part (default: {'N/A'})
    
    Returns:
        Dict -- Part and its information
    
    """
    binding = {}
    attributes = {
        "subject": subject,
        "displayId": displayId,
        "version": str(version) if version is not None else None,
        "name": name,
        "description": description,
        "type": _type,
        "role": role,
        "sboltype": sbol_type,
        "order_by": order_by,
        "percentMatch": str(percentMatch) if percentMatch != -1 else None,
        "strandAlignment": strandAlignment if strandAlignment != 'N/A' else None,
        "CIGAR": CIGAR if CIGAR != 'N/A' else None
    }
    for key, value in attributes.items():
        if value is not None:
            datatype = "http://www.w3.org/2001/XMLSchema#uri" if key in ["subject", "type", "role", "sboltype"] else "http://www.w3.org/2001/XMLSchema#string"
            ltype = "uri" if key in ["subject", "type", "role", "sboltype"] else "literal"
            binding[key] = {"type": ltype, "value": str(value), "datatype": datatype} if not key=="order_by" else order_by
    return binding

def create_bindings(es_response, clusters, allowed_graphs, allowed_subjects=None):
    """
    Creates the mass binding consisting of all parts in the search
    
    Arguments:
        es_response {Dict} -- List of all responses from ES
        clusters {?} -- ?
        allowed_graphs {List} -- List of allowed graphs
    
    Keyword Arguments:
        allowed_subjects {List} -- List of allowed subjects (default: {None})
    
    Returns:
        Dict -- All parts and their corresponding information
    """
    if es_response is None or 'hits' not in es_response:
        logger_.log("[ERROR] Typesense response is None or malformed.")
        return []

    bindings = []
    cluster_duplicates = set()

    allowed_subjects_set = set(allowed_subjects) if allowed_subjects else None

    for hit in es_response['hits']:
        _source = hit['document']
        _score = hit.get('text_match', 0)
        subject = _source['subject']

        if allowed_subjects_set and subject not in allowed_subjects_set:
            continue

        graph = _source.get('graph')
        if graph not in allowed_graphs:
            continue

        if subject in cluster_duplicates:
            _score /= 2.0
        elif subject in clusters:
            cluster_duplicates.update(clusters[subject])

        if _source.get('type') is not None and 'http://sbols.org/v2#Sequence' in _source.get('type'):
            _score /= 10.0

        binding = create_binding(
            subject,
            _source.get('displayId'),
            _source.get('version'),
            _source.get('name'),
            _source.get('description'),
            _source.get('type'),
            _source.get('role'),
            _source.get('sboltype'),
            _score
        )
        bindings.append(binding)

    return bindings

def load_uc_index(ucTableName):
    """
    Loads the UC-index file into an in-memory index

    Arguments:
        ucTableName -- Name of UC-index file

    Returns:
        Dict -- UC-index file
    """
    index = {}

    with open(ucTableName, 'r') as file:
        for line in file:
            parts = line.split()
            if parts[0] == 'H':
                index[parts[9]] = (parts[3], parts[4], parts[7])
    return index

def create_criteria_bindings(criteria_response, uri2rank, sequence_search=False, ucTableName=''):
    """
    Creates binding for all non-string or non-empty searches
    
    Arguments:
        criteria_response {Dict} -- List of parts and their information
        uri2rank {Dict} -- Pagerank information
    
    Keyword Arguments:
        sequence_search {bool} -- Whether to sequence search (default: {False})
        ucTableName {str} -- Name of UC table in Explorer's filesystem (default: {''})
    
    Returns:
        Dict -- Binding of parts
    """
    uc_index = load_uc_index(ucTableName) if sequence_search else {}

    bindings = []
    parts = (p for p in criteria_response if p.get('role') is None or 'http://wiki.synbiohub.org' in p.get('role'))
    for part in parts:
        subject = part.get('subject')
        pagerank = uri2rank.get(subject, 1)

        if 'http://sbols.org/v2#Sequence' in part.get('type', ''):
            pagerank /= 10.0

        if sequence_search:
            pct, strand, cigar = uc_index.get(subject, ('N/A', 'N/A', 'N/A'))
            percent_match = float(pct) / 100 if pct != 'N/A' else 0.0
            binding = create_binding(
                subject,
                part.get('displayId'),
                part.get('version'),
                part.get('name'),
                part.get('description'),
                part.get('type'),
                part.get('role'),
                part.get('sboltype'),
                pagerank * percent_match,
                percent_match,
                strand,
                cigar
            )
        else:
            binding = create_binding(
                subject,
                part.get('displayId'),
                part.get('version'),
                part.get('name'),
                part.get('description'),
                part.get('type'),
                part.get('role'),
                part.get('sboltype'),
                pagerank
            )

        bindings.append(binding)

    return bindings

def get_allowed_subjects(criteria_response):
    """
    Filters the allowed subjects from the unfiltered list from Virtuoso
    Args:
        criteria_response: Unfiltered response from Virtuoso

    Returns: Parts the user is allowed to see

    """
    return {part['subject'] for part in criteria_response}

def create_similar_criteria(criteria, clusters):
    
    """
    Adds filter to query to be sent to Virtuoso
    Args:
        criteria: Criteria from SynBioHub
        clusters: Cluster of parts

    Returns: String containing a SPARQL filter

    """
    subject = criteria.split(':', 1)[1]

    if subject not in clusters or not clusters[subject]:
        return 'FILTER (?subject != ?subject)'

    filters = ' || '.join(f'?subject = <{duplicate}>' for duplicate in clusters[subject])
    return f'FILTER ({filters})'


def create_sequence_criteria(criteria, uris):
    """
    Adds filter to query to be sent to Virtuoso
    Args:
        criteria: Criteria from SynBioHub
        uris: URI's to be filtered

    Returns: String containing a SPARQL filter

    """
    if not uris:
        return ''
    filters = ' || '.join(f'?subject = <{uri}>' for uri in uris)
    return f'FILTER ({filters})'


def parse_allowed_graphs(allowed_graphs):
    """
    Grabs allowed graphs for user
    Args:
        allowed_graphs: Allowed graphs

    Returns: List of allowed graphs

    """
    return ' '.join(f'FROM <{graph}>' for graph in allowed_graphs if graph)

def search(sparql_query, uri2rank, clusters, default_graph_uri):
    """
    Main search method.
    Args:
        sparql_query: SPARQL query to be sent to Virtuoso
        uri2rank: List of pageranks for each URI
        clusters: Clusters of parts
        default_graph_uri: The default graph URI

    Returns: List of parts (JSON)

    """
    es_query, _from, criteria, offset, limit, sequence, flags = extract_query(sparql_query)
    
    if criteria.strip() == 'FILTER ()':
        criteria = ''

    filterless_criteria = re.sub('FILTER .*', '', criteria).strip()
    allowed_graphs = extract_allowed_graphs(_from, default_graph_uri)
    _from = parse_allowed_graphs(allowed_graphs)

    if 'file_search' in flags:
        filename = str(flags['file_search'])
        results = sequencesearch.sequence_search(flags, filename)
        allowed_uris = filter_sequence_search_subjects(_from, results)
        criteria_response = query.query_parts(_from)
        # Filter searches by URI to hide private parts here instead of on Virtuoso
        criteria_response_filtered = [c for c in criteria_response if any(f in c.get('subject', '') for f in allowed_uris)]
        bindings = create_criteria_bindings(criteria_response_filtered, uri2rank, True, filename[:-4] + '.uc')

    elif sequence.strip():
        # send sequence search to search.py
        temp_filename = sequencesearch.write_to_temp(sequence)
        results = sequencesearch.sequence_search(flags, temp_filename)
        allowed_uris = filter_sequence_search_subjects(_from, results)
        criteria_response = query.query_parts(_from)
        criteria_response_filtered = [c for c in criteria_response if any(f in c.get('subject', '') for f in allowed_uris)]
        bindings = create_criteria_bindings(criteria_response_filtered, uri2rank, True, temp_filename[:-4] + '.uc')

    elif 'SIMILAR' in criteria:
        # SIMILAR
        similar_criteria = create_similar_criteria(criteria, clusters)
        criteria_response = query.query_parts(_from, similar_criteria)
        bindings = create_criteria_bindings(criteria_response, uri2rank)

    elif 'USES' in criteria or 'TWINS' in criteria:
        # USES or TWINS or pure advanced search
        criteria_response = query.query_parts(_from, criteria)
        bindings = create_criteria_bindings(criteria_response, uri2rank)

    elif es_query == '' and not filterless_criteria:
        # empty search
        es_response = empty_search_es(offset, limit, allowed_graphs)
        bindings = create_bindings(es_response, clusters, allowed_graphs)
        bindings.sort(key=lambda b: b['order_by'], reverse=True)
        return create_response(es_response.get('found', len(bindings)), bindings, is_count_query(sparql_query))

    else:
        if not filterless_criteria:
            es_response = search_es(es_query)
            # pure string search
            bindings = create_bindings(es_response, clusters, allowed_graphs)
        else:
            # advanced search and string search
            criteria_response = query.query_parts(_from, filterless_criteria)
            allowed_subjects = get_allowed_subjects(criteria_response)

            es_allowed_subject = (search_es_allowed_subjects_empty_string(allowed_subjects)
                                  if es_query == '' 
                                  else search_es_allowed_subjects(es_query, allowed_subjects))

            bindings = create_bindings(es_allowed_subject, clusters, allowed_graphs, allowed_subjects)
            logger_.log('Advanced string search complete.')

    bindings.sort(key=lambda b: b['order_by'], reverse=True)
    return create_response(len(bindings), bindings[offset:offset + limit], is_count_query(sparql_query))


def filter_sequence_search_subjects(_from, uris):
    """
    Adds filters to SPARQL based on the allowed graphs and URI's from sequence search
    
    [description]
    
    Arguments:
        _from {list} -- List of allowed graphs
        uris {list} -- List of URI's from sequence search
    """
    from_uris = set(re.findall(r"\<([A-Za-z0-9:\/.]+)\>*", _from))
    return [uri for uri in uris if any(f in uri for f in from_uris)]