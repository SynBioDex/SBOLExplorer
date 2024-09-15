import requests
import urllib.parse
from functools import lru_cache
from wor_client import WORClient
import re
from configManager import ConfigManager
from logger import Logger

# Load config once and reuse
config_manager = ConfigManager()
config = config_manager.load_config()

logger_ = Logger()
wor_client_ = WORClient()

def query_parts(_from='', criteria='', indexing=False):
    """
    Gets all parts from Virtuoso.
    Args:
        _from: Graph the parts are from
        criteria: Any additional criteria
        indexing: Whether this query is being called during indexing

    Returns: Formatted list of all parts from Virtuoso
    """
    query = f'''
    SELECT DISTINCT
        ?subject
        ?displayId
        ?version
        ?name
        ?description
        ?type
        ?graph
        ?role
        ?sboltype
    {_from}
    WHERE {{
    {criteria}
        ?subject a ?type .
        ?subject sbh:topLevel ?subject .
        {("GRAPH ?graph { ?subject ?a ?t } ." if indexing else "")}
        OPTIONAL {{ ?subject sbol2:displayId ?displayId . }}
        OPTIONAL {{ ?subject sbol2:version ?version . }}
        OPTIONAL {{ ?subject dcterms:title ?name . }}
        OPTIONAL {{ ?subject dcterms:description ?description . }}
        OPTIONAL {{ ?subject sbol2:role ?role . }}
        OPTIONAL {{ ?subject sbol2:type ?sboltype . }}
    }} 
    '''
    return memoized_query_sparql(query)

@lru_cache(maxsize=32)
def memoized_query_sparql(query):
    """
    Speeds up SPARQL queries using a LRU cache.
    Args:
        query: SPARQL Query

    Returns: Results of the SPARQL query
    """
    return query_sparql(query)

def query_sparql(query):
    """
    Query instances of Virtuoso.
    Args:
        query: SPARQL query

    Returns: Deduplicated results of the SPARQL query
    """
    endpoints = [config['sparql_endpoint']]

    if config.get('distributed_search'):
        instances = wor_client_.get_wor_instance()
        endpoints.extend(instance['instanceUrl'] + '/sparql?' for instance in instances)

    results = []

    for endpoint in endpoints:
        try:
            results.extend(page_query(query, endpoint))
        except Exception as e:
            logger_.log(f'[ERROR] failed querying: {endpoint} - {str(e)}')
            continue

    return deduplicate_results(results)

def deduplicate_results(results):
    """
    Removes duplicates from all SPARQL queries to various Virtuoso instances.
    Args:
        results: List of results which may contain duplicates

    Returns: Deduplicated list of results
    """
    seen = set()
    deduped = []
    for result in results:
        result_tuple = tuple(sorted(result.items()))
        if result_tuple not in seen:
            seen.add(result_tuple)
            deduped.append(result)
    return deduped

def page_query(query, endpoint):
    """
    Query to get results from a particular page in SynBioHub.
    Args:
        query: Query to run
        endpoint: Virtuoso endpoint to hit

    Returns: List of parts
    """
    logger_.log(f'Current endpoint: {endpoint}')
    query_prefix = '''
    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
    PREFIX dcterms: <http://purl.org/dc/terms/>
    PREFIX dc: <http://purl.org/dc/elements/1.1/>
    PREFIX sbh: <http://wiki.synbiohub.org/wiki/Terms/synbiohub#>
    PREFIX synbiohub: <http://synbiohub.org#>
    PREFIX igem: <http://wiki.synbiohub.org/wiki/Terms/igem#>
    PREFIX prov: <http://www.w3.org/ns/prov#>
    PREFIX sbol2: <http://sbols.org/v2#>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX purl: <http://purl.obolibrary.org/obo/>
    PREFIX ncbi: <http://www.ncbi.nlm.nih.gov#>
    '''

    offset = 0
    limit = 10000
    results = []

    if endpoint != config['sparql_endpoint']:
        query = re.sub(r'''FROM.*\n''', '', query)

    while True:
        full_query = f"{query_prefix} {query} OFFSET {offset} LIMIT {limit}"
        new_results = send_query(full_query, endpoint)
        results.extend(new_results)

        if len(new_results) < limit:
            break

        offset += limit

    return results

def send_query(query, endpoint):
    """
    Sends a query to Virtuoso.
    Args:
        query: Query to be sent
        endpoint: Endpoint where Virtuoso resides

    Returns: List of parts from Virtuoso
    """
    params = {'query': query}

    if endpoint == config['sparql_endpoint']:
        params['default-graph-uri'] = ''  # Modify this if needed

    url = f"{endpoint}{urllib.parse.urlencode(params)}"
    headers = {'Accept': 'application/json'}
    
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()  # Raises an error for bad HTTP responses
    except requests.RequestException as e:
        logger_.log(f"[ERROR] exception when connecting: {str(e)}")
        raise Exception("Local SynBioHub isn't responding")

    results = [
        {key: binding[key]['value'] for key in binding}
        for binding in r.json()['results']['bindings']
    ]

    return results
