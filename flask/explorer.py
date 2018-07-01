from flask import Flask
from flask import request
from flask import jsonify
import re

app = Flask(__name__)

@app.route('/hello')
def hello_world():
    return 'Hello, World!'


count_response = {"head":{"link":[],"vars":["count"]},"results":{"distinct":False,"ordered":True,"bindings":[{"count":{"type":"typed-literal","datatype":"http://www.w3.org/2001/XMLSchema#integer","value":"0"}}]}}

results_response = {"head":{"link":[],"vars":["subject","displayId","version","name","description","type"]},"results":{"distinct":False,"ordered":True,"bindings":[]}}

extract_keyword_re = re.compile(r'''CONTAINS\(lcase\(\?displayId\), lcase\('([^']*)'\)\)''')

@app.route('/')
def search():
    sparql_query = request.args.get('query')

    print(sparql_query)

    if 'SELECT (count(distinct' in sparql_query:
        return jsonify(count_response)

    keywords = []
    for keyword in re.findall(extract_keyword_re, sparql_query):
        keywords.append(keyword)

    print(keywords)

    return jsonify(results_response)

