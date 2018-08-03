#!/usr/bin/python3

from flask import Flask
from flask import request
from flask import jsonify
import logging
import cluster
import pagerank
import index
import search
import utils
import query


log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)


@app.route('/info')
def info():
    return 'Explorer up!!! Virtutoso ' + str(query.memoized_query_sparql.cache_info())


@app.route('/update')
def update():
    subject = request.args.get('subject')

    if subject is None:
        clusters = cluster.update_clusters()
        utils.save_clusters(clusters)

        uri2rank = pagerank.update_pagerank()
        utils.save_uri2rank(uri2rank)

        index.update_index(utils.get_uri2rank())
        
        query.memoized_query_sparql.cache_clear()
        print('Cache cleared')

        success_message = 'Successfully updated entire index!'
    else:
        index.incrementally_update_index(subject, utils.get_uri2rank())
        success_message = 'Successfully updated ' + subject + '!'

    print(success_message)
    return success_message


@app.route('/')
def sparql_search_endpoint():
    sparql_query = request.args.get('query')
    return jsonify(search.search(sparql_query, utils.get_uri2rank(), utils.get_clusters()))

