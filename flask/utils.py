import requests
import urllib.parse
from xml.etree import ElementTree
from functools import lru_cache
from elasticsearch import Elasticsearch
import pickle
import json


def get_config():
    with open('config.json') as f:
        config = json.load(f)

    return config


es = None

def get_es():
    global es

    if not es:
        es = Elasticsearch([get_config()['elasticsearch_endpoint']], verify_certs=True)
        if not es.ping():
            raise ValueError('Connection failed')

    return es


query_prefix = '''
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX sbh: <http://wiki.synbiohub.org/wiki/Terms/synbiohub#>
PREFIX synbiohub: <http://synbiohub.org#>
PREFIX igem: <http://wiki.synbiohub.org/wiki/Terms/igem#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX sbol2: <http://sbols.org/v2#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX purl: <http://purl.obolibrary.org/obo/>
PREFIX ncbi: <http://www.ncbi.nlm.nih.gov#>
'''


@lru_cache(maxsize=32)
def memoized_query_sparql(query):
    return query_sparql(query)


def query_sparql(query):
    endpoints = [get_config()['sparql_endpoint']]

    if get_config()['distributed_search']:
        instances = requests.get('https://wor.synbiohub.org/instances/').json()
        for instance in instances:
            endpoints.append(instance['instanceUrl'] + '/sparql?')

    results = []

    for endpoint in endpoints:
        results.extend(page_query(query, endpoint))

    return deduplicate_results(results)


def deduplicate_results(results):
    deduped = set()

    for result in results:
        deduped.add(json.dumps(result, sort_keys=True))

    return [json.loads(result) for result in deduped]


def page_query(query, endpoint):
    print('endpoint: ' + endpoint)

    offset = 0
    limit = 10000

    results = []

    while True:
        full_query = query_prefix + query + 'OFFSET ' + str(offset) + ' LIMIT ' + str(limit)
        new_results = send_query(full_query, endpoint)
        results.extend(new_results)
        print(str(len(results)) + ' ', end='', flush=True)

        if len(new_results) != limit:
            print()
            break

        offset += limit

    return results


def send_query(query, endpoint):
    url = endpoint + urllib.parse.urlencode({'query': query})
    headers = {'Accept': 'application/json'}
    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        print('Error, got status code: ' + str(r.status_code))

    results = []

    for binding in r.json()['results']['bindings']:
        result = {}
        for key in binding:
            result[key] = binding[key]['value']
        results.append(result)

    return results


def serialize(data, filename):
    f = open(filename, 'wb')
    pickle.dump(data, f)
    f.close()


def deserialize(filename):
    f = open(filename, 'rb')
    data = pickle.load(f)
    f.close()
    return data

