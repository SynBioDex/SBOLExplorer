from flask import Flask
from flask import request
from flask import jsonify
import sparql_search
import pagerank
import index
import utils
import logging


log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)


@app.route('/hello')
def hello_world():
    return 'Hello, World!'


@app.route('/update_clusters')
def update_clusters():
    return 'TODO'


uri2rank = None
uri2rank_filename = 'uri2rank_dump'


@app.route('/update_index')
def update_index():
    global uri2rank

    uri2rank = pagerank.update_pagerank()
    utils.serialize(uri2rank, uri2rank_filename)

    index.update_index(uri2rank)

    success_message = 'Index successfully updated!'
    print(success_message)
    return success_message


@app.route('/')
def sparql_search_endpoint():
    global uri2rank

    if uri2rank is None:
        uri2rank = utils.deserialize(uri2rank_filename)

    sparql_query = request.args.get('query')
    return jsonify(sparql_search.sparql_search(sparql_query, uri2rank))

