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
    count_response['results']['bindings'][0]['count']['value'] = str(es_response.hits.total)
    return count_response


def create_results_response(es_response, limit, offset, ranks):
    results_response = {"head":{"link":[],"vars":["subject","displayId","version","name","description","type"]},"results":{"distinct":False,"ordered":True,"bindings":[]}}

    bindings = []
    for hit in es_response:
        pagerank = ranks.pr_vector[ranks.uri2index[hit.subject]] # TODO make sure type is not float is ok
        match_score = hit.meta.score
        weighted_score = weight(pagerank, match_score, len(ranks.pr_vector))

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
            },
            "pagerank": pagerank,
            "match_score": match_score,
            "weighted_score": weighted_score
        }
        bindings.append(binding)

    bindings.sort(key = lambda binding: binding['weighted_score'], reverse = True)
    results_response['results']['bindings'] = bindings

    for i in range(len(bindings)):
        print(i)
        print('uri: ' + bindings[i]['subject']['value'])
        print('pagerank: ' + str(bindings[i]['pagerank']))
        print('match_score: ' + str(bindings[i]['match_score']))
        print('weighted_score: ' + str(bindings[i]['weighted_score']))

    return results_response


def weight(pagerank, match_score, num_parts):
    pagerank_weight = 10 * num_parts
    match_score_weight = 1
    return pagerank_weight * pagerank + match_score_weight * match_score


def sparql_search(sparql_query, ranks):
    es_query, limit, offset = extract_query(sparql_query)

    es_response = search_es(es_query, limit, offset)

    if is_count_query(sparql_query):
        return create_count_response(es_response)
    else:
        return create_results_response(es_response, limit, offset, ranks)

