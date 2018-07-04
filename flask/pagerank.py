from xml.etree import ElementTree
import requests
import urllib.parse
import numpy as np


class ranks:
    def __init__(self, pr_vector, uri2index):
        self.pr_vector = pr_vector
        self.uri2index = uri2index


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


endpoint = 'http://localhost:7777/sparql?'

query_prefix = '''
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX sbh: <http://wiki.synbiohub.org/wiki/Terms/synbiohub#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX sbol: <http://sbols.org/v2#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX purl: <http://purl.obolibrary.org/obo/>
'''

usage_query = query_prefix + '''
select distinct ?pcd ?ie ?ccd
WHERE
{
?pcd a sbol:ComponentDefinition ;
sbol:component ?sc;
prov:wasDerivedFrom ?ie .

?sc sbol:definition ?ccd
}
'''

uri_query = query_prefix + '''
select distinct ?cd
WHERE
{
?cd a sbol:ComponentDefinition
}
'''


def query_sparql(query):
    url = endpoint + urllib.parse.urlencode({'query': query})
    print(url)
    r = requests.get(url)

    print(r.status_code)
    print(r.encoding)
    print(r.headers['content-type'])
    print(r.content[0:100])

    return r.content


# add uris as keys to usages
def populate_usage_uris(uri_response):
    usages = {}
    
    ns = {'sparql_results': 'http://www.w3.org/2005/sparql-results#'}
    
    root = ElementTree.fromstring(uri_response)
    results = root.find('sparql_results:results', ns)

    for result in results.findall('sparql_results:result', ns):
        bindings = result.findall('sparql_results:binding', ns)

        for binding in bindings:
            if binding.attrib['name'] == 'cd':
                cd = binding.find('sparql_results:uri', ns).text

        usages[cd] = []
    
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


def update_pagerank():
    uri_response = query_sparql(uri_query)
    usages = populate_usage_uris(uri_response)

    usage_response = query_sparql(usage_query)
    add_usages(usage_response, usages)

    g = graph(usages)
    pr = pagerank(g)
    pr_vector = np.squeeze(np.asarray(pr))
    return ranks(pr_vector, g.uri2index)

