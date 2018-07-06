import sparql_util
from xml.etree import ElementTree
from elasticsearch import Elasticsearch
from elasticsearch import ElasticsearchException
from elasticsearch import helpers


parts_query = '''
SELECT DISTINCT
    ?subject
    ?displayId
    ?version
    ?name
    ?description
    ?type
WHERE {
    ?subject a sbol:ComponentDefinition .
    ?subject a ?type .
    ?subject sbh:topLevel ?subject
    OPTIONAL { ?subject sbol:displayId ?displayId . }
    OPTIONAL { ?subject sbol:version ?version . }
    OPTIONAL { ?subject dcterms:title ?name . }
    OPTIONAL { ?subject dcterms:description ?description . }
} 
'''


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


def add_pagerank(parts, uri2rank):
    for part in parts:
        part['pagerank'] = uri2rank[part['subject']]


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
    index_name = 'part'

    es = Elasticsearch(['http://localhost:9200/'], verify_certs=True)
    if not es.ping():
        raise ValueError('Connection failed')

    parts_response = sparql_util.query_sparql(parts_query)
    parts = create_parts(parts_response)	
    add_pagerank(parts, uri2rank)
    create_parts_index(es, index_name)
    index_parts(parts, es, index_name)

    print('Number of parts: ' + str(len(parts))) # TODO only fetching first 50000 parts

