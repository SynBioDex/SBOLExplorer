import json
import re
from functools import lru_cache
from typing import Dict, List, Optional

import search
from configManager import ConfigManager
from elasticsearchManager import ElasticsearchManager

config_manager = ConfigManager()
elasticsearch_manager = ElasticsearchManager(config_manager)

# Facet name (the /facets API name) -> the keyword-array field it is stored in,
# and the SPARQL pattern (binding ?subject and ?value) that fills that field at
# index time. These fields are separate from the single-valued 'role', 'type'
# and 'sboltype' fields the text search uses, which keep only one value per part.
FACETS = {
    'role': {
        'field': 'facet_role',
        'pattern': '?subject sbol2:role ?value .'
    },
    'sboltype': {
        'field': 'facet_sboltype',
        'pattern': '?subject sbol2:type ?value .'
    },
    'type': {
        'field': 'facet_type',
        'pattern': '?subject a ?value .'
    },
    'creator': {
        'field': 'facet_creator',
        'pattern': '?subject dc:creator ?value .'
    },
    'collections': {
        'field': 'facet_collections',
        'pattern': '?value a sbol2:Collection . ?value sbol2:member ?subject .'
    },
}

DEFAULT_FACETS = list(FACETS)
# Facets list every value, like the SPARQL facet queries they replace: a
# private collection's creator is on that one collection only (SynBioHub puts
# dc:creator on the submission collection, not its parts), so a top-N cut-off
# hides it. Five facets x 10,000 stays below Elasticsearch's search.max_buckets
# (65,536 per search).
MAX_FACET_SIZE = 10000

SO_TERM_PATTERN = re.compile(r'SO[:_](\d{7})')


@lru_cache(maxsize=1)
def so_labels() -> Dict[str, str]:
    """Maps 'SO_0000167' -> 'promoter' from the bundled SO term list."""
    with open('so-simplified.json', 'r') as so_json:
        terms = json.load(so_json)
    return {term['id'].rsplit('/', 1)[-1]: term['lbl'] for term in terms if term.get('lbl')}


def short_name(uri: str) -> str:
    return re.split(r'[#/]', uri.rstrip('/'))[-1]


def role_label(uri: str) -> str:
    match = SO_TERM_PATTERN.search(uri)
    if match:
        label = so_labels().get(f'SO_{match.group(1)}')
        if label:
            return label
    return short_name(uri)


def graph_filter(graphs: List[str]) -> Dict:
    """
    Restricts documents to the caller's graphs. With no graphs given, only
    public documents are counted, so a caller that forgets to pass its graphs
    can never see counts (or collection names) from someone's private graph.
    """
    if graphs:
        return {'terms': {'graph': graphs}}
    return {'bool': {'must_not': {'wildcard': {'graph': '*/user/*'}}}}


def selected_filters(selected: Dict[str, List[str]], exclude: Optional[str] = None) -> List[Dict]:
    """OR within a facet, AND across facets; optionally leaving one facet out."""
    return [
        {'terms': {FACETS[name]['field']: values}}
        for name, values in selected.items()
        if values and name != exclude
    ]


def facet_search(es_query: str, graphs: List[str], selected: Dict[str, List[str]],
                 facet_by: List[str], size: int = 50) -> Dict:
    """
    Facet counts for a text search, in a single Elasticsearch request.

    Every facet's counts honour the selections in all OTHER facets but not its
    own (self-exclusion), so picking one role still shows the counts of the
    other roles. 'found' honours every selection: it is the size of the
    filtered result set.

    Arguments:
        es_query -- search text; '' counts every document in the graphs
        graphs -- graph URIs the caller may see (public + their own private graph)
        selected -- {facet name: [selected values]}
        facet_by -- facets to return counts for
        size -- maximum values returned per facet

    Returns:
        {'found': int, 'facets': {name: [{'value', 'label', 'count'}]}}
    """
    index_name = config_manager.load_config()['elasticsearch_index_name']
    es = elasticsearch_manager.get_es()
    visible = graph_filter(graphs)

    aggs = {'_found': {'filter': {'bool': {'filter': selected_filters(selected)}}}}
    for name in facet_by:
        aggs[name] = {
            'filter': {'bool': {'filter': selected_filters(selected, exclude=name)}},
            'aggs': {'values': {'terms': {'field': FACETS[name]['field'], 'size': size}}}
        }

    body = {
        'size': 0,
        'query': {
            'bool': {
                'must': [search.text_query(es_query) if es_query else {'match_all': {}}],
                'filter': [visible]
            }
        },
        'aggs': aggs
    }
    aggregations = es.search(index=index_name, body=body)['aggregations']

    facets = {}
    for name in facet_by:
        buckets = aggregations[name]['values']['buckets']
        facets[name] = [{'value': b['key'], 'count': b['doc_count']} for b in buckets]
    for name, values in facets.items():
        if name == 'collections':
            facets[name] = visible_collections(es, index_name, values, visible)
        else:
            for value in values:
                value['label'] = label_for(name, value['value'])

    return {'found': aggregations['_found']['doc_count'], 'facets': facets}


def label_for(name: str, value: str) -> str:
    if name == 'role':
        return role_label(value)
    if name == 'creator':
        return value
    return short_name(value)


def visible_collections(es, index_name: str, values: List[Dict], visible: Dict) -> List[Dict]:
    """
    Keeps only collections the caller may see, labelled with their name.

    A public part can be a member of someone's private collection; the counts
    are over visible parts either way, but the private collection itself must
    not appear as an option. Collections are top-level documents, so their own
    'graph' field decides visibility.
    """
    if not values:
        return []
    response = es.search(index=index_name, body={
        'size': len(values),
        '_source': ['subject', 'name', 'displayId'],
        'query': {'bool': {'filter': [{'terms': {'subject': [v['value'] for v in values]}}, visible]}}
    })
    names = {}
    for hit in response['hits']['hits']:
        source = hit['_source']
        names[source['subject']] = source.get('name') or source.get('displayId') or short_name(source['subject'])
    return [
        {**value, 'label': names[value['value']]}
        for value in values
        if value['value'] in names
    ]
