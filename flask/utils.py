from elasticsearch import Elasticsearch
import json
import pickle
import requests
import datetime
import subprocess
import os

config = None

def get_config():
    """
    Gets a copy of the config file
    Returns: Config file in JSON

    """
    global config

    if not config:
        with open('config.json') as f:
            config = json.load(f)

    return config


def set_config(new_config):
    """
    Overwrites the existing config with a new config file
    Args:
        new_config: New config file with the updated information

    Returns:

    """
    global config

    config = get_config()

    for key in new_config:
        if key in config:
            config[key] = new_config[key]

    with open('config.json', 'w') as f:
        json.dump(config, f)


def save_time(attribute):
    """
    Saves the current time to an attribute in the config
    Args:
        attribute: Config attribute to save current time to

    Returns:

    """
    config = get_config()

    now = datetime.datetime.now()

    config[attribute] = str(now)

    set_config(config)

def save_update_end_time():
    """
    Save end time of indexing
    Returns:

    """
    save_time("last_update_end")


def save_update_start_time():
    """
    Save start time of indexing
    Returns:

    """
    save_time("last_update_start")
        

def get_wor():
    """
    Gets all instances of SynBioHub from the Web of Registries
    Returns:

    """
    try: 
        instances = requests.get('https://wor.synbiohub.org/instances/')
    except Exception:
        log('[ERROR] Web of Registries had a problem!')
        return []

    if instances.status_code != 200:
        log('[ERROR] Web of Registries had a problem!')
        return []

    return instances.json()


def get_es():
    """
    Gets an instance of elasticsearch
    Returns: The instance of elasticsearch

    """
    es = Elasticsearch([get_config()['elasticsearch_endpoint']], verify_certs=True)

    if not es.ping():
        raise ValueError('Elasticsearch connection failed')

    return es


def log(message):
    """
    Writes a message to the log
    Args:
        message: Message to write

    Returns:

    """
    log_message = '[' + str(datetime.datetime.now()) + '] ' + message + '\n'
    print(log_message)

    if os.path.exists('log.txt') and os.path.getsize('log.txt') > 20000000: # Delete the log if it is > 20 MB
        os.remove('log.txt')

    with open('log.txt', 'a+') as f:
        f.write(log_message)

def log_indexing(message):
    log_message = '[' + str(datetime.datetime.now()) + '] ' + message + '\n'
    print(log_message)

    if os.path.exists('indexing_log.txt') and os.path.getsize('indexing_log.txt') > 20000000: # Delete the log if it is > 20 MB
        os.remove('indexing_log.txt')

    with open('indexing_log.txt', 'a+') as f:
        f.write(log_message)

def get_log():
    """
    Gets a copy of the log
    Returns: Stream from the read() method

    """
    with open('log.txt', 'r') as f:
        return f.read()

def get_indexing_log():
    with open('indexing_log.txt', 'r') as f:
        return f.read()

clusters = None
clusters_filename = 'dumps/clusters_dump'

uri2rank = None
uri2rank_filename = 'dumps/uri2rank_dump'


def save_clusters(new_clusters):
    """
    Save clusters of parts
    Args:
        new_clusters: Clusters to be saved

    Returns:

    """
    global clusters
    clusters = new_clusters
    serialize(clusters, clusters_filename)


def get_clusters():
    """
    Gets all clusters of parts
    Returns:

    """
    global clusters

    if clusters is None:
        clusters = deserialize(clusters_filename)

    return clusters


def save_uri2rank(new_uri2rank):
    """
    Saves the pagerank of all URI's
    Args:
        new_uri2rank:

    Returns:

    """
    global uri2rank
    uri2rank = new_uri2rank
    serialize(uri2rank, uri2rank_filename)


def get_uri2rank():
    """
    Gets all pageranks of URI's
    Returns:

    """
    global uri2rank

    if uri2rank is None:
        uri2rank = deserialize(uri2rank_filename)

    return uri2rank


def serialize(data, filename):
    """
    Serializes some data to a file
    Args:
        data: Data to be written
        filename: File to be written to

    Returns:

    """
    f = open(filename, 'wb')
    pickle.dump(data, f)
    f.close()


def deserialize(filename):
    """
    Deserializes data from a serialized file
    Args:
        filename: Serialized file

    Returns: Deserialized data from file

    """
    if not os.path.exists(filename):
        return {}

    f = open(filename, 'rb')
    data = pickle.load(f)
    f.close()
    return data
    