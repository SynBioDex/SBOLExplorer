import hashlib
import os
import subprocess
import tempfile
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

def load_sequence_hashes():
    """
    Load existing sequences from sequences_filename into hash {uri: sha256(sequence)}

    Returns:
        sequence_hashes {dict} -- dictionary of uri to sha256 hash of sequence
    """
    sequence_hashes = {}
    with open(sequences_filename, 'r') as f:
        for line in f:
            if line.startswith('>'):
                uri = line[1:].strip()
            else:
                sequence = line.strip()
                sequence_hashes[uri] = hashlib.sha256(sequence.encode()).hexdigest()
    return sequence_hashes

def find_new_sequences(sequence_response, existing_hashes):
    """
    Find new sequences that are not in existing_hashes

    Arguments:
        sequence_response {list} -- list of sequences from query
        existing_hashes {dict} -- dictionary of uri to sha256 hash of sequence

    Returns:
        list -- list of new sequences
    """
    new_sequences = []
    for sequence in sequence_response:
        uri = sequence['subject']
        seq = sequence['sequence']
        seq_hash = hashlib.sha256(seq.encode()).hexdigest()
        if uri not in existing_hashes or existing_hashes[uri] != seq_hash:
            new_sequences.append(sequence)
    return new_sequences

def run_incremental_uclust(new_sequences_filename):
    """
    Runs --usearch_global on only the new sequences against the existing corpus and appends results to uclust_results_filename.

    Arguments:
        new_sequences_filename {str} -- path to FASTA file containing only new/changed sequences
    """
    with tempfile.NamedTemporaryFile(suffix='.uc', delete=False, mode='w') as tmp:
        tmp_uc = tmp.name

    args = [usearch_binary_filename, '--usearch_global', new_sequences_filename,
            '--db', sequences_filename, '--uc', tmp_uc, '--uc_allhits',
            '--id', str(uclust_identity), '--iddef', '2',
            '--maxaccepts', '50', '--maxrejects', '0',
            '--maxseqlength', '5000', '--minseqlength', '20']

    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    logger_.log(result.stdout, True)
    logger_.log(result.stderr, True)

    with open(tmp_uc, 'r') as src, open(uclust_results_filename, 'a') as dst:
        for line in src:
            parts = line.split()
            if parts[0] in ('H', 'S'):
                dst.write(line)

    os.unlink(tmp_uc)


def append_to_fasta(new_sequences):
    """
    Appends new sequences to sequences.fsa without overwriting existing content.

    Arguments:
        new_sequences {list} -- list of new/changed sequence dicts with 'subject' and 'sequence' keys
    """
    with open(sequences_filename, 'a') as f:
        for sequence in new_sequences:
            f.write(f">{sequence['subject']}\n{sequence['sequence']}\n")

def run_uclust():
    args = [usearch_binary_filename, '--cluster_fast', sequences_filename, '--id', uclust_identity, '--uc', uclust_results_filename]
    # result = subprocess.run(args, capture_output=True, text=True) # Python3.7
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    logger_.log(result.stdout, True)
    logger_.log(result.stderr, True)

def analyze_uclust():
    total_parts = 0
    total_identity = 0.0
    hits = 0

    with open(uclust_results_filename, 'r') as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
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
            if not parts or parts[0] not in ('H', 'S') or len(parts) < 10:
                continue
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

    if not os.path.exists(sequences_filename) or not os.path.exists(uclust_results_filename):
        logger_.log('******** No existing cluster data — running full cluster ********', True)
        write_fasta(sequences_response)
        run_uclust()
    else:
        existing_hashes = load_sequence_hashes()
        new_sequences = find_new_sequences(sequences_response, existing_hashes)

        if not new_sequences:
            logger_.log('******** No new sequences — skipping cluster ********', True)
        else:
            logger_.log(f'******** {len(new_sequences)} new/changed sequences — running incremental cluster ********', True)
            with tempfile.NamedTemporaryFile(suffix='.fsa', delete=False, mode='w') as tmp:
                tmp_fasta = tmp.name
                for seq in new_sequences:
                    tmp.write(f">{seq['subject']}\n{seq['sequence']}\n")
            run_incremental_uclust(tmp_fasta)
            os.unlink(tmp_fasta)
            append_to_fasta(new_sequences)

    logger_.log('******** Running uclust complete ********', True)
    analyze_uclust()
    logger_.log('------------ Successfully updated clusters ------------\n', True)
    return uclust2clusters()
