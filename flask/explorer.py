from flask import Flask
from flask import request
from flask import jsonify
import sparql_search


app = Flask(__name__)


@app.route('/hello')
def hello_world():
    return 'Hello, World!'


@app.route('/')
def sparql_search_endpoint():
    sparql_query = request.args.get('query')
    return jsonify(sparql_search.sparql_search(sparql_query))

