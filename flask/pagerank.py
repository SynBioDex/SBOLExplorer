from xml.etree import ElementTree
import numpy as np
import utils


usage_query = '''
SELECT DISTINCT ?pcd ?ie ?ccd
WHERE
{
    ?pcd a sbol2:ComponentDefinition ;
    sbol2:component ?sc;
    prov:wasDerivedFrom ?ie .

    ?sc sbol2:definition ?ccd
}
'''

uri_query = '''
SELECT DISTINCT ?subject
WHERE
{
    ?subject sbh:topLevel ?subject
}
'''


class graph:
    # create uri to index mapping
    def init_mapping(self, usages):
        uris = set()
        for parent in usages:
            uris.add(parent)
            for child in usages[parent]:
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
    
    
    def init_in_links(self, usages):
        for j in range(self.size):
            self.in_links[j] = []
        
        for parent in usages:
            for child in usages[parent]:
                parent_idx = self.uri2index[parent]
                child_idx = self.uri2index[child]
                self.in_links[child_idx].append(parent_idx)
            
            
    def init_number_out_links(self, usages):
        for j in range(self.size):
            self.number_out_links[j] = 0
            
        for parent in usages:
            parent_idx = self.uri2index[parent]
            number_children = len(usages[parent])
            self.number_out_links[parent_idx] = number_children
            
        
    def init_dangling_pages(self, usages):
        for parent in usages:
            number_children = len(usages[parent])
            if number_children == 0:
                self.dangling_pages.add(self.uri2index[parent])
                
                
    def __init__(self, usages):
        self.index2uri = []
        self.uri2index = {}
        self.init_mapping(usages)
        
        self.size = len(self.index2uri)
        
        self.in_links = {}
        self.init_in_links(usages)
        
        self.number_out_links = {}
        self.init_number_out_links(usages)
        
        self.dangling_pages = set()
        self.init_dangling_pages(usages)


# add uris as keys to usages
def populate_usage_uris(uri_response):
    usages = {}
    
    ns = {'sparql_results': 'http://www.w3.org/2005/sparql-results#'}
    
    root = ElementTree.fromstring(uri_response)
    results = root.find('sparql_results:results', ns)

    for result in results.findall('sparql_results:result', ns):
        bindings = result.findall('sparql_results:binding', ns)

        for binding in bindings:
            if binding.attrib['name'] == 'subject':
                subject = binding.find('sparql_results:uri', ns).text

        usages[subject] = []
    
    return usages


# add actual usage edges
def add_usages(usage_response, usages):
    ns = {'sparql_results': 'http://www.w3.org/2005/sparql-results#'}
    
    root = ElementTree.fromstring(usage_response)
    results = root.find('sparql_results:results', ns)

    for result in results.findall('sparql_results:result', ns):
        bindings = result.findall('sparql_results:binding', ns)

        for binding in bindings:
            if binding.attrib['name'] == 'pcd':
                pcd = binding.find('sparql_results:uri', ns).text

        for binding in bindings:
            if binding.attrib['name'] == 'ccd':
                ccd = binding.find('sparql_results:uri', ns).text

        usages[pcd].append(ccd)


def pagerank(g, s=0.85, tolerance=0.001):
    n = g.size
    p = np.matrix(np.ones((n, 1))) / n
    
    iteration = 1
    delta = 2
    
    dangling_contrib = sum([p[j] for j in g.dangling_pages]) / n
    teleportation_contrib = 1 / n
    
    while delta > tolerance:
        print('iteration: ' + str(iteration))
        
        v = np.matrix(np.zeros((n, 1)))
        for j in range(n):
            link_contrib = sum([p[k] / g.number_out_links[k] for k in g.in_links[j]])
            v[j] = s * link_contrib + s * dangling_contrib + (1 - s) * teleportation_contrib
        new_p = v / np.sum(v)
            
        delta = np.sum(np.abs(p - new_p))
        print('L1 norm delta: ' + str(delta))
        
        p = new_p
        iteration += 1
        
    return p


def make_uri2rank(pr_vector, uri2index):
    uri2rank = {}

    for uri in uri2index:
        uri2rank[uri] = pr_vector[uri2index[uri]]

    return uri2rank


def update_pagerank():
    print('Query for uris')
    uri_response = utils.query_sparql(uri_query)
    print('Query for uris complete')
    usages = populate_usage_uris(uri_response)

    print('Query for usages')
    usage_response = utils.query_sparql(usage_query)
    print('Query for usages complete')
    add_usages(usage_response, usages)

    g = graph(usages)
    print('Running pagerank')
    pr = pagerank(g, tolerance=float(utils.get_config()['pagerank_tolerance']))
    print('Running pagerank complete')
    pr_vector = np.squeeze(np.asarray(pr))

    return make_uri2rank(pr_vector, g.uri2index)

