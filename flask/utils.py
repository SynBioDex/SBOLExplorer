from elasticsearch import Elasticsearch
import json
import pickle
import requests
import datetime


config = None

def get_config():
    global config

    if not config:
        with open('config.json') as f:
            config = json.load(f)

    return config


def set_config(new_config):
    global config

    config = get_config()

    for key in new_config:
        if key in config:
            config[key] = new_config[key]

    with open('config.json', 'w') as f:
        json.dump(config, f)


def get_wor():
    instances = requests.get('https://wor.synbiohub.org/instances/')
    if instances.status_code != 200:
        log('[ERROR] Web of Registries had a problem!')
        return []
    return instances.json()


def get_es():
    es = Elasticsearch([get_config()['elasticsearch_endpoint']], verify_certs=True)

    if not es.ping():
        raise ValueError('Elasticsearch connection failed')

    return es


def log(message):
    log_message = '[' + str(datetime.datetime.now()) + '] ' + message + '\n'
    print(log_message)

    with open('log.txt', 'a+') as f:
        f.write(log_message)


def get_log():
    with open('log.txt', 'r') as f:
        return f.read()


clusters = None
clusters_filename = 'dumps/clusters_dump'

uri2rank = None
uri2rank_filename = 'dumps/uri2rank_dump'

def save_clusters(new_clusters):
    global clusters
    clusters = new_clusters
    serialize(clusters, clusters_filename)


def get_clusters():
    global clusters

    if clusters is None:
        clusters = deserialize(clusters_filename)

    return clusters


def save_uri2rank(new_uri2rank):
    global uri2rank
    uri2rank = new_uri2rank
    serialize(uri2rank, uri2rank_filename)


def get_uri2rank():
    global uri2rank

    if uri2rank is None:
        uri2rank = deserialize(uri2rank_filename)

    return uri2rank


def serialize(data, filename):
    f = open(filename, 'wb')
    pickle.dump(data, f)
    f.close()


def deserialize(filename):
    f = open(filename, 'rb')
    data = pickle.load(f)
    f.close()
    return data


