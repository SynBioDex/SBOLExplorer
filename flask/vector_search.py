from collections import Counter
from typing import Dict, List, Optional

import embedding
import facets
from configManager import ConfigManager
from elasticsearchManager import ElasticsearchManager

config_manager = ConfigManager()
elasticsearch_manager = ElasticsearchManager(config_manager)

# Largest result list a vector search returns.
MAX_SIZE = 100


def vector_search_es(es_query: str, graphs: List[str], size: int,
                     selected: Optional[Dict[str, List[str]]] = None) -> Dict:
    """
    Nearest-neighbour search on part embeddings: the parts whose text is closest
    in meaning to es_query, including those that share no word with it.

    Arguments:
        es_query {string} -- text to search for
        graphs {list} -- graph URIs the caller may see (see facets.graph_filter)
        size {int} -- number of parts to return, at most MAX_SIZE
        selected {dict} -- {facet name: [selected values]}, OR within a facet and
            AND across facets (see facets.selected_filters)

    Returns:
        Dict -- Elasticsearch hits, most similar first
    """
    # Same visibility rule as /facets: private parts only for their owner.
    clauses = [facets.graph_filter(graphs), *facets.selected_filters(selected or {})]
    body = {
        'knn': {
            'field': embedding.FIELD,
            'query_vector': embedding.embed([es_query])[0].tolist(),
            'k': size,
            # Candidates are the nearest vectors per shard; more of them give
            # better recall at a small cost.
            'num_candidates': max(100, 10 * size),
            # A pre-filter: the k nearest parts are chosen among those that match.
            'filter': clauses[0] if len(clauses) == 1 else {'bool': {'filter': clauses}}
        },
        'size': size
    }
    return elasticsearch_manager.get_es().search(
        index=config_manager.load_config()['elasticsearch_index_name'], body=body, rest_total_hits_as_int=True)


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
