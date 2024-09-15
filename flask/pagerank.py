import numpy as np
import query
from logger import Logger
from configManager import ConfigManager

config_manager = ConfigManager()
logger_ = Logger()

link_query = '''
SELECT DISTINCT ?parent ?child
WHERE
{
    ?parent sbh:topLevel ?parent .
    ?child sbh:topLevel ?child .
    { ?parent ?oneLink ?child } UNION { ?parent ?twoLinkOne ?tmp . ?tmp ?twoLinkTwo ?child }
}
'''

uri_query = '''
SELECT DISTINCT ?subject
WHERE
{
    ?subject sbh:topLevel ?subject
}
'''

class Graph:
    def __init__(self, adjacency_list):
        self.uri2index = {uri: idx for idx, uri in enumerate(adjacency_list)}
        self.index2uri = list(adjacency_list.keys()) 
        self.size = len(self.index2uri)

        self.in_links = {_:[] for _ in range(self.size)}
        self.number_out_links = {_:0 for _ in range(self.size)}
        self.dangling_pages = set()

        for parent, children in adjacency_list.items():
            parent_idx = self.uri2index[parent]
            if children:
                self.number_out_links[parent_idx] = len(children)
                for child in children:
                    child_idx = self.uri2index[child]
                    self.in_links[child_idx].append(parent_idx)
            else:
                self.dangling_pages.add(parent_idx)

    def get_dangling_contrib(self, p):
        return sum([p[j] for j in self.dangling_pages]) / self.size

    def get_teleportation_contrib(self):
        return 1.0 / self.size

def populate_uris(uri_response):
    return {uri['subject']: set() for uri in uri_response}

# add edges
def populate_links(link_response, adjacency_list):
    try:
        for link in link_response:
            adjacency_list[link['parent']].add(link['child'])
    except:
        raise

def pagerank(g, s=0.85, tolerance=0.001):
    n = g.size
    p = np.ones(n) / n  # Initial probability distribution vector

    if n == 0:
        logger_.log('no iterations: empty graph', True)
        return p
    
    iteration = 1
    delta = 2

    while delta > tolerance:
        v = np.zeros(n)
        dangling_contrib = g.get_dangling_contrib(p)
        teleportation_contrib = g.get_teleportation_contrib()

        for j in range(n):
            in_link_contrib = np.sum(p[k] / g.number_out_links[k] for k in g.in_links[j])
            v[j] = s * (in_link_contrib + dangling_contrib) + (1 - s) * teleportation_contrib

        v /= np.sum(v)
        delta = np.sum(np.abs(p - v))
        logger_.log(f'Iteration {iteration}: L1 norm delta is {delta}', True)
        
        p = v
        iteration += 1

    return p

def make_uri2rank(pr_vector, uri2index):
    return {uri: pr_vector[idx] for uri, idx in uri2index.items()}

def update_pagerank():
    logger_.log('------------ Updating pagerank ------------', True)
    logger_.log('******** Query for uris ********', True)
    uri_response = query.query_sparql(uri_query)
    logger_.log('******** Query for uris complete ********', True)

    adjacency_list = populate_uris(uri_response)

    logger_.log('******** Query for links ********', True)
    link_response = query.query_sparql(link_query)
    logger_.log('******** Query for links complete ********', True)

    populate_links(link_response, adjacency_list)

    g = Graph(adjacency_list)

    logger_.log('******** Running pagerank ********', True)
    pr_vector = pagerank(g, tolerance=float(config_manager.load_config()['pagerank_tolerance']))
    logger_.log('******** Running pagerank complete ********', True)
    logger_.log('------------ Successfully updated pagerank ------------\n', True)
    
    return make_uri2rank(pr_vector, g.uri2index)
