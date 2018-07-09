from flask import Flask
from flask import request
from flask import jsonify
import logging
import cluster
import pagerank
import index
import search
import utils


log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)


@app.route('/hello')
def hello_world():
    return 'Hello, World!'


clusters = None
clusters_filename = 'dumps/clusters_dump'

uri2rank = None
uri2rank_filename = 'dumps/uri2rank_dump'


@app.route('/update_index')
def update_index():
    global clusters
    global uri2rank

    clusters = cluster.update_clusters()
    utils.serialize(clusters, clusters_filename)

    uri2rank = pagerank.update_pagerank()
    utils.serialize(uri2rank, uri2rank_filename)

    index.update_index(uri2rank)

    success_message = 'Index successfully updated!'
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

