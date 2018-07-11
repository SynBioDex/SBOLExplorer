import requests
import urllib.parse
from xml.etree import ElementTree
from functools import lru_cache
import pickle
import json


def get_config():
    with open('config.json') as f:
        config = json.load(f)

    return config


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
    url = get_config()['synbiohub_sparql_endpoint'] + urllib.parse.urlencode({'query': query_prefix + query})
    r = requests.get(url)

    if r.status_code != 200:
        print('Error, got status code: ' + str(r.status_code))

    return r.content


def create_parts(parts_response):
    parts = []
    
    ns = {'sparql_results': 'http://www.w3.org/2005/sparql-results#'}
    
    root = ElementTree.fromstring(parts_response)
    results = root.find('sparql_results:results', ns)

    for result in results.findall('sparql_results:result', ns):
        bindings = result.findall('sparql_results:binding', ns)

        subject = 'no subject'
        for binding in bindings:
            if binding.attrib['name'] == 'subject':
                subject = binding.find('sparql_results:uri', ns).text

        display_id = 'no displayId'
        for binding in bindings:
            if binding.attrib['name'] == 'displayId':
                display_id = binding.find('sparql_results:literal', ns).text
                
        version = 'no version'
        for binding in bindings:
            if binding.attrib['name'] == 'version':
                version = binding.find('sparql_results:literal', ns).text
        
        name = 'no name'
        for binding in bindings:
            if binding.attrib['name'] == 'name':
                name = binding.find('sparql_results:literal', ns).text
        
        description = 'no description'
        for binding in bindings:
            if binding.attrib['name'] == 'description':
                description = binding.find('sparql_results:literal', ns).text
                
        _type = 'no type'
        for binding in bindings:
            if binding.attrib['name'] == 'type':
                _type = binding.find('sparql_results:uri', ns).text

        part = {
            'subject': subject,
            'displayId': display_id,
            'version': version,
            'name': name,
            'description': description,
            'type': _type
        }
        parts.append(part)
    
    return parts


def serialize(data, filename):
    f = open(filename, 'wb')
    pickle.dump(data, f)
    f.close()


def deserialize(filename):
    f = open(filename, 'rb')
    data = pickle.load(f)
    f.close()
    return data

