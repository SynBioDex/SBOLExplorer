from typesense.exceptions import ObjectNotFound
from configManager import ConfigManager
from typesenseManager import TypesenseManager
import query
import json
from logger import Logger

config_manager = ConfigManager()
config = config_manager.load_config()
typesense_manager = TypesenseManager(config_manager)
logger_ = Logger()


PARTS_COLLECTION_SCHEMA = {
    'fields': [
        {'name': 'subject',     'type': 'string'},
        {'name': 'displayId',   'type': 'string', 'optional': True},
        {'name': 'version',     'type': 'string', 'optional': True},
        {'name': 'name',        'type': 'string', 'optional': True},
        {'name': 'description', 'type': 'string', 'optional': True},
        {'name': 'type',        'type': 'string', 'optional': True, 'facet': True},
        {'name': 'role',        'type': 'string', 'optional': True},
        {'name': 'sboltype',    'type': 'string', 'optional': True},
        {'name': 'keywords',    'type': 'string', 'optional': True},
        {'name': 'graph',       'type': 'string', 'facet': True},
        {'name': 'pagerank',    'type': 'float'},
    ],
    'default_sorting_field': 'pagerank',
}


def _doc_from_part(part):
    doc = {k: v for k, v in part.items() if v is not None}
    doc['id'] = part['subject']
    return doc


def create_parts_collection(collection_name):
    """
    Creates a fresh Typesense collection, deleting any existing one with the same name.
    """
    client = typesense_manager.get_client()
    try:
        client.collections[collection_name].delete()
        logger_.log('Collection already exists -> deleted', True)
    except ObjectNotFound:
        pass

    schema = {'name': collection_name, **PARTS_COLLECTION_SCHEMA}
    client.collections.create(schema)
    logger_.log('Collection created', True)


def add_pagerank(parts_response, uri2rank):
    """
    Adds the pagerank score for each part.
    """
    for part in parts_response:
        part['pagerank'] = uri2rank.get(part['subject'], 1)


def add_keywords(parts_response):
    """
    Adds the displayId to the 'keyword' category.
    """
    for part in parts_response:
        display_id = part.get('displayId')
        if display_id:
            part['keywords'] = ' '.join(display_id.split('_'))
        else:
            part['keywords'] = ''


def add_roles(parts_response, term_list):
    """
    Adds the synonyms from the SO-Ontologies list to each part's keyword category.
    """
    for part in parts_response:
        role = part.get('role')
        if role and 'identifiers.org' in role:
            keywords_list = []
            so_term = role[-10:].replace(':','_')

            for term in term_list:
                if so_term in term['id']:
                    keywords_list.append(term['lbl'])
                    synonyms = term.get('synonyms', [])
                    if synonyms:
                        for synonym in synonyms:
                            if 'INSDC' in synonym:
                                synonym = synonym.replace('INSDC_qualifier:', '')
                            if synonym not in keywords_list:
                                keywords_list.append(synonym)

            part['keywords'] += ' ' + ' '.join(keywords_list)


def add_sbol_type(parts_response):
    for part in parts_response:
        sbol_type = part.get('sboltype')
        if sbol_type and 'http://www.biopax.org/release/biopax-level3.owl#' in sbol_type:
            type_ = sbol_type[48:]
            if 'region' in type_:
                type_ = type_.replace('Region','')
            part['keywords'] += ' ' + type_


def bulk_index_parts(parts_response, collection_name):
    """
    Imports each part as a document into the Typesense collection.
    """
    collection = typesense_manager.get_client().collections[collection_name]
    docs = [_doc_from_part(part) for part in parts_response]

    logger_.log('Bulk indexing', True)
    try:
        results = collection.documents.import_(
            docs,
            {'action': 'upsert', 'dirty_values': 'coerce_or_drop'}
        )
        failures = [r for r in results if not r.get('success', False)]
        if failures:
            logger_.log(
                f'[ERROR] {len(failures)} documents failed to index. First error: {failures[0]}',
                True
            )
            raise RuntimeError(f'{len(failures)} documents failed indexing')
        logger_.log('Bulk indexing complete', True)
    except Exception as e:
        logger_.log(f'[ERROR] Error during bulk indexing: {str(e)}', True)
        raise


def update_index(uri2rank):
    """
    Main method to update the index.
    """
    collection_name = config_manager.get_typesense_collection_name()

    logger_.log('------------ Updating index ------------', True)
    logger_.log('******** Query for parts ********', True)
    parts_response = query.query_parts(indexing=True)
    logger_.log('******** Query for parts complete ********', True)

    logger_.log('******** Adding parts to new index ********', True)
    add_pagerank(parts_response, uri2rank)
    add_keywords(parts_response)

    with open('so-simplified.json', 'r') as so_json:
        term_list = json.load(so_json)
    add_roles(parts_response, term_list)

    add_sbol_type(parts_response)
    create_parts_collection(collection_name)
    bulk_index_parts(parts_response, collection_name)

    logger_.log(f'******** Finished adding {len(parts_response)} parts to index ********', True)
    logger_.log('------------ Successfully updated index ------------\n', True)


def delete_subject(subject):
    """
    Delete part for incremental indexing.
    """
    collection_name = config_manager.get_typesense_collection_name()
    try:
        typesense_manager.get_client().collections[collection_name].documents[subject].delete()
    except ObjectNotFound:
        pass


def index_part(part):
    collection_name = config_manager.get_typesense_collection_name()
    doc = _doc_from_part(part)
    typesense_manager.get_client().collections[collection_name].documents.upsert(doc)


def refresh_index(subject, uri2rank):
    delete_subject(subject)
    part_response = query.query_parts('', f'FILTER (?subject = <{subject}>)', True)

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
    collection_membership_query = f'''
    SELECT
        ?s
    WHERE {{
        <{subject}> sbol2:member ?s .
        FILTER(STRSTARTS(str(?s), '{uri_prefix}'))
    }}
    '''
    members = query.query_sparql(collection_membership_query)

    delete_subject(subject)
    for member in members:
        delete_subject(member['s'])
