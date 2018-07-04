from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
import re


es = Elasticsearch(['http://localhost:9200/'], verify_certs=True)


def search_es(es_query, limit, offset):
    s = Search(using=es, index='part').query('multi_match', query=es_query, fields=['subject', 'displayId', 'version', 'name', 'description', 'type'])
    s = s[offset:offset + limit]
    return s.execute()


def extract_query(sparql_query):
    extract_keyword_re = re.compile(r'''CONTAINS\(lcase\(\?displayId\), lcase\('([^']*)'\)\)''')
    keywords = []
    for keyword in re.findall(extract_keyword_re, sparql_query):
        keywords.append(keyword)
    es_query = ' '.join(keywords)
    print('keywords: ' + es_query)

    limit = 10
    limit_search = re.search(r'''LIMIT (\d*)''', sparql_query)
    if limit_search:
        limit = int(limit_search.group(1))
        print('limit: ' + str(limit))

    offset = 0
    offset_search = re.search(r'''OFFSET (\d*)''', sparql_query)
    if offset_search:
        offset = int(offset_search.group(1))
        print('offset: ' + str(offset))

    return es_query, limit, offset


def is_count_query(sparql_query):
    return 'SELECT (count(distinct' in sparql_query


def create_count_response(es_results):
    count_response = {"head":{"link":[],"vars":["count"]},"results":{"distinct":False,"ordered":True,"bindings":[{"count":{"type":"typed-literal","datatype":"http://www.w3.org/2001/XMLSchema#integer","value":"10"}}]}}
    count_response['results']['bindings'][0]['count']['value'] = str(es_results.hits.total)
    return count_response


def create_results_response(es_results):
    results_response = {"head":{"link":[],"vars":["subject","displayId","version","name","description","type"]},"results":{"distinct":False,"ordered":True,"bindings":[]}}

    bindings = []
    for hit in es_results:
        binding = {
            "subject": {
                "type": "uri",
                "datatype": "http://www.w3.org/2001/XMLSchema#uri",
                "value": hit.subject
            },
            "displayId": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": hit.displayId
            },
            "version": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": hit.version
            },
            "name": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": hit.name
            },
            "description": {
                "type": "literal",
                "datatype": "http://www.w3.org/2001/XMLSchema#string",
                "value": hit.description
            },
            "type": {
                "type": "uri",
                "datatype": "http://www.w3.org/2001/XMLSchema#uri",
                "value": hit.type
            }
        }
        bindings.append(binding)
    
    results_response['results']['bindings'] = bindings
    return results_response


def sparql_search(sparql_query):
    print(sparql_query)

    es_query, limit, offset = extract_query(sparql_query)

    es_results = search_es(es_query, limit, offset)

    if is_count_query(sparql_query):
        return create_count_response(es_results)
    else:
        return create_results_response(es_results)

