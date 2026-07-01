from xml.etree import ElementTree
import os
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
    if whichSearch == 'vsearch':
        args = [usearch_binary_filename, '--cluster_fast', sequences_filename, '--id', uclust_identity, '--uc',
                uclust_results_filename]
    else:
        args = [usearch_binary_filename, '-cluster_fast', sequences_filename, '-id', uclust_identity, '-sort', 'length',
                '-uc', uclust_results_filename]
    logger_.log(f'******** Running {whichSearch} clustering with identity {uclust_identity} ********', True)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    for line in proc.stderr:
        line = line.strip()
        if line:
            logger_.log(line, True)
    proc.wait()
    if proc.returncode != 0:
        logger_.log(f'******** ERROR: {whichSearch} clustering failed with exit code {proc.returncode} ********', True)
        raise RuntimeError(f'clustering ({whichSearch}) failed (exit {proc.returncode}) — see indexing log for details')
    if not os.path.exists(uclust_results_filename) or os.path.getsize(uclust_results_filename) == 0:
        raise RuntimeError(f'{whichSearch} clustering produced no output — {uclust_results_filename} is missing or empty')
    logger_.log('******** Clustering completed successfully ********', True)


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

def hash_exact_duplicates(sequences):
    """
    Groups sequences by exact match to identify duplicates.
    Returns a dictionary of URIs mapped to the full group set (including self).
    Callers must exclude the key URI when iterating.

    Arguments:
        sequences {list} -- A list of sequences.

    Returns:
        dict -- A dictionary mapping URIs to their duplicate group set.
    """
    seq_to_uris = {}
    for sequence in sequences:
        seq_to_uris.setdefault(sequence['sequence'], set()).add(sequence['subject'])

    duplicates = {}
    for uris in seq_to_uris.values():
        if len(uris) > 1:
            for uri in uris:
                duplicates[uri] = uris  # shared set reference — callers must exclude self
    return duplicates

def update_clusters():
    logger_.log('------------ Updating clusters ------------', True)

    logger_.log('******** Query for sequences ********', True)
    sequences_response = query.query_sparql(sequence_query)
    logger_.log('******** Query for sequences complete ********', True)
    write_fasta(sequences_response)

    clusters = hash_exact_duplicates(sequences_response)
    logger_.log(f'******** Found {len(clusters)} URIs with exact duplicates ********', True)

    return clusters



# def update_clusters():
#     logger_.log('------------ Updating clusters ------------', True)
#
#     # Re-read config (force a fresh load, not the value cached at import) so a
#     # flag set at runtime via /config is honored. skip_clustering DEFAULTS TO
#     # TRUE: the (very slow) uclust run is skipped and the previous clusters are
#     # reused unless config explicitly sets skip_clustering to false. This lets
#     # deployments (e.g. Azure) that can't edit config.json avoid the multi-hour
#     # clustering by default; a frontend can later set it false to force a rerun.
#     config_manager._config = None
#     if config_manager.load_config().get('skip_clustering', True):
#         logger_.log('******** skip_clustering=true: skipping uclust, reusing previous clusters ********', True)
#         logger_.log('------------ Clustering skipped (previous clusters kept) ------------\n', True)
#         return None
#
#     logger_.log('******** Query for sequences ********', True)
#     sequences_response = query.query_sparql(sequence_query)
#     logger_.log('******** Query for sequences complete ********', True)
#     write_fasta(sequences_response)
#
#     logger_.log('******** Running uclust ********', True)
#     run_uclust()
#     logger_.log('******** Running uclust complete ********', True)
#
#     analyze_uclust()
#     logger_.log('------------ Successfully updated clusters ------------\n', True)
#     return uclust2clusters()
