from flask import Flask
from flask import request
from flask import jsonify
import sparql_search
import pagerank


app = Flask(__name__)


@app.route('/hello')
def hello_world():
    return 'Hello, World!'


@app.route('/update_clusters')
def update_clusters():
    return 'TODO'


# have lock around this
ranks = None

@app.route('/update_pagerank')
def update_pagerank():
    global ranks
    ranks = pagerank.update_pagerank()
    return 'Pagerank successfully updated!'


@app.route('/update_index')
def update_index():
    return 'TODO'


@app.route('/')
def sparql_search_endpoint():
    sparql_query = request.args.get('query')

    global ranks
    return jsonify(sparql_search.sparql_search(sparql_query, ranks))

