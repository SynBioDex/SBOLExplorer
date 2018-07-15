from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from xml.etree import ElementTree
import re
import utils


es = Elasticsearch([utils.get_config()['elasticsearch_endpoint']], verify_certs=True)


def search_es(es_query):
    body = {
        'query': {
            'function_score': {
                'query': {
                    'multi_match': {
                        'query': es_query,
                        'fields': [
                            'subject',
                            'displayId', # TODO separate displayId into tokens in searchable field
                            'version',
                            'name',
                            'description',
                            'type'
                        ],
                        'operator': 'and',
                        'fuzziness': 'AUTO',
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
    return es.search(index='part', body=body)


def extract_query(sparql_query):
    _from = ''
    if is_count_query(sparql_query):
        _from_search = re.search(r'''SELECT \(count\(distinct \?subject\) as \?tempcount\)\s*(.*)\s*WHERE {''', sparql_query)
    else:
        _from_search = re.search(r'''(.*)\s*WHERE {''', sparql_query)
    if _from_search:
        _from = _from_search.group(1)

    criteria = ''
    criteria_search = re.search(r'''WHERE {\s*(.*)\s*\?subject a \?type \.''', sparql_query)
    if criteria_search:
        criteria = criteria_search.group(1)

    offset = 0
    offset_search = re.search(r'''OFFSET (\d*)''', sparql_query)
    if offset_search:
        offset = int(offset_search.group(1))

    limit = 50
    limit_search = re.search(r'''LIMIT (\d*)''', sparql_query)
    if limit_search:
        limit = int(limit_search.group(1))

    extract_keyword_re = re.compile(r'''CONTAINS\(lcase\(\?displayId\), lcase\('([^']*)'\)\)''')
    keywords = []
    for keyword in re.findall(extract_keyword_re, criteria):
        keywords.append(keyword)
    es_query = ' '.join(keywords)

    return es_query, _from, criteria, offset, limit


def is_count_query(sparql_query):
    return 'SELECT (count(distinct' in sparql_query


def create_count_response(count):
    count_response = {"head":{"link":[],"vars":["count"]},"results":{"distinct":False,"ordered":True,"bindings":[{"count":{"type":"typed-literal","datatype":"http://www.w3.org/2001/XMLSchema#integer","value":"10"}}]}}
    count_response['results']['bindings'][0]['count']['value'] = str(count)
    return count_response


def create_results_response(bindings):
    results_response = {"head":{"link":[],"vars":["subject","displayId","version","name","description","type"]},"results":{"distinct":False,"ordered":True,"bindings":[]}}
    results_response['results']['bindings'] = bindings
    return results_response


def create_binding(subject, displayId, version, name, description, _type, order_by):
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

    if order_by is not None:
        binding["order_by"] = order_by

    return binding


def create_bindings(es_response, clusters, allowed_subjects = None):
    bindings = []

    cluster_duplicates = set()

    for hit in es_response['hits']['hits']:
        _source = hit['_source']
        _score = hit['_score']
        subject = _source['subject']

        if allowed_subjects is not None and subject not in allowed_subjects:
            continue
        
        if subject in cluster_duplicates:
            _score = _score / 2.0
        elif subject in clusters:
            cluster_duplicates.update(clusters[subject])

        binding = create_binding(subject, 
                _source.get('displayId'),
                _source.get('version'),
                _source.get('name'),
                _source.get('description'),
                _source.get('type'),
                _score)

        bindings.append(binding)

    return bindings


def create_criteria_bindings(criteria_response, uri2rank):
    bindings = []

    parts = utils.create_parts(criteria_response)

    for part in parts:
        subject = part['subject']
        if subject not in uri2rank:
            pagerank = 1
        else:
            pagerank = uri2rank[subject]

        binding = create_binding(part.get('subject'),
                part.get('displayId'),
                part.get('version'),
                part.get('name'),
                part.get('description'),
                part.get('type'),
                pagerank)

        bindings.append(binding)

    return bindings


def query_criteria(_from, criteria):
    criteria_query = '''
    SELECT DISTINCT
        ?subject
        ?displayId
        ?version
        ?name
        ?description
        ?type
    ''' + _from + '''
    WHERE {
    ''' + criteria + '''

        ?subject a ?type .
        ?subject sbh:topLevel ?subject
        OPTIONAL { ?subject sbol2:displayId ?displayId . }
        OPTIONAL { ?subject sbol2:version ?version . }
        OPTIONAL { ?subject dcterms:title ?name . }
        OPTIONAL { ?subject dcterms:description ?description . }
    } 
    '''

    return utils.memoized_query_sparql(criteria_query)


def get_allowed_subjects(criteria_response):
    subjects = set()
    
    ns = {'sparql_results': 'http://www.w3.org/2005/sparql-results#'}
    
    root = ElementTree.fromstring(criteria_response)
    results = root.find('sparql_results:results', ns)

    for result in results.findall('sparql_results:result', ns):
        bindings = result.findall('sparql_results:binding', ns)

        for binding in bindings:
            if binding.attrib['name'] == 'subject':
                subject = binding.find('sparql_results:uri', ns).text

        subjects.add(subject)
    
    return subjects


def create_similar_criteria(criteria, clusters):
    subject = criteria.split(':', 1)[1]

    if subject not in clusters or not clusters[subject]:
        return 'FILTER (?subject != ?subject)'

    return 'FILTER (' + ' || '.join(['?subject = <' + duplicate + '>' for duplicate in clusters[subject]]) + ')'


def search(sparql_query, uri2rank, clusters):
    es_query, _from, criteria, offset, limit = extract_query(sparql_query)

    if 'SIMILAR' in criteria:
        # SIMILAR
        similar_criteria = create_similar_criteria(criteria, clusters)
        criteria_response = query_criteria(_from, similar_criteria) 
        bindings = create_criteria_bindings(criteria_response, uri2rank)
    elif 'USES' in criteria or 'TWINS' in criteria or es_query == '' or es_query.isspace():
        # USES or TWINS or pure advanced search
        criteria_response = query_criteria(_from, criteria)
        bindings = create_criteria_bindings(criteria_response, uri2rank)
    else:
        es_response = search_es(es_query)

        filterless_criteria = re.sub('FILTER .*', '', criteria)
        if filterless_criteria == '' or filterless_criteria.isspace():
            # pure string search
            bindings = create_bindings(es_response, clusters)
        else:
            # advanced search and string search
            criteria_response = query_criteria(_from, filterless_criteria)
            allowed_subjects = get_allowed_subjects(criteria_response)
            bindings = create_bindings(es_response, clusters, allowed_subjects)

    bindings.sort(key = lambda binding: binding['order_by'], reverse = True)

    if is_count_query(sparql_query):
        return create_count_response(len(bindings))
    else:
        bindings = bindings[offset:offset + limit]
        return create_results_response(bindings)

