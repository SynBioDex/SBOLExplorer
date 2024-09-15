import re
from typing import List, Dict, Tuple, Optional
import query
import sequencesearch
from wor_client import WORClient
from elasticsearchManager import ElasticsearchManager
from configManager import ConfigManager
from logger import Logger

config_manager = ConfigManager()
elasticsearch_manager = ElasticsearchManager(config_manager)
logger_ = Logger()
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
    String query for ES searches.
    """
    body = {
        'query': {
            'function_score': {
                'query': {
                    'multi_match': {
                        'query': es_query,
                        'fields': [
                            'subject',
                            'displayId^3',  # caret indicates displayId is 3 times as important during search
                            'version',
                            'name',
                            'description',
                            'type',
                            'keywords'
                        ],
                        'operator': 'or',
                        'fuzziness': 'AUTO'
                    }
                },
                'script_score': {
                    'script': {
                        'source': "_score * Math.log(doc['pagerank'].value + 1)"  # Math.log is a natural log
                    }
                }
            }
        },
        'from': 0,
        'size': 10000
    }
    try:
        return elasticsearch_manager.get_es().search(index=config_manager.load_config()['elasticsearch_index_name'], body=body)
    except:
        logger_.log("search_es(es_query: str)")
        raise

def empty_search_es(offset: int, limit: int, allowed_graphs: List[str]) -> Dict:
    """
    Empty string search based solely on pagerank.
    Arguments:
        offset {int} -- Offset for search results
        limit {int} -- Size of search
        allowed_graphs {List} -- List of allowed graphs to search on
    
    Returns:
        List -- List of search results
    """
    query = {'term': {'graph': allowed_graphs[0]}} if len(allowed_graphs) == 1 else {'terms': {'graph': allowed_graphs}}

    body = {
        'query': {
            'function_score': {
                'query': query,
                'script_score': {
                    'script': {
                        'source': "_score * Math.log(doc['pagerank'].value + 1)"  # Math.log is a natural log
                    }
                }
            }
        },
        'from': offset,
        'size': limit
    }
    try:
        return elasticsearch_manager.get_es().search(index=config_manager.load_config()['elasticsearch_index_name'], body=body)
    except:
        logger_.log("empty_search_es(offset: int, limit: int, allowed_graphs: List[str])")
        raise

def search_es_allowed_subjects(es_query: str, allowed_subjects: List[str]) -> Dict:
    """
    String query for ES searches limited to allowed parts.
    Arguments:
        es_query {string} -- String to search for
        allowed_subjects {list} - list of allowed subjects from Virtuoso
    
    Returns:
        List -- List of all search results
    """
    body = {
        'query': {
            'function_score': {
                'query': {
                    'bool': {
                        'must': [
                            {'multi_match': {
                                'query': es_query,
                                'fields': [
                                    'subject',
                                    'displayId^3',
                                    'version',
                                    'name',
                                    'description',
                                    'type',
                                    'keywords'
                                ],
                                'operator': 'or',
                                'fuzziness': 'AUTO'
                            }},
                            {'ids': {'values': list(allowed_subjects)}}
                        ]
                    }
                },
                'script_score': {
                    'script': {
                        'source': "_score * Math.log(doc['pagerank'].value + 1)"
                    }
                },
            },
        },
        'from': 0,
        'size': 10000
    }
    try:
        return elasticsearch_manager.get_es().search(index=config_manager.load_config()['elasticsearch_index_name'], body=body)
    except:
        logger_.log("search_es_allowed_subjects(es_query: str, allowed_subjects: List[str])")
        raise

def search_es_allowed_subjects_empty_string(allowed_subjects: List[str]):
    """
    ES search purely limited to allowed parts.
    Arguments:
        allowed_subjects {list} - list of allowed subjects from Virtuoso
    
    Returns:
        List -- List of all search results
    """
    body = {
        'query': {
            'function_score': {
                'query': {
                    'bool': {
                        'must': [
                            {'ids': {'values': list(allowed_subjects)}}
                        ]
                    }
                },
                'script_score': {
                    'script': {
                        'source': "_score * Math.log(doc['pagerank'].value + 1)"
                    }
                },
            },
        },
        'from': 0,
        'size': 10000
    }
    try:
        return elasticsearch_manager.get_es().search(index=config_manager.load_config()['elasticsearch_index_name'], body=body)
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
    if es_response is None or 'hits' not in es_response or 'hits' not in es_response['hits']:
        logger_.log("[ERROR] Elasticsearch response is None or malformed.")
        return []
    
    bindings = []
    cluster_duplicates = set()

    allowed_subjects_set = set(allowed_subjects) if allowed_subjects else None

    for hit in es_response['hits']['hits']:
        _source = hit['_source']
        _score = hit['_score']
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
    bindings = []
    parts = (p for p in criteria_response if p.get('role') is None or 'http://wiki.synbiohub.org' in p.get('role'))
    for part in parts:
        subject = part.get('subject')
        pagerank = uri2rank.get(subject, 1)

        if 'http://sbols.org/v2#Sequence' in part.get('type', ''):
            pagerank /= 10.0

        if sequence_search:
            percent_match = float(get_percent_match(subject, ucTableName)) / 100
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
                get_strand_alignment(subject, ucTableName),
                get_cigar_data(subject, ucTableName)
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
        return create_response(es_response['hits']['total'], bindings, is_count_query(sparql_query))

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

def get_info_from_uc_table(uri, ucTableName, column_index):
    with open(ucTableName, 'r') as file:
        for line in file:
            parts = line.split()
            if parts[9] == uri:
                return parts[column_index]
    return 'N/A'

def get_percent_match(uri, ucTableName):
    """
    Get percent match from USEARCH
    Args:
        uri: URI of part
        ucTableName: UClust table

    Returns: Percent match if available, else -1

    """
    return get_info_from_uc_table(uri, ucTableName, 3)


def get_strand_alignment(uri, ucTableName):
    """
    Gets the strand alignment (+ or -) of the part
    Args:
        uri: URI of the part
        ucTableName: UClust table

    Returns: + or -

    """
    return get_info_from_uc_table(uri, ucTableName, 4)

def get_cigar_data(uri, ucTableName):
    return get_info_from_uc_table(uri, ucTableName, 7)

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