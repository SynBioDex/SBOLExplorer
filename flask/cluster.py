from xml.etree import ElementTree
import subprocess
import utils
import query
from sys import platform


uclust_identity = utils.get_config()['uclust_identity'] # how similar sequences in the same cluster must be
sequences_filename = 'usearch/sequences.fsa'

if platform == "linux" or platform == "linux2":
    usearch_binary_filename = 'usearch/usearch10.0.240_i86linux32'
elif platform == "darwin":
    usearch_binary_filename = 'usearch/usearch11.0.667_i86osx32'
else:
    print("Sorry, your OS is not supported by usearch.")

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
    #utils.log(output)  # This is giving error "must be str, not bytes"?
    print(output)


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
    utils.log('parts: ' + str(total_parts))
    utils.log('hits: ' + str(hits))

    if hits > 0:
        utils.log('average hit identity: ' + str(total_identity / hits))


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
    utils.log('Query for sequences')
    sequences_response = query.query_sparql(sequence_query)
    utils.log('Query for sequences complete')
    write_fasta(sequences_response)

    utils.log('Running uclust')
    run_uclust()
    utils.log('Running uclust complete')

    analyze_uclust()
    return uclust2clusters()

