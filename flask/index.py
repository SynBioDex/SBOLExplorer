from elasticsearch import helpers
from configManager import ConfigManager
from elasticsearchManager import ElasticsearchManager
import query
import json
from logger import Logger

# Load config and initialize managers once
config_manager = ConfigManager()
config = config_manager.load_config()
elasticsearch_manager = ElasticsearchManager(config_manager)
logger_ = Logger()

def add_pagerank(parts_response, uri2rank):
    """
    Adds the pagerank score for each part.

    Arguments:
        parts_response {List} -- List containing all parts from the SPARQL query
        uri2rank {Dict} -- Dictionary of each part and its calculated pagerank score
    """
    for part in parts_response:
        part['pagerank'] = uri2rank.get(part['subject'], 1)


def add_keywords(parts_response):
    """
    Adds the displayId to the 'keyword' category.

    Arguments:
        parts_response {List} -- List containing all parts from the SPARQL query
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

    Arguments:
        parts_response {List} -- List containing all parts from the SPARQL query
        term_list {List} -- List of terms from the SO-Ontologies
    """
    for part in parts_response: 
        # Split the CSV of roles from sparql
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
                            # remove the annoying header from the synonyms
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


def create_parts_index(index_name):
    """
    Creates a new index.

    Arguments:
        index_name {String} -- Name of the new index
    """
    es = elasticsearch_manager.get_es()
    if es.indices.exists(index_name):
        logger_.log('Index already exists -> deleting', True)
        es.indices.delete(index=index_name)

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
        'settings': {
            'number_of_shards': 1
        }
    }
    es.indices.create(index=index_name, body=body)
    
    logger_.log('Index created', True)


def index_page(es, parts_page, index_name, uri2rank, term_list):
    """
    Enriches one page of parts (pagerank/keywords/roles/sbol type) and bulk
    indexes it. Keeping enrichment + indexing per-page means only one page is
    ever resident in memory, instead of the whole corpus.

    Arguments:
        es -- Elasticsearch client
        parts_page {List} -- One page of parts from the SPARQL query
        index_name {String} -- Name of the index
        uri2rank {Dict} -- Pagerank scores
        term_list {List} -- SO-Ontologies terms (loaded once, reused per page)
    """
    add_pagerank(parts_page, uri2rank)
    add_keywords(parts_page)
    add_roles(parts_page, term_list)
    add_sbol_type(parts_page)

    skipped = []

    def actions():
        for part in parts_page:
            # ES rejects the whole bulk request if any _id exceeds 512 bytes,
            # which would kill the entire page. Skip the (rare) parts with a
            # pathologically long subject URI; they're logged below, not
            # silently dropped.
            if len(part['subject'].encode('utf-8')) > 512:
                skipped.append(part['subject'])
                continue
            yield {
                '_index': index_name,
                '_type': index_name,
                '_id': part['subject'],
                '_source': part
            }

    try:
        helpers.bulk(es, actions())
    except Exception as e:
        logger_.log(f'[ERROR] Error during bulk indexing: {str(e)}', True)
        raise
    if skipped:
        logger_.log(f'[WARN] skipped {len(skipped)} part(s) with subject URI > 512 bytes '
                    f'(ES _id limit); first: {skipped[0][:120]}', True)


def update_index(uri2rank):
    """
    Main method to update the index.

    Streams parts page-by-page so peak memory stays at one page rather than the
    full ~300k-part corpus (which OOM-killed indexing on memory-limited hosts).

    Args:
        uri2rank: Dictionary of pageranks for each URI
    """
    index_name = config['elasticsearch_index_name']

    logger_.log('------------ Updating index ------------', True)

    # Load the SO-Ontologies list once; reused for every page.
    with open('so-simplified.json', 'r') as so_json:
        term_list = json.load(so_json)

    es = elasticsearch_manager.get_es()

    total = 0
    if config.get('distributed_search'):
        # Distributed mode needs cross-endpoint dedup, so fall back to loading
        # all parts at once (original behavior).
        logger_.log('******** Query for parts (distributed, full load) ********', True)
        parts_response = query.query_parts(indexing=True)
        logger_.log('******** Query for parts complete ********', True)
        # Create (delete+recreate) only after the query succeeds, so a failed
        # query leaves the old index intact.
        create_parts_index(index_name)
        index_page(es, parts_response, index_name, uri2rank, term_list)
        total = len(parts_response)
    else:
        # Single endpoint: stream page-by-page to keep memory flat.
        logger_.log('******** Streaming parts into index ********', True)
        page_num = 0
        for parts_page in query.query_parts_paged(indexing=True):
            page_num += 1
            if page_num == 1:
                # Delete the old index only once the first page is in hand, so a
                # query that fails up front doesn't wipe the existing index.
                create_parts_index(index_name)
            index_page(es, parts_page, index_name, uri2rank, term_list)
            total += len(parts_page)
            logger_.log(f'Indexed page {page_num} ({total} parts so far)', True)
        if total == 0:
            # No parts returned: still (re)create an empty index, matching the
            # original behavior of always producing a fresh index.
            create_parts_index(index_name)

    logger_.log(f'******** Finished adding {total} parts to index ********', True)
    logger_.log('------------ Successfully updated index ------------\n', True)


def delete_subject(subject):
    """
    Delete part for incremental indexing.

    Args:
        subject: The subject to delete from the index.
    """
    index_name = config['elasticsearch_index_name']
    es = elasticsearch_manager.get_es()

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
    es.delete_by_query(index=index_name, doc_type=index_name, body=body)


def index_part(part):
    delete_subject(part['subject'])
    index_name = config['elasticsearch_index_name']
    es = elasticsearch_manager.get_es()
    es.index(index=index_name, doc_type=index_name, id=part['subject'], body=part)


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
