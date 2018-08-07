from elasticsearch import helpers
import utils
import query


def add_pagerank(parts_response, uri2rank):
    for part in parts_response:
        subject = part['subject']

        if subject in uri2rank:
            part['pagerank'] = uri2rank[subject]
        else:
            part['pagerank'] = 1


def add_keywords(parts_response):
    for part in parts_response:
        keywords = []

        displayId = part.get('displayId')
        if displayId is not None:
            keywords.extend(displayId.split('_'))

        part['keywords'] = ' '.join(keywords)


def create_parts_index(index_name):
    if utils.get_es().indices.exists(index_name):
        print('Index already exists -> deleting')
        utils.get_es().indices.delete(index=index_name)

    mapping = {
        'mappings': {
            index_name: {
                'properties': {
                    'subject': {
                        'type': 'keyword'
                    },
                    'graph': {
                        'type': 'keyword'
                    }
                }
            }
        }
    }
    utils.get_es().indices.create(index=index_name, body=mapping)
    print('Index created')


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
    parts_response = query.query_parts()
    print('Query for parts complete')

    add_pagerank(parts_response, uri2rank)
    add_keywords(parts_response)
    create_parts_index(index_name)
    index_parts(parts_response, index_name)

    print('Number of parts: ' + str(len(parts_response)))


def incrementally_update_index(subject, uri2rank):
    index_name = utils.get_config()['elasticsearch_index_name']

    body = {
        'query': {
            'term': { 'subject': subject }
        },
        'conflicts': 'proceed'
    }
    utils.get_es().delete_by_query(index=index_name, doc_type=index_name, body=body)

    part_response = query.query_parts('', 'FILTER (?subject = <' + subject + '>)')

    if len(part_response) == 1:
        add_pagerank(part_response, uri2rank)
        add_keywords(part_response)

        utils.get_es().index(index=index_name, doc_type=index_name, body=part_response[0])
    
