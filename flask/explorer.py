#!/usr/bin/python3

from flask import Flask, request, jsonify, abort, render_template
from werkzeug.exceptions import HTTPException
import os
import traceback
import logging
import threading
import time
import cluster
import pagerank
import index
import search
import query
from configManager import ConfigManager
from dataManager import DataManager
from elasticsearchManager import ElasticsearchManager
from logger import Logger


# Configure logging, This will affect all loggers in your application, not just the Werkzeug logger.
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

config_manager = ConfigManager()
data_manager = DataManager()
elasticsearch_manager = ElasticsearchManager(config_manager)
logger_ = Logger()

app = Flask(__name__)


# Error handler
@app.errorhandler(Exception)
def handle_error(e):
    log.error(f'[ERROR] Returning error {e}\n Traceback:\n{traceback.format_exc()}')
    if isinstance(e, HTTPException):
        return jsonify(error=str(e.name + ": " + e.description)), e.code
    return jsonify(error=str(type(e).__name__) + str(e)), 500

def startup():
    def auto_update_index():
        update_interval = int(config_manager.load_config().get('updateTimeInDays', 0)) * 86400
        while True:
            time.sleep(update_interval)
            # Implement your update logic here
            if config_manager.load_config().get('autoUpdateIndex', False):
                update_index()

    # Start the background thread for auto-updating the index
    update_thread = threading.Thread(target=auto_update_index, daemon=True)
    update_thread.start()

    # Manage log file sizes
    for log_file in ['log.txt', 'indexing_log.txt']:
        if os.path.exists(log_file) and os.path.getsize(log_file) > 20000000:  # 20 MB
            os.remove(log_file)

    logger_.log('SBOLExplorer started :)')

    # Check and create index if necessary
    try:
        es = elasticsearch_manager.get_es()
        index_name = config_manager.load_config().get('elasticsearch_index_name')
        if not es.indices.exists(index=index_name):
            logger_.log('Index not found, creating new index.')
            update_index()
    except Exception as e:
        log.error(f'Error during startup: {e}')
        raise
    
startup()

def update_index():
    logger_.log('============ STARTING INDEXING ============\n\n', True)
    config_manager.save_update_start_time()

    clusters = cluster.update_clusters()
    data_manager.save_clusters(clusters)
    
    uri2rank = pagerank.update_pagerank()
    data_manager.save_uri2rank(uri2rank)

    index.update_index(data_manager.get_uri2rank())
    
    query.memoized_query_sparql.cache_clear()
    logger_.log('Cache cleared', True)

    config_manager.save_update_end_time()
    logger_.log('============ INDEXING COMPLETED ============\n\n', True)

@app.route('/info', methods=['GET'])
def info():
    logger_.log('Explorer up!!! Virtuoso ' + str(query.memoized_query_sparql.cache_info()))
    return logger_.get_log()

@app.route('/indexinginfo', methods=['GET'])
def indexinginfo():
    return logger_.get_indexing_log()

@app.route('/config', methods=['POST', 'GET'])
def config_route():
    if request.method == 'POST':
        new_config = request.get_json()
        config_manager.save_config(new_config)
        logger_.log('Successfully updated config')

    return jsonify(config_manager.load_config())

@app.route('/update', methods=['GET'])
def update():
    try:
        subject = request.args.get('subject')
        if subject:
            index.refresh_index(subject, data_manager.get_uri2rank())
            success_message = f'Successfully refreshed: {subject}'
        else:
            update_index()
            success_message = 'Successfully updated entire index'
        return success_message
    except Exception as e:
        log.error(f'Error during update: {e}')
        raise

@app.route('/incrementalupdate', methods=['POST'])
def incremental_update():
    try:
        updates = request.get_json()
        index.incremental_update(updates, data_manager.get_uri2rank())
        success_message = 'Successfully incrementally updated parts'
        logger_.log(success_message)
        return success_message
    except Exception as e:
        log.error(f'Error during incremental update: {e}')
        raise

@app.route('/incrementalremove', methods=['GET'])
def incremental_remove():
    try:
        subject = request.args.get('subject')
        index.incremental_remove(subject)
        success_message = f'Successfully incrementally removed: {subject}'
        logger_.log(success_message)
        return success_message
    except Exception as e:
        log.error(f'Error during incremental remove: {e}')
        raise

@app.route('/incrementalremovecollection', methods=['GET'])
def incremental_remove_collection():
    try:
        subject = request.args.get('subject')
        uri_prefix = request.args.get('uriPrefix')
        index.incremental_remove_collection(subject, uri_prefix)
        success_message = f'Successfully incrementally removed collection and members: {subject}'
        logger_.log(success_message)
        return success_message
    except Exception as e:
        log.error(f'Error during incremental remove collection: {e}')
        raise

@app.route('/test', methods=['GET'])
def SBOLExplore_test_endpoint():
    return render_template('index.html')

@app.route('/', methods=['GET'])
def sparql_search_endpoint():
    try:
        es = elasticsearch_manager.get_es()
        index_name = config_manager.load_config().get('elasticsearch_index_name')
        if not es.indices.exists(index=index_name) or es.cat.indices(format='json')[0]['health'] == 'red':
            abort(503, 'Elasticsearch is not working or the index does not exist.')

        sparql_query = request.args.get('query')
        if sparql_query:
            default_graph_uri = request.args.get('default-graph-uri')
            response = jsonify(search.search(
                sparql_query, 
                data_manager.get_uri2rank(), 
                data_manager.get_clusters(), 
                default_graph_uri
            ))
            return response
        return "<pre><h1>Welcome to SBOLExplorer! <br> <h2>The available indices in Elasticsearch are shown below:</h2></h1><br>"\
            + str(elasticsearch_manager.get_es().cat.indices(format='json'))\
            + "<br><br><h3>The config options are set to:</h3><br>"\
            + str(config_manager.load_config())\
            + "<br><br><br><br><a href=\"https://github.com/synbiodex/sbolexplorer\">Visit our GitHub repository!</a>"\
            + "<br><br>Any issues can be reported to our <a href=\"https://github.com/synbiodex/sbolexplorer/issues\">issue tracker.</a>"\
            + "<br><br>Used by <a href=\"https://github.com/synbiohub/synbiohub\">SynBioHub.</a>"
            
    except Exception as e:
        log.error(f'Error during SPARQL search: {e}')
        raise

@app.route('/search', methods=['GET'])
def search_by_string():
    try:
        es = elasticsearch_manager.get_es()
        index_name = config_manager.load_config().get('elasticsearch_index_name')
        if not es.indices.exists(index=index_name) or es.cat.indices(format='json')[0]['health'] == 'red':
            abort(503, 'Elasticsearch is not working or the index does not exist.')

        query = request.args.get('query')
        response = jsonify(search.search_es(query)['hits'])
        return response
    except Exception as e:
        log.error(f'Error during search by string: {e}')
        raise

if __name__ == "__main__":
    app.run(debug=False, threaded=True) # threaded=True
