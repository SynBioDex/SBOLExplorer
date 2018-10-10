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

@app.errorhandler(Exception)
def handle_error(e):
    print('Returning error ' + str(e))
    return jsonify(error=str(e)), 500


@app.route('/info', methods=['GET'])
def info():
    success_message = 'Explorer up!!! Virtutoso ' + str(query.memoized_query_sparql.cache_info())
    print(success_message)
    return success_message


@app.route('/config', methods=['POST', 'GET'])
def config():
    if request.method == 'POST':
        new_config = request.get_json()
        utils.set_config(new_config)
        print('Successfully updated config')

    config = utils.get_config()
    return jsonify(config)


@app.route('/update', methods=['GET'])
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

        success_message = 'Successfully updated entire index'
    else:
        index.refresh_index(subject, utils.get_uri2rank())
        success_message = 'Successfully refreshed: ' + subject

    print(success_message)
    return success_message


@app.route('/incrementalupdate', methods=['POST'])
def incremental_update():
    updates = request.get_json()

    index.incremental_update(updates, utils.get_uri2rank())

    success_message = 'Successfully incrementally updated parts'
    print(success_message)
    return success_message


@app.route('/incrementalremove', methods=['GET'])
def incremental_remove():
    subject = request.args.get('subject')

    index.incremental_remove(subject)

    success_message = 'Successfully incrementally removed: ' + subject
    print(success_message)
    return success_message


@app.route('/incrementalremovecollection', methods=['GET'])
def incremental_remove_collection():
    subject = request.args.get('subject')
    uri_prefix = request.args.get('uriPrefix')

    index.incremental_remove_collection(subject, uri_prefix)

    success_message = 'Successfully incrementally removed collection and members: ' + subject
    print(success_message)
    return success_message


@app.route('/', methods=['GET'])
def sparql_search_endpoint():
    sparql_query = request.args.get('query')

    response = jsonify(search.search(sparql_query, utils.get_uri2rank(), utils.get_clusters()))

    print('Successfully searched')
    return response

