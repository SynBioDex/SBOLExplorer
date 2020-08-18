#!/usr/bin/python3

from flask import Flask, request, jsonify, abort
from werkzeug.exceptions import HTTPException

import traceback
import logging
import cluster
import pagerank
import index
import search
import utils
import query
import sequencesearch
import requests


log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

def auto_update_index():
    while utils.get_config()['autoUpdateIndex']:
        sleep(int(utils.get_config()['updateTimeInDays']) * 86400)
        utils.log('Updating index automatically. To disable, set the \"autoUpdateIndex\" property in config.json to false.')
        
@app.errorhandler(Exception)
def handle_error(e):
    utils.log('[ERROR] Returning error ' + str(e) + "\n Traceback:\n" + traceback.format_exc())

    if isinstance(e, HTTPException):
        return jsonify(error=str(e.name + ": " + e.description)), e.code
    else:
        return jsonify(error=str(type(e).__name__) + str(e)), 500

@app.before_first_request
def startup():
    utils.log('SBOLExplorer started :)')
    auto_update_index()

@app.errorhandler(Exception)
def handle_error(e):
    utils.log('[ERROR] Returning error ' + str(e) + "\n Traceback:\n" + traceback.format_exc())
    return jsonify(error=str(e)), 500
    es_indices = utils.get_es().indices.get(index='*,-localhost*,-.kibana')
    if (len(es_indices) == 0):
        utils.log('Index not found, creating new index.')
        requests.get(request.url_root + '/update')


@app.route('/info', methods=['GET'])
def info():
    utils.log('Explorer up!!! Virtutoso ' + str(query.memoized_query_sparql.cache_info()))
    return utils.get_log()


@app.route('/config', methods=['POST', 'GET'])
def config():
    if request.method == 'POST':
        new_config = request.get_json()
        utils.set_config(new_config)
        utils.log('Successfully updated config')

    config = utils.get_config()
    return jsonify(config)


@app.route('/update', methods=['GET'])
def update():
    try:
        subject = request.args.get('subject')

        if subject is None:
            utils.save_update_start_time()

            clusters = cluster.update_clusters()
            utils.save_clusters(clusters)
            
            
            uri2rank = pagerank.update_pagerank()
            utils.save_uri2rank(uri2rank)

            index.update_index(utils.get_uri2rank())
            
            query.memoized_query_sparql.cache_clear()
            utils.log('Cache cleared')

            utils.save_update_end_time()
            success_message = 'Successfully updated entire index'
        else:
            index.refresh_index(subject, utils.get_uri2rank())
            success_message = 'Successfully refreshed: ' + subject

        utils.log(success_message)
        return success_message
    except:
        raise


@app.route('/incrementalupdate', methods=['POST'])
def incremental_update():
    try:
        updates = request.get_json()

        index.incremental_update(updates, utils.get_uri2rank())

        success_message = 'Successfully incrementally updated parts'
        utils.log(success_message)
        return 
    except:
        raise


@app.route('/incrementalremove', methods=['GET'])
def incremental_remove():
    try:
        subject = request.args.get('subject')

        index.incremental_remove(subject)

        success_message = 'Successfully incrementally removed: ' + subject
        utils.log(success_message)
        return success_message
    except:
        raise

@app.route('/incrementalremovecollection', methods=['GET'])
def incremental_remove_collection():
    try:
        subject = request.args.get('subject')
        uri_prefix = request.args.get('uriPrefix')

        index.incremental_remove_collection(subject, uri_prefix)

        success_message = 'Successfully incrementally removed collection and members: ' + subject
        utils.log(success_message)
        return success_message
    except:
        raise


@app.route('/', methods=['GET'])
def sparql_search_endpoint():
    try:
        # make sure index is built, or throw exception
        if utils.get_es().indices.exists(index='*,-localhost*,-.kibana') is False or utils.get_es().cat.indices(format='json')[0]['health'] is 'red':
            abort(503, 'Elasticsearch is not working or the index does not exist.')

        sparql_query = request.args.get('query')

        if sparql_query is not None:
            default_graph_uri = request.args.get('default-graph-uri')
            response = jsonify(search.search(sparql_query, utils.get_uri2rank(), utils.get_clusters(), default_graph_uri))
            utils.log('Search complete.')
            return response
        else:
            return "<pre><h1>Welcome to SBOLExplorer! <br> <h2>The available indices in Elasticsearch are shown below:</h2></h1><br>"\
            + str(utils.get_es().cat.indices(format='json'))\
            + "<br><br><h3>The config options are set to:</h3><br>"\
            + str(utils.get_config())\
            + "<br><br><br><br><a href=\"https://github.com/synbiodex/sbolexplorer\">Visit our GitHub repository!</a>"\
            + "<br><br>Any issues can be reported to our <a href=\"https://github.com/synbiodex/sbolexplorer/issues\">issue tracker.</a>"\
            + "<br><br>Used by <a href=\"https://github.com/synbiohub/synbiohub\">SynBioHub.</a>"
    except:
        raise

@app.route('/search', methods=['GET'])
def search_by_string():
    try:
        if utils.get_es().indices.exists(index='*,-localhost*,-.kibana') is False or utils.get_es().cat.indices(format='json')[0]['health'] is 'red':
            abort(503, 'Elasticsearch is not working or the index does not exist.')

        query = request.args.get('query')

        response = jsonify(search.search_es(query)['hits'])

        utils.log('Successfully string searched')
        return response
    except:
        raise
