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
    ?graph
WHERE {
    ?subject a ?type .
    ?subject sbh:topLevel ?subject .
    GRAPH ?graph { ?subject ?a ?t } .
    OPTIONAL { ?subject sbol2:displayId ?displayId . }
    OPTIONAL { ?subject sbol2:version ?version . }
    OPTIONAL { ?subject dcterms:title ?name . }
    OPTIONAL { ?subject dcterms:description ?description . }
} 
'''

def add_pagerank(parts_response, uri2rank):
    for part in parts_response:
        part['pagerank'] = uri2rank[part['subject']]


def add_keywords(parts_response):
    for part in parts_response:
        keywords = []

        displayId = part.get('displayId')
        if displayId is not None:
            keywords.extend(displayId.split('_'))

        part['keywords'] = ' '.join(keywords)


def create_parts_index(index_name):
    try:
        utils.get_es.indices.create(index=index_name)
    except ElasticsearchException as error:
        print('Index already exists: ' + str(error))
        utils.get_es.indices.delete(index=index_name)
        utils.get_es.indices.create(index=index_name)
        print('Index deleted and recreated')


def index_parts(parts_response, index_name):
    actions = []
    for i in range(len(parts_response)):
        action = {
            '_index': index_name,
            '_type': index_name,
            '_id': i,
            '_source': parts_response[i]
        }

        actions.append(action)

    print('Bulk indexing')
    stats = helpers.bulk(utils.get_es(), actions)
    if len(stats[1]) == 0:
        print('Bulk indexing complete')
    else:
        print('Error_messages: ' + '\n'.join(stats[1]))


def update_index(uri2rank):
    index_name = utils.get_config()['elasticsearch_index_name']

    print('Query for parts')
    parts_response = utils.query_sparql(parts_query)
    print('Query for parts complete')

    add_pagerank(parts_response, uri2rank)
    add_keywords(parts_response)
    create_parts_index(index_name)
    index_parts(parts_response, index_name)

    print('Number of parts: ' + str(len(parts_response)))


def incrementally_update_index(subject):
    # TODO implement delete and then index of subject
    pass
    
