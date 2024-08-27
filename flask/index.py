from elasticsearch import helpers
from configManager import ConfigManager
from elasticsearchManager import ElasticsearchManager
import query
import json
from logger import Logger

config_manager = ConfigManager()
elasticsearch_manager = ElasticsearchManager(config_manager)
logger_ = Logger()

def add_pagerank(parts_response, uri2rank):
    """
    Adds the pagerank score for each part

    Arguments:
        parts_response {List} -- List containing all parts from the SPARQL query
        uri2rank {List} -- List of each part and its calculated pagerank score
    """

    for part in parts_response:
        subject = part['subject']

        if subject in uri2rank:
            part['pagerank'] = uri2rank[subject]
        else:
            part['pagerank'] = 1


def add_keywords(parts_response):
    """
    Adds the displayId to the 'keyword' category
    
    Arguments:
        parts_response {List} -- List containing all parts from the SPARQL query
    """

    for part in parts_response:
        keywords = []

        displayId = part.get('displayId')
        if displayId is not None:
            keywords.extend(displayId.split('_'))

        part['keywords'] = ' '.join(keywords)

def add_roles(parts_response):
    """
    Adds the synonyms from the SO-Ontologies list to each part's keyword category 
        
    Arguments:
        parts_response {List} -- List containing all parts from the SPARQL query
    """
    with open('so-simplified.json','r') as so_json:
        term_list = json.load(so_json)

        for part in parts_response: 
            # Split the CSV of roles from sparql
            role = part.get('role')

            if role is not None and 'identifiers.org' in role:
                keywords_list = []
                so_term = role[-10:]
                so_term = so_term.replace(':','_')

                for term in term_list:
                    if so_term in term['id']:
                        keywords_list.append(term['lbl'])

                        if 'synonyms' in term and term['synonyms'] is not None:
                            for synonym in term['synonyms']:

                                # remove the annoying header from the synonyms
                                if 'INSDC' in synonym:
                                    synonym = synonym.replace('INSDC_qualifier:', '')

                                if synonym not in keywords_list:
                                    keywords_list.append(synonym)
                                
                for keyword in keywords_list:           
                    part['keywords'] += ' ' + keyword

def add_sbol_type(parts_response):
    for part in parts_response:
        sbol_type = part.get('sboltype')

        if sbol_type is not None and 'http://www.biopax.org/release/biopax-level3.owl#' in sbol_type:
            type = sbol_type[48:]

            if 'region' in type:
                type = type.replace('Region','')
                
            part['keywords'] += ' ' + type

def create_parts_index(index_name):
    """
    Creates a new index

    Arguments:
        index_name {String} -- Name of the new index
    """

    if elasticsearch_manager.get_es().indices.exists(index_name):
        logger_.log('Index already exists -> deleting', True)
        elasticsearch_manager.get_es().indices.delete(index=index_name)

    body = {
        'mappings': {
            index_name: {
                'properties': {
                    'subject': {
                        'type': 'keyword'
                    },
                    'graph': {
                        'type': 'keyword'
                    }
                },
            }
        },
        "settings": {
            "number_of_shards": 1
        }

    }
    elasticsearch_manager.get_es().indices.create(index=index_name, body=body)
    logger_.log('Index created', True)


def bulk_index_parts(parts_response, index_name):
    """
    Adds each part as a document to the index
    
    Arguments:
        parts_response {List} -- List containing all parts from the SPARQL query
        index_name {String} -- Name of the index
    
    Raises:
        Exception -- Indexing fails
    """

    actions = []
    for i in range(len(parts_response)):
        action = {
            '_index': index_name,
            '_type': index_name,
            '_id': parts_response[i].get('subject'),
            '_source': parts_response[i]
        }

        actions.append(action)

    logger_.log('Bulk indexing', True)
    try:
        stats = helpers.bulk(elasticsearch_manager.get_es(), actions)
        logger_.log('Bulk indexing complete', True)
    except:
        logger_.log('[ERROR] Error_messages: ' + '\n'.join(stats[1]), True)
        raise Exception("Bulk indexing failed")

def update_index(uri2rank):
    """
    Main method
    Args:
        uri2rank: List of pageranks for each URI

    Returns:

    """
    index_name = config_manager.load_config()['elasticsearch_index_name']

    logger_.log('------------ Updating index ------------', True)

    logger_.log('******** Query for parts ********', True)
    parts_response = query.query_parts(indexing = True)
    logger_.log('******** Query for parts complete ********', True)

    logger_.log('******** Adding parts to new index ********', True)
    add_pagerank(parts_response, uri2rank)
    add_keywords(parts_response)
    add_roles(parts_response)
    add_sbol_type(parts_response)
    create_parts_index(index_name)
    bulk_index_parts(parts_response, index_name)

    logger_.log('******** Finished adding ' + str(len(parts_response)) + ' parts to index ********', True)

    logger_.log('------------ Successfully updated index ------------\n', True)


def delete_subject(subject):
    """
    Delete part for incremental indexing
    Args:
        subject:

    Returns:

    """
    index_name = config_manager.load_config()['elasticsearch_index_name']

    body = {
        'query': {
            'bool': {
                'must': [
                    {'ids': {'values': subject}}
                ]
            }
        },
        'conflicts': 'proceed'
    }
    elasticsearch_manager.get_es().delete_by_query(index=index_name, doc_type=index_name, body=body)


def index_part(part):
    delete_subject(part['subject'])
    index_name = config_manager.load_config()['elasticsearch_index_name']
    elasticsearch_manager.get_es().index(index=index_name, doc_type=index_name, id=part['subject'], body=part)


def refresh_index(subject, uri2rank):
    delete_subject(subject)

    part_response = query.query_parts('', 'FILTER (?subject = <' + subject + '>)', True)

    if len(part_response) == 1:
        add_pagerank(part_response, uri2rank)
        add_keywords(part_response)
        index_part(part_response[0])


def incremental_update(updates, uri2rank):
    if 'partsToRemove' in updates:
        for subject in updates['partsToRemove']:
            delete_subject(subject)

    parts_to_add = updates['partsToAdd']
    add_pagerank(parts_to_add, uri2rank)
    add_keywords(parts_to_add)

    for part in parts_to_add:
        index_part(part)


def incremental_remove(subject):
    delete_subject(subject)


def incremental_remove_collection(subject, uri_prefix):
    collection_membership_query = '''
    SELECT
        ?s
    WHERE {
        <''' + subject + '''> sbol2:member ?s .
        FILTER(STRSTARTS(str(?s),''' + "'" + uri_prefix + "'" + '''))
    }
    '''
    members = query.query_sparql(collection_membership_query)

    delete_subject(subject)
    for member in members:
        delete_subject(member['s'])


