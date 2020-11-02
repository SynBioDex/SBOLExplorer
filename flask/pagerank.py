from xml.etree import ElementTree
import numpy as np
import utils
import query

def get_uris():
    graphs = query.query_graphs()
    parts = []

    for graph in graphs:

        uri_query = '''
        SELECT DISTINCT ?subject
        FROM <''' + graph['graph'] + '''>
        WHERE
        {
            ?subject sbh:topLevel ?subject
        }
        '''
        parts += query.memoized_query_sparql(uri_query)

    return parts

def get_links():
    graphs = query.query_graphs()
    parts = []

    for graph in graphs:

        link_query = '''
        SELECT DISTINCT ?parent ?child
        FROM <''' + graph['graph'] + '''>
        WHERE
        {
            ?parent sbh:topLevel ?parent .
            ?child sbh:topLevel ?child .
            { ?parent ?oneLink ?child } UNION { ?parent ?twoLinkOne ?tmp . ?tmp ?twoLinkTwo ?child }
        }
        '''
        parts += query.memoized_query_sparql(link_query)

    return parts

class graph:
    # create uri to index mapping
    def init_mapping(self, adjacency_list):
        uris = set()
        for parent in adjacency_list:
            uris.add(parent)
            for child in adjacency_list[parent]:
                uris.add(child)

        self.index2uri = list(uris)
        self.uri2index = {}

        for i in range(len(self.index2uri)):
            uri = self.index2uri[i]
            self.uri2index[uri] = i

        # assert mappings are correct
        for i in range(len(self.index2uri)):
            uri = self.index2uri[i]
            index = self.uri2index[uri]
            assert(index == i)
    
    
    def init_in_links(self, adjacency_list):
        for j in range(self.size):
            self.in_links[j] = []
        
        for parent in adjacency_list:
            for child in adjacency_list[parent]:
                parent_idx = self.uri2index[parent]
                child_idx = self.uri2index[child]
                self.in_links[child_idx].append(parent_idx)
            
            
    def init_number_out_links(self, adjacency_list):
        for j in range(self.size):
            self.number_out_links[j] = 0
            
        for parent in adjacency_list:
            parent_idx = self.uri2index[parent]
            number_children = len(adjacency_list[parent])
            self.number_out_links[parent_idx] = number_children
            
        
    def init_dangling_pages(self, adjacency_list):
        for parent in adjacency_list:
            number_children = len(adjacency_list[parent])
            if number_children == 0:
                self.dangling_pages.add(self.uri2index[parent])
                
                
    def __init__(self, adjacency_list):
        self.index2uri = []
        self.uri2index = {}
        self.init_mapping(adjacency_list)
        
        self.size = len(self.index2uri)
        
        self.in_links = {}
        self.init_in_links(adjacency_list)
        
        self.number_out_links = {}
        self.init_number_out_links(adjacency_list)
        
        self.dangling_pages = set()
        self.init_dangling_pages(adjacency_list)


# add uris as keys to adjacency_list
def populate_uris(uri_response):
    adjacency_list = {}

    for uri in uri_response:
        adjacency_list[uri['subject']] = set()
    
    return adjacency_list


# add edges
def populate_links(link_response, adjacency_list):
    for link in link_response:
        adjacency_list[link['parent']].add(link['child'])


def pagerank(g, s=0.85, tolerance=0.001):
    n = g.size
    p = np.matrix(np.ones((n, 1))) / n


    if n == 0:
        utils.log('no iterations: empty graph')
        return p
    
    iteration = 1
    delta = 2
    
    while delta > tolerance:
        utils.log('iteration: ' + str(iteration))
        
        v = np.matrix(np.zeros((n, 1)))

        dangling_contrib = sum([p[j] for j in g.dangling_pages]) / n
        teleportation_contrib = 1 / n
    
        for j in range(n):
            link_contrib = sum([p[k] / g.number_out_links[k] for k in g.in_links[j]])
            v[j] = s * link_contrib + s * dangling_contrib + (1 - s) * teleportation_contrib
        new_p = v / np.sum(v)
            
        delta = np.sum(np.abs(p - new_p))
        utils.log('L1 norm delta: ' + str(delta))
        
        p = new_p
        iteration += 1
        
    return p


def make_uri2rank(pr_vector, uri2index):
    uri2rank = {}

    for uri in uri2index:
        uri2rank[uri] = pr_vector[uri2index[uri]]

    return uri2rank


def update_pagerank():
    utils.log('Query for uris')
    uri_response = get_uris()
    utils.log('Query for uris complete')
    adjacency_list = populate_uris(uri_response)

    utils.log('Query for links')
    link_response = get_links()
    utils.log('Query for links complete')
    populate_links(link_response, adjacency_list)

    g = graph(adjacency_list)
    utils.log('Running pagerank')
    pr = pagerank(g, tolerance=float(utils.get_config()['pagerank_tolerance']))
    utils.log('Running pagerank complete')
    pr_vector = np.squeeze(np.asarray(pr))

    # after squeeze, make sure it at least has a dimension in the case that there is only one element
    if pr_vector.shape == ():
        pr_vector = np.array([pr_vector])
    
    return make_uri2rank(pr_vector, g.uri2index)

