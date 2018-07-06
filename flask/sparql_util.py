import requests
import urllib.parse


endpoint = 'http://localhost:7777/sparql?'

query_prefix = '''
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX sbh: <http://wiki.synbiohub.org/wiki/Terms/synbiohub#>
PREFIX synbiohub: <http://synbiohub.org#>
PREFIX igem: <http://wiki.synbiohub.org/wiki/Terms/igem#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX sbol: <http://sbols.org/v2#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX purl: <http://purl.obolibrary.org/obo/>
PREFIX ncbi: <http://www.ncbi.nlm.nih.gov#>
'''


def query_sparql(query):
    url = endpoint + urllib.parse.urlencode({'query': query_prefix + query})
    r = requests.get(url)

    if r.status_code != 200:
        print('Error, got status code: ' + str(r.status_code))

    return r.content
