from flask import Flask
from flask import request
from flask import jsonify
import sparql_search
import pagerank
import index


app = Flask(__name__)


@app.route('/hello')
def hello_world():
    return 'Hello, World!'


@app.route('/update_clusters')
def update_clusters():
    return 'TODO'


@app.route('/update_index')
def update_index():
    uri2rank = pagerank.update_pagerank()
    index.update_index(uri2rank)

    success_message = 'Index successfully updated!'
    print(success_message)
    return success_message


@app.route('/')
def sparql_search_endpoint():
    sparql_query = request.args.get('query')

    return jsonify(sparql_search.sparql_search(sparql_query))

