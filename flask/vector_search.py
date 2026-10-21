from typing import Dict, List

import embedding
import facets
from configManager import ConfigManager
from elasticsearchManager import ElasticsearchManager

config_manager = ConfigManager()
elasticsearch_manager = ElasticsearchManager(config_manager)

# Largest result list a vector search returns.
MAX_SIZE = 100


def vector_search_es(es_query: str, graphs: List[str], size: int) -> Dict:
    """
    Nearest-neighbour search on part embeddings: the parts whose text is closest
    in meaning to es_query, including those that share no word with it.

    Arguments:
        es_query {string} -- text to search for
        graphs {list} -- graph URIs the caller may see (see facets.graph_filter)
        size {int} -- number of parts to return, at most MAX_SIZE

    Returns:
        Dict -- Elasticsearch hits, most similar first
    """
    body = {
        'knn': {
            'field': embedding.FIELD,
            'query_vector': embedding.embed([es_query])[0].tolist(),
            'k': size,
            # Candidates are the nearest vectors per shard; more of them give
            # better recall at a small cost.
            'num_candidates': max(100, 10 * size),
            # Same visibility rule as /facets: private parts only for their owner.
            'filter': facets.graph_filter(graphs)
        },
        'size': size
    }
    return elasticsearch_manager.get_es().search(
        index=config_manager.load_config()['elasticsearch_index_name'], body=body, rest_total_hits_as_int=True)
