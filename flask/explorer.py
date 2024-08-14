#!/usr/bin/python3

from flask import Flask, request, jsonify, abort, render_template
from werkzeug.exceptions import HTTPException

import os
import traceback
import logging
import cluster
import pagerank
import index
import search
import utils
import query

import threading
import time
from flask_debugtoolbar import DebugToolbarExtension
from flask_debugtoolbar_lineprofilerpanel.profile import line_profile


def profile_flask_app():
    app.run(debug=True)

if __name__ == "__main__":
    #profiler = profile.Profile()
    #profiler.enable()
    profile_flask_app()
    #profiler.disable()
    #profiler.print_stats(sort='time')
    
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Required for the debug toolbar
app.config['DEBUG'] = True
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = False
# Profiler configuration
app.config['DEBUG_TB_PROFILER_ENABLED'] = True
app.config['DEBUG_TB_PANELS'] = [
    'flask_debugtoolbar.panels.versions.VersionDebugPanel',
    'flask_debugtoolbar.panels.timer.TimerDebugPanel',
    'flask_debugtoolbar.panels.headers.HeaderDebugPanel',
    'flask_debugtoolbar.panels.request_vars.RequestVarsDebugPanel',
    'flask_debugtoolbar.panels.config_vars.ConfigVarsDebugPanel',
    'flask_debugtoolbar.panels.template.TemplateDebugPanel',
    'flask_debugtoolbar.panels.logger.LoggingPanel',
    'flask_debugtoolbar.panels.profiler.ProfilerDebugPanel',
    'flask_debugtoolbar_lineprofilerpanel.panels.LineProfilerPanel'
]

# Initialize the debug toolbar
toolbar = DebugToolbarExtension(app)


@app.errorhandler(Exception)
def handle_error(e):
    utils.log('[ERROR] Returning error ' + str(e) + "\n Traceback:\n" + traceback.format_exc())

    if isinstance(e, HTTPException):
        return jsonify(error=str(e.name + ": " + e.description)), e.code
    else:
        return jsonify(error=str(type(e).__name__) + str(e)), 500

@app.before_first_request
def startup():
    # Method for running auto indexing
    def auto_update_index():
        while True:
            time.sleep(int(utils.get_config()['updateTimeInDays']) * 86400)
            # if utils.get_config()['autoUpdateIndex'] and utils.get_config()['updateTimeInDays'] > 0:
            #     utils.log('Updating index automatically. To disable, set the \"autoUpdateIndex\" property in config.json to false.')
            #     update()

    # Thread for automatically updaing the index periodically
    update_thread = threading.Thread(target=auto_update_index, daemon=True)
    update_thread.start()

    if os.path.exists('log.txt') and os.path.getsize('log.txt') > 20000000: # Delete the log if it is > 20 MB
            os.remove('log.txt')
    
    if os.path.exists('indexing_log.txt') and os.path.getsize('indexing_log.txt') > 20000000: # Delete the log if it is > 20 MB
        os.remove('indexing_log.txt')

    utils.log('SBOLExplorer started :)')

    try:
        if utils.get_es().indices.exists(index=utils.get_config()['elasticsearch_index_name']) is False:
            utils.log('Index not found, creating new index.')
            update()
    except:
        raise

@app.errorhandler(Exception)
def handle_error(e):
    utils.log('[ERROR] Returning error ' + str(e) + "\n Traceback:\n" + traceback.format_exc())
    return jsonify(error=str(e)), 500   

@app.route('/info', methods=['GET'])
def info():
    utils.log('Explorer up!!! Virtutoso ' + str(query.memoized_query_sparql.cache_info()))
    return utils.get_log()

@app.route('/indexinginfo', methods=['GET'])
def indexinginfo():
    return utils.get_indexing_log()

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
            utils.log_indexing('============ STARTING INDEXING ============\n\n')
            utils.log('============ STARTING INDEXING ============\n\n')
            utils.save_update_start_time()

            clusters = cluster.update_clusters()
            utils.save_clusters(clusters)
            
            
            uri2rank = pagerank.update_pagerank()
            utils.save_uri2rank(uri2rank)

            index.update_index(utils.get_uri2rank())
            
            query.memoized_query_sparql.cache_clear()
            utils.log_indexing('Cache cleared')

            utils.save_update_end_time()
            success_message = 'Successfully updated entire index'
        else:
            index.refresh_index(subject, utils.get_uri2rank())
            success_message = 'Successfully refreshed: ' + subject

        utils.log_indexing('============ INDEXING COMPLETED ============\n\n')
        utils.log('============ INDEXING COMPLETED ============\n\n')
        return success_message
    except Exception as e:
    	utils.log_indexing('[ERROR] Returning error ' + str(e) + "\n Traceback:\n" + traceback.format_exc())


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

@app.route('/test', methods=['GET'])
@line_profile
def SBOLExplore_test_endpoint():
    return render_template('index.html')

@app.route('/', methods=['GET'])
@line_profile
def sparql_search_endpoint():
    try:
        # make sure index is built, or throw exception
        if utils.get_es().indices.exists(index=utils.get_config()['elasticsearch_index_name']) is False or utils.get_es().cat.indices(format='json')[0]['health'] is 'red':
            abort(503, 'Elasticsearch is not working or the index does not exist.')

        sparql_query = request.args.get('query')

        if sparql_query is not None:
            default_graph_uri = request.args.get('default-graph-uri')
            response = jsonify(
                search.search(
                    sparql_query, 
                    utils.get_uri2rank(), 
                    utils.get_clusters(), 
                    default_graph_uri
                    ))
            return response
        else:
            return "<pre><h1>Welcome to SBOLExplorer! <br> <h2>The available indices in Elasticsearch are shown below:</h2></h1><br>"\
            + str(utils.get_es().cat.indices(format='json'))\
            + "<br><br><h3>The config options are set to:</h3><br>"\
            + str(utils.get_config())\
            + "<br><br><br><br><a href=\"https://github.com/synbiodex/sbolexplorer\">Visit our GitHub repository!</a>"\
            + "<br><br>Any issues can be reported to our <a href=\"https://github.com/synbiodex/sbolexplorer/issues\">issue tracker.</a>"\
            + "<br><br>Used by <a href=\"https://github.com/synbiohub/synbiohub\">SynBioHub.</a>"
            #return render_template('index.html')
    except:
        raise

@app.route('/search', methods=['GET'])
def search_by_string():
    try:
        if utils.get_es().indices.exists(index=utils.get_config()['elasticsearch_index_name']) is False or utils.get_es().cat.indices(format='json')[0]['health'] is 'red':
            abort(503, 'Elasticsearch is not working or the index does not exist.')

        query = request.args.get('query')

        response = jsonify(search.search_es(query)['hits'])

        return response
    except:
        raise
