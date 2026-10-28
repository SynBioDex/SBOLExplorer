from collections import Counter
from typing import Dict, List, Optional

import embedding
import facets
from configManager import ConfigManager
from elasticsearchManager import ElasticsearchManager

config_manager = ConfigManager()
elasticsearch_manager = ElasticsearchManager(config_manager)

# Largest page a vector search returns.
MAX_SIZE = 100
# Deepest result a vector search pages through (offset + size never goes past it).
MAX_RESULTS = 100


def visible_filter(graphs: List[str], selected: Optional[Dict[str, List[str]]] = None) -> Dict:
    """The caller's visibility and facet selections as one ES filter."""
    clauses = [facets.graph_filter(graphs), *facets.selected_filters(selected or {})]
    return clauses[0] if len(clauses) == 1 else {'bool': {'filter': clauses}}


def top_n(graphs: List[str], selected: Optional[Dict[str, List[str]]] = None) -> int:
    """
    How many parts a search by meaning returns in all: every visible part that
    has an embedding (kNN always has a nearest part to give), at most MAX_RESULTS.
    """
    body = {'query': {'bool': {'filter': [
        visible_filter(graphs, selected), {'exists': {'field': embedding.FIELD}}
    ]}}}
    count = elasticsearch_manager.get_es().count(
        index=config_manager.load_config()['elasticsearch_index_name'], body=body)['count']
    return min(count, MAX_RESULTS)


def vector_search_es(es_query: str, graphs: List[str], size: int,
                     selected: Optional[Dict[str, List[str]]] = None, offset: int = 0) -> Dict:
    """
    Nearest-neighbour search on part embeddings: the parts whose text is closest
    in meaning to es_query, including those that share no word with it.

    Arguments:
        es_query {string} -- text to search for
        graphs {list} -- graph URIs the caller may see (see facets.graph_filter)
        size {int} -- number of parts to return, at most MAX_SIZE
        selected {dict} -- {facet name: [selected values]}, OR within a facet and
            AND across facets (see facets.selected_filters)
        offset {int} -- number of most similar parts to skip, for paging

    Returns:
        Dict -- Elasticsearch hits, most similar first, from offset on
    """
    # kNN returns its k nearest parts, so a page is the first offset + size of
    # them with the first offset dropped
    k = offset + size
    # Same visibility rule as /facets: private parts only for their owner.
    body = {
        'knn': {
            'field': embedding.FIELD,
            'query_vector': embedding.embed([es_query])[0].tolist(),
            'k': k,
            # Candidates are the nearest vectors per shard; more of them give
            # better recall at a small cost.
            'num_candidates': max(100, 10 * k),
            # A pre-filter: the k nearest parts are chosen among those that match.
            'filter': visible_filter(graphs, selected)
        },
        'size': k
    }
    response = elasticsearch_manager.get_es().search(
        index=config_manager.load_config()['elasticsearch_index_name'], body=body, rest_total_hits_as_int=True)
    response['hits']['hits'] = response['hits']['hits'][offset:]
    return response


def facets_for_hits(hits: List[Dict], facet_by: List[str], graphs: List[str]) -> Dict:
    """
    Facet counts over the hits themselves: how many of the returned parts have
    each value. Counts are for these parts only, not the whole index, and
    ignore the sidebar selections, as the hits do.

    Arguments:
        hits {list} -- Elasticsearch hits from vector_search_es
        facet_by {list} -- facets to count (names from facets.FACETS)
        graphs {list} -- graph URIs the caller may see, as for vector_search_es

    Returns:
        Dict -- {facet name: [{'value', 'label', 'count'}]}, most frequent first
    """
    counts = {name: Counter() for name in facet_by}
    for hit in hits:
        for name in facet_by:
            counts[name].update(hit['_source'].get(facets.FACETS[name]['field']) or [])

    index_name = config_manager.load_config()['elasticsearch_index_name']
    es = elasticsearch_manager.get_es()
    visible = facets.graph_filter(graphs)

    result = {}
    for name in facet_by:
        values = [{'value': value, 'count': count} for value, count in counts[name].most_common()]
        if name == 'collections':
            result[name] = facets.visible_collections(es, index_name, values, visible)
        else:
            for value in values:
                value['label'] = facets.label_for(name, value['value'])
            result[name] = values
    return result
