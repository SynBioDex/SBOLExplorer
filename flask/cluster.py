from xml.etree import ElementTree
import subprocess
from configManager import ConfigManager
from logger import Logger
import query
from sys import platform

config_manager = ConfigManager()
config = config_manager.load_config()  # Load config once
uclust_identity = config['uclust_identity']  # Get the uclust identity value
logger_ = Logger()
sequences_filename = 'dumps/sequences.fsa'

# Ensure 'which_search' is set in config
if 'which_search' not in config:
    config['which_search'] = 'vsearch'
    config_manager.save_config(config)

whichSearch = config['which_search']

# Determine the correct binary filename based on OS and search tool
usearch_binary_filename = None
if platform.startswith("linux"):
    usearch_binary_filename = 'usearch/vsearch_linux' if whichSearch == 'vsearch' else 'usearch/usearch10.0.240_i86linux32'
elif platform == "darwin":
    usearch_binary_filename = 'usearch/vsearch_macos' if whichSearch == 'vsearch' else 'usearch/usearch11.0.667_i86osx32'
else:
    logger_.log("Sorry, your OS is not supported for sequence-based search.")
    raise SystemExit

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
    with open(sequences_filename, 'w') as f:
        for sequence in sequences:
            f.write(f">{sequence['subject']}\n{sequence['sequence']}\n")

def run_uclust():
    args = [usearch_binary_filename, '-cluster_fast', sequences_filename, '-id', uclust_identity, '-sort', 'length', '-uc', uclust_results_filename]
    result = subprocess.run(args, capture_output=True, text=True)
    logger_.log(result.stdout, True)

def analyze_uclust():
    total_parts = 0
    total_identity = 0.0
    hits = 0

    with open(uclust_results_filename, 'r') as f:
        for line in f:
            parts = line.split()
            record_type = parts[0]
            if record_type in ('H', 'S'):
                total_parts += 1
                if record_type == 'H':
                    total_identity += float(parts[3])
                    hits += 1

    logger_.log(f'parts: {total_parts}', True)
    logger_.log(f'hits: {hits}', True)
    if hits > 0:
        logger_.log(f'average hit identity: {total_identity / hits}', True)

def uclust2uris(fileName):
    uris = set()
    with open(fileName, 'r') as f:
        for line in f:
            parts = line.split()
            if parts[0] == 'H':
                uris.add(parts[9])
    return uris

def uclust2clusters():
    cluster2parts = {}
    
    with open(uclust_results_filename, 'r') as f:
        for line in f:
            parts = line.split()
            if parts[0] in ('H', 'S'):
                part, cluster = parts[8], parts[1]
                if cluster not in cluster2parts:
                    cluster2parts[cluster] = set()
                cluster2parts[cluster].add(part)

    clusters = {part: parts.difference({part}) for cluster, parts in cluster2parts.items() for part in parts}

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
    logger_.log('------------ Successfully updated clusters ------------\n', True)
    return uclust2clusters()
