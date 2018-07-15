from elasticsearch import Elasticsearch
from elasticsearch import ElasticsearchException
from elasticsearch import helpers
import utils


parts_query = '''
SELECT DISTINCT
    ?subject
    ?displayId
    ?version
    ?name
    ?description
    ?type
WHERE {
    ?subject a ?type .
    ?subject sbh:topLevel ?subject
    OPTIONAL { ?subject sbol2:displayId ?displayId . }
    OPTIONAL { ?subject sbol2:version ?version . }
    OPTIONAL { ?subject dcterms:title ?name . }
    OPTIONAL { ?subject dcterms:description ?description . }
} 
'''

def add_pagerank(parts, uri2rank):
    for part in parts:
        part['pagerank'] = uri2rank[part['subject']]


def add_keywords(parts):
    for part in parts:
        keywords = []

        displayId = part.get('displayId')
        if displayId is not None:
            keywords.extend(displayId.split('_'))

        part['keywords'] = ' '.join(keywords)


def create_parts_index(es, index_name):
    try:
        es.indices.create(index=index_name)
    except ElasticsearchException as error:
        print('Index already exists: ' + str(error))
        es.indices.delete(index=index_name)
        es.indices.create(index=index_name)
        print('Index deleted and recreated')


def index_parts(parts, es, index_name):
    actions = []
    for i in range(len(parts)):
        action = {
            '_index': index_name,
            '_type': index_name,
            '_id': i,
            '_source': parts[i]
        }

        actions.append(action)

    print('Bulk indexing')
    stats = helpers.bulk(es, actions)
    if len(stats[1]) == 0:
        print('Bulk indexing complete')
    else:
        print('Error_messages: ' + '\n'.join(stats[1]))


def update_index(uri2rank):
    index_name = utils.get_config()['elasticsearch_index_name']

    es = Elasticsearch([utils.get_config()['elasticsearch_endpoint']], verify_certs=True)
    if not es.ping():
        raise ValueError('Connection failed')

    parts_response = utils.query_sparql(parts_query)
    parts = utils.create_parts(parts_response)	
    add_pagerank(parts, uri2rank)
    add_keywords(parts)
    create_parts_index(es, index_name)
    index_parts(parts, es, index_name)

    print('Number of parts: ' + str(len(parts))) # TODO only fetching first 50000 parts

