from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
import re


def search_es(es_query, limit, offset):
    es = Elasticsearch(['http://localhost:9200/'], verify_certs=True)
    body = {
        'query': {
            'function_score': {
                'query': {
                    'multi_match': {
                        'query': es_query,
                        'fields': [
                            'subject',
                            'displayId',
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
                        'source': "_score * Math.log(doc['pagerank'].value + 1)"
                    }
                }
            }
        },
        'from': offset,
        'size': limit
    }
    return es.search(index='part', body=body)


def extract_query(sparql_query):
    extract_keyword_re = re.compile(r'''CONTAINS\(lcase\(\?displayId\), lcase\('([^']*)'\)\)''')
    keywords = []
    for keyword in re.findall(extract_keyword_re, sparql_query):
        keywords.append(keyword)
    es_query = ' '.join(keywords)

    limit = 50
    limit_search = re.search(r'''LIMIT (\d*)''', sparql_query)
    if limit_search:
        limit = int(limit_search.group(1))

    offset = 0
    offset_search = re.search(r'''OFFSET (\d*)''', sparql_query)
    if offset_search:
        offset = int(offset_search.group(1))

    return es_query, limit, offset


def is_count_query(sparql_query):
    return 'SELECT (count(distinct' in sparql_query


def create_count_response(es_response):
    count_response = {"head":{"link":[],"vars":["count"]},"results":{"distinct":False,"ordered":True,"bindings":[{"count":{"type":"typed-literal","datatype":"http://www.w3.org/2001/XMLSchema#integer","value":"10"}}]}}
    count_response['results']['bindings'][0]['count']['value'] = str(es_response['hits']['total'])
    return count_response


def create_results_response(es_response, limit, offset):
    results_response = {"head":{"link":[],"vars":["subject","displayId","version","name","description","type"]},"results":{"distinct":False,"ordered":True,"bindings":[]}}

    bindings = []
    for hit in es_response['hits']['hits']:
        _source = hit['_source']
        binding = {
            "subject": {
                "type": "uri",
                "datatype": "http://www.w3.org/2001/XMLSchema#uri",
                "value": _source['subject']
            },
            "displayId": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": _source['displayId']
            },
            "version": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": _source['version']
            },
            "name": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": _source['name']
            },
            "description": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": _source['description']
            },
            "type": {
                "type": "uri",
                "datatype": "http://www.w3.org/2001/XMLSchema#uri",
                "value": _source['type']
            },
            "pagerank": _source['pagerank'],
            "_score": hit['_score']
        }
        bindings.append(binding)

    results_response['results']['bindings'] = bindings

    print('results:')
    for binding in bindings:
        print('uri: ' + binding['subject']['value'] + ' _score: ' + str(binding['_score']) + ' pagerank: ' + str(binding['pagerank']))

    return results_response


def sparql_search(sparql_query):
    es_query, limit, offset = extract_query(sparql_query)

    es_response = search_es(es_query, limit, offset)

    if is_count_query(sparql_query):
        return create_count_response(es_response)
    else:
        return create_results_response(es_response, limit, offset)

