from logger import Logger
import query

logger_ = Logger()
sequences_filename = 'dumps/sequences.fsa'

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


def uclust2uris(fileName):
    uris = set()
    with open(fileName, 'r') as f:
        for line in f:
            parts = line.split()
            if parts[0] == 'H':
                uris.add(parts[9])
    return uris

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
