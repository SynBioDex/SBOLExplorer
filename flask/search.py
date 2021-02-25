from elasticsearch_dsl import Search
from xml.etree import ElementTree
import re
import requests
import utils
import query
import sequencesearch
import cluster

def search_es(es_query):
    """
    String query for ES searches
    
    Arguments:
        es_query {string} -- String to search for
    
    Returns:
        List -- List of all search results
    """
    body = {
        'query': {
            'function_score': {
                'query': {
                    'multi_match': {
                        'query': es_query,
                        'fields': [
                            'subject',
                            'displayId^3', # caret indicates displayId is 3 times as important during search
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
                        'source': "_score * Math.log(doc['pagerank'].value + 1)" # Math.log is a natural log
                    }
                }
            }
        },
        'from': 0,
        'size': 10000
    }
    return utils.get_es().search(index=utils.get_config()['elasticsearch_index_name'], body=body)


def empty_search_es(offset, limit, allowed_graphs):
    """
    Empty string search based solely on pagerank
    
    Arguments:
        offset {int} -- Offset for search results
        limit {int} -- Size of search
        allowed_graphs {List} -- List of allowed graphs to search on
    
    Returns:
        List -- List of search results
    """
    if len(allowed_graphs) == 1:
        query = { 'term': { 'graph': allowed_graphs[0] } }
    else:
        query = { 'terms': { 'graph': allowed_graphs } }

    body = {
        'query': {
            'function_score': {
                'query': query,
                'script_score': {
                    'script': {
                        'source': "_score * Math.log(doc['pagerank'].value + 1)" # Math.log is a natural log
                    }
                }
            }
        },
        'size': limit
    }
    
    # Initial ES query
    initial_search = utils.get_es().search(index=utils.get_config()['elasticsearch_index_name'], body=body, scroll='5s')

    # Store inital parts
    parts = initial_search

    # Get scroll ID for search
    scroll_id = initial_search['_scroll_id']

    # We will limit the size to 30k results
    size = 0

    # While the scroll search still returns results and we are below 30k total parts:
    while (len(initial_search['hits']['hits']) and size < 30000):
        initial_search = utils.get_es().scroll(scroll_id=scroll_id, scroll='5s')
        # Save ID of latest scroll search in case ID changed
        scroll_id = initial_search['_scroll_id']

        # Append new parts to list of parts
        parts['hits']['hits'].extend(initial_search['hits']['hits'])
        # Increment counter of parts
        size = size + len(initial_search['hits']['hits'])

    # Clear scroll
    utils.get_es().clear_scroll(scroll_id)

    # Get all parts between from and limit
    parts['hits']['hits'] = parts['hits']['hits'][offset:(offset+limit+1)]

    return parts


def extract_query(sparql_query):
    """
    Extracts information from SPARQL query to be passed to ES
    
    Arguments:
        sparql_query {string} -- SPARQL query
    
    Returns:
        List -- List of information extracted
    """
    _from = ''
    if is_count_query(sparql_query):
        _from_search = re.search(r'''SELECT \(count\(distinct \?subject\) as \?tempcount\)\s*(.*)\s*WHERE {''', sparql_query)
    else:
        _from_search = re.search(r'''\?type\n(.*)\s*WHERE {''', sparql_query)
    if _from_search:
        _from = _from_search.group(1).strip()

    criteria = ''
    criteria_search = re.search(r'''WHERE {\s*(.*)\s*\?subject a \?type \.''', sparql_query)
    if criteria_search:
        criteria = criteria_search.group(1).strip()

    offset = 0
    offset_search = re.search(r'''OFFSET (\d*)''', sparql_query)
    if offset_search:
        offset = int(offset_search.group(1))

    limit = 50
    limit_search = re.search(r'''LIMIT (\d*)''', sparql_query)
    if limit_search:
        limit = int(limit_search.group(1))

    sequence = ''
    sequence_search = re.search(r'''\s*\?subject sbol2:sequence \?seq \.\s*\?seq sbol2:elements \"([a-zA-Z]*)\"''', sparql_query)
    if sequence_search:
        sequence = sequence_search.group(1)

    flags = {}
    flag_search = re.finditer(r'''# flag_([a-zA-Z0-9._]*): ([a-zA-Z0-9./-_]*)''', sparql_query)
    for flag in flag_search:
        flags[flag.group(1)] = flag.group(2)

    extract_keyword_re = re.compile(r'''CONTAINS\(lcase\(\?displayId\), lcase\('([^']*)'\)\)''')
    keywords = []
    for keyword in re.findall(extract_keyword_re, criteria):
        keywords.append(keyword)
    es_query = ' '.join(keywords).strip()

    return es_query, _from, criteria, offset, limit, sequence, flags


def extract_allowed_graphs(_from, default_graph_uri):
    """
    Extracts the allowed graphs to search over
    
    Arguments:
        _from {string} -- Graph where search originated
        default_graph_uri {string} -- The default graph URI pulled from SBH
    
    Returns:
        List -- List of allowed graphs
    """
    allowed_graphs = []

    if utils.get_config()['distributed_search']:
        instances = utils.get_wor()
        for instance in instances:
            allowed_graphs.append(instance['instanceUrl'] + '/public')

    if _from == '':
        allowed_graphs.append(default_graph_uri)
        return allowed_graphs
    else:
        for graph in _from.split('FROM'):
            graph = graph.strip()
            graph = graph[1:len(graph) - 1]

            if graph != '':
                allowed_graphs.append(graph)

        return allowed_graphs


def is_count_query(sparql_query):
    return 'SELECT (count(distinct' in sparql_query


def create_response(count, bindings, return_count):
    """
    Creates response to be sent back to SBH
    
    Arguments:
        count {int} -- ?
        bindings {Dict} -- The bindings
        return_count {int} -- ?
    
    Returns:
        ? -- ?
    """
    if return_count:
        response = {"head":{"link":[],"vars":["count"]},"results":{"distinct":False,"ordered":True,"bindings":[{"count":{"type":"typed-literal","datatype":"http://www.w3.org/2001/XMLSchema#integer","value":"10"}}]}}
        response['results']['bindings'][0]['count']['value'] = str(count)
    else:
        response = {"head":{"link":[],"vars":["subject","displayId","version","name","description","type","percentMatch","strandAlignment","CIGAR"]},"results":{"distinct":False,"ordered":True,"bindings":[]}}
        response['results']['bindings'] = bindings

    return response


def create_binding(subject, displayId, version, name, description, _type, role, sbol_type, order_by, percentMatch = -1, strandAlignment = 'N/A', CIGAR = 'N/A'):
    """
    Creates bindings to be sent to SBH
    
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

    if subject is not None:
        binding["subject"] = {
            "type": "uri",
            "datatype": "http://www.w3.org/2001/XMLSchema#uri",
            "value": subject
        }
        
    if displayId is not None:
        binding["displayId"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#string",
            "value": displayId
        }

    if version is not None:
        binding["version"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#string",
            "value": version
        }

    if name is not None:
        binding["name"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#string",
            "value": name
        }

    if description is not None:
        binding["description"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#string",
            "value": description
        }

    if _type is not None:
        binding["type"] = {
            "type": "uri",
            "datatype": "http://www.w3.org/2001/XMLSchema#uri",
            "value": _type
        }

    if role is not None:
        binding["role"] = {
            "type": "uri",
            "datatype": "http://www.w3.org/2001/XMLSchema#uri",
            "value": role
        }

    if sbol_type is not None:
        binding["sboltype"] = {
            "type": "uri",
            "datatype": "http://www.w3.org/2001/XMLSchema#uri",
            "value": sbol_type
        }

    if order_by is not None:
        binding["order_by"] = order_by

    if percentMatch != -1:
        binding["percentMatch"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#string",
            "value": str(percentMatch)
        }

    if strandAlignment != 'N/A':
        binding["strandAlignment"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#string",
            "value": strandAlignment
        }

    if CIGAR != 'N/A':
        binding["CIGAR"] = {
            "type": "literal",
            "datatype": "http://www.w3.org/2001/XMLSchema#string",
            "value": CIGAR
        }

    return binding


def create_bindings(es_response, clusters, allowed_graphs, allowed_subjects = None):
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
    bindings = []
    cluster_duplicates = set()
    hits = (h for h in es_response['hits']['hits'] if h['_source'].get('role') is None or 'http://wiki.synbiohub.org' in h['_source'].get('role'))
    for hit in hits:
        _source = hit['_source']
        _score = hit['_score']
        subject = _source['subject']

        if allowed_subjects is not None and subject not in allowed_subjects:
            continue

        if _source.get('graph') not in allowed_graphs:
            continue
        
        if subject in cluster_duplicates:
            _score = _score / 2.0
        elif subject in clusters:
            cluster_duplicates.update(clusters[subject])

        if _source.get('type') is not None and'http://sbols.org/v2#Sequence' in _source.get('type'):
            _score = _score / 10.0

        binding = create_binding(subject, 
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


def create_criteria_bindings(criteria_response, uri2rank, sequence_search = False, ucTableName = ''):
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

        if subject not in uri2rank:
            pagerank = 1
        else:
            pagerank = uri2rank[subject]

        if part.get('type') is not None and 'http://sbols.org/v2#Sequence' in part.get('type'):
            pagerank = pagerank / 10.0

        if sequence_search:
            pagerank = pagerank * (float(get_percent_match(part.get('subject'), ucTableName)) / 100)
            binding = create_binding(part.get('subject'),
                    part.get('displayId'),
                    part.get('version'),
                    part.get('name'),
                    part.get('description'),
                    part.get('type'),
                    part.get('role'),
                    part.get('sboltype'),
                    pagerank, 
                    get_percent_match(part.get('subject'), ucTableName), 
                    get_strand_alignment(part.get('subject'), ucTableName), 
                    get_cigar_data(part.get('subject'), ucTableName))

        else:
            binding = create_binding(part.get('subject'),
                    part.get('displayId'),
                    part.get('version'),
                    part.get('name'),
                    part.get('description'),
                    part.get('type'),
                    part.get('role'),
                    part.get('sboltype'),
                    pagerank)

        bindings.append(binding)
    return bindings


def get_allowed_subjects(criteria_response):
    subjects = set()

    for part in criteria_response:
        subjects.add(part['subject'])
    
    return subjects


def create_similar_criteria(criteria, clusters):
    subject = criteria.split(':', 1)[1]
	
    if subject not in clusters or not clusters[subject]:
        return 'FILTER (?subject != ?subject)'

    return 'FILTER (' + ' || '.join(['?subject = <' + duplicate + '>' for duplicate in clusters[subject]]) + ')'

def create_sequence_criteria(criteria, uris):
    return 'FILTER (' + ' || '.join(['?subject = <' + uri + '>' for uri in uris]) + ')'

def parse_allowed_graphs(allowed_graphs):
    result = ''
    for allowed_graph in allowed_graphs:
        if allowed_graph is not None:
            result += 'FROM <' + allowed_graph + '> '
    return result

def search(sparql_query, uri2rank, clusters, default_graph_uri):
    es_query, _from, criteria, offset, limit, sequence, flags = extract_query(sparql_query)

    if criteria.strip() == 'FILTER ()':
        criteria = ''

    filterless_criteria = re.sub('FILTER .*', '', criteria).strip()
    allowed_graphs = extract_allowed_graphs(_from, default_graph_uri)
    _from = parse_allowed_graphs(allowed_graphs)

    if 'file_search' in flags:
        filename = str(flags['file_search'])
        results = sequencesearch.sequence_search(flags, filename)
        sequence_criteria = create_sequence_criteria(criteria, results)
        criteria_response = query.query_parts(_from, sequence_criteria) 
        bindings = create_criteria_bindings(criteria_response, uri2rank, True, filename[:-4] + '.uc')

    elif len(sequence.strip()) > 0:
        # send sequence search to search.py
        temp_filename = sequencesearch.write_to_temp(sequence)
        results = sequencesearch.sequence_search(flags, temp_filename)
        
        # return new clusters here
        #pass into func -> queryparts create_sequence_criteria
        sequence_criteria = create_sequence_criteria(criteria, results)
        criteria_response = query.query_parts(_from, sequence_criteria) 
        bindings = create_criteria_bindings(criteria_response, uri2rank, True, temp_filename[:-4] + '.uc')

    elif 'SIMILAR' in criteria:
        # SIMILAR
        similar_criteria = create_similar_criteria(criteria, clusters)
        criteria_response = query.query_parts(_from, similar_criteria) 
        bindings = create_criteria_bindings(criteria_response, uri2rank)

    elif 'USES' in criteria or 'TWINS' in criteria or (es_query == '' and filterless_criteria != ''):
        # USES or TWINS or pure advanced search
        criteria_response = query.query_parts(_from, criteria)
        bindings = create_criteria_bindings(criteria_response, uri2rank)

    elif es_query == '' and filterless_criteria == '':
        # empty search
        es_response = empty_search_es(offset, limit, allowed_graphs)
        bindings = create_bindings(es_response, clusters, allowed_graphs)
        bindings.sort(key = lambda binding: binding['order_by'], reverse = True)
        return create_response(es_response['hits']['total'], bindings, is_count_query(sparql_query))

    else:
        es_response = search_es(es_query)

        if filterless_criteria == '':
            # pure string search
            bindings = create_bindings(es_response, clusters, allowed_graphs)

        else:
            # advanced search and string search
            criteria_response = query.query_parts(_from, filterless_criteria)
            allowed_subjects = get_allowed_subjects(criteria_response)
            bindings = create_bindings(es_response, clusters, allowed_graphs, allowed_subjects)

    bindings.sort(key = lambda binding: binding['order_by'], reverse = True)

    return create_response(len(bindings), bindings[offset:offset + limit], is_count_query(sparql_query))

def get_percent_match(uri, ucTableName):
    with open(ucTableName, 'r') as read:
        uc_reader = read.read()
        lines = uc_reader.splitlines()

        for line in lines:
            line = line.split()
            if line[9] == uri:
                return line[3]

        return -1

def get_strand_alignment(uri, ucTableName):
    with open(ucTableName, 'r') as read:
        uc_reader = read.read()
        lines = uc_reader.splitlines()

        for line in lines:
            line = line.split()
            if line[9] == uri:
                return line[4]

        return 'N/A'

def get_cigar_data(uri, ucTableName):
    with open(ucTableName, 'r') as read:
        uc_reader = read.read()
        lines = uc_reader.splitlines()

        for line in lines:
            line = line.split()
            if line[9] == uri:
                return line[7]

        return 'N/A'
