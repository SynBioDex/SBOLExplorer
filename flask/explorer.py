from flask import Flask
from flask import request
from flask import jsonify
import logging
import cluster
import pagerank
import index
import search
import utils


# TODO add switch to SynBioHub, write metric tester, test API with SBOLDesigner

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)


clusters = None
clusters_filename = 'dumps/clusters_dump'

uri2rank = None
uri2rank_filename = 'dumps/uri2rank_dump'


@app.route('/info')
def info():
    return 'Explorer up!!! Virtutoso ' + str(utils.memoized_query_sparql.cache_info())


#@app.route('/similar_parts')
#def similar_parts():
# TODO use clusters to get similar parts


@app.route('/update')
def update():
    global clusters
    global uri2rank

    clusters = cluster.update_clusters()
    utils.serialize(clusters, clusters_filename)

    uri2rank = pagerank.update_pagerank()
    utils.serialize(uri2rank, uri2rank_filename)

    index.update_index(uri2rank)

    success_message = 'Successfully updated!'
    print(success_message)
    return success_message


@app.route('/')
def sparql_search_endpoint():
    global clusters
    global uri2rank

    if clusters is None:
        clusters = utils.deserialize(clusters_filename)

    if uri2rank is None:
        uri2rank = utils.deserialize(uri2rank_filename)

    sparql_query = request.args.get('query')
    return jsonify(search.search(sparql_query, uri2rank, clusters))

