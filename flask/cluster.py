from xml.etree import ElementTree
import subprocess
from configManager import ConfigManager
from logger import Logger
import query
from sys import platform

config_manager = ConfigManager()
uclust_identity = config_manager.load_config()['uclust_identity'] # how similar sequences in the same cluster must be
logger_ = Logger()
sequences_filename = 'dumps/sequences.fsa'

if 'which_search' not in config_manager.load_config():
    explorerConfig = config_manager.load_config()
    explorerConfig['which_search'] = 'vsearch'
    config_manager.load_config(explorerConfig)

whichSearch = config_manager.load_config()['which_search']

if platform == "linux" or platform == "linux2":
    if whichSearch == 'usearch':
        usearch_binary_filename = 'usearch/usearch10.0.240_i86linux32'
    elif whichSearch == 'vsearch':
        usearch_binary_filename = 'usearch/vsearch_linux'
elif platform == "darwin":
    if whichSearch == 'usearch':
        usearch_binary_filename = 'usearch/usearch11.0.667_i86osx32'
    elif whichSearch == 'vsearch':
        usearch_binary_filename = 'usearch/vsearch_macos'
else:
    logger_.log("Sorry, your OS is not supported for sequence based-search.")

uclust_results_filename = 'usearch/uclust_results.uc'

sequence_query = '''
SELECT ?subject ?sequence
WHERE {
    ?subject a sbol2:ComponentDefinition .
    ?subject sbol2:sequence ?seq .
    ?seq a sbol2:Sequence .
    ?seq sbol2:elements ?sequence .
}
'''


def write_fasta(sequences):
    f = open(sequences_filename, 'w')
    
    for sequence in sequences:
        f.write('>%s\n' % sequence['subject'])
        f.write('%s\n' % sequence['sequence'])
    
    f.close()
    

def run_uclust():
    args = [usearch_binary_filename, '-cluster_fast', sequences_filename, '-id', uclust_identity, '-sort', 'length', '-uc', uclust_results_filename]
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    output = popen.stdout.read()
    logger_.log(str(output), True)


def analyze_uclust():
    f = open(uclust_results_filename, 'r')
    results = f.read()
    
    total_parts = 0
    total_identity = 0.0
    hits = 0

    lines = results.splitlines()
    for line in lines:
        line = line.split()
        record_type = line[0]
        
        if record_type in ('H', 'S'):
            total_parts += 1

            if line[0] is 'H':
                total_identity += float(line[3])
                hits += 1
    
    f.close()
    logger_.log('parts: ' + str(total_parts), True)
    logger_.log('hits: ' + str(hits), True)

    if hits > 0:
        logger_.log('average hit identity: ' + str(total_identity / hits), True)


def uclust2uris(fileName):
    uris = set()
    
    f = open(fileName, 'r')
    results = f.read()
    lines = results.splitlines()

    for line in lines:
        line = line.split()
        
        if line[0] is 'H':
            partURI = line[9]

            uris.add(partURI)

    f.close()

    return uris

def uclust2clusters():
    # populate cluster2parts
    cluster2parts = {}
    
    f = open(uclust_results_filename, 'r')
    results = f.read()
    lines = results.splitlines()

    for line in lines:
        line = line.split()
        
        if line[0] is 'H' or line[0] is 'S':
            part, cluster = line[8], line[1]

            if cluster not in cluster2parts:
                cluster2parts[cluster] = set()
            cluster2parts[cluster].add(part)

    f.close()

    # transform cluster2parts to clusters
    clusters = {}

    for cluster in cluster2parts:
        parts = cluster2parts[cluster]
        for part in parts:
            clusters[part] = parts.difference({part})

    return clusters


def update_clusters():
    logger_.log('------------ Updating clusters ------------', True)
    logger_.log('******** Query for sequences ********', True)
    sequences_response = query.query_sparql(sequence_query)
    logger_.log('******** Query for sequences complete ********', True)
    write_fasta(sequences_response)

    logger_.log('******** Running uclust ********', True)
    run_uclust()
    logger_.log('******** Running uclust complete ********', True)

    analyze_uclust()
    logger_.log('------------ Successsfully updated clusters ------------\n', True)
    return uclust2clusters()

