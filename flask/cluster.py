from xml.etree import ElementTree
import subprocess
import utils


uclust_identity = utils.get_config()['uclust_identity'] # how similar sequences in the same cluster must be
sequences_filename = 'usearch/sequences.fsa'
usearch_binary_filename = 'usearch/usearch10.0.240_i86linux32'
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


def create_sequences(sequences_response):
    sequences = {}
    
    ns = {'sparql_results': 'http://www.w3.org/2005/sparql-results#'}
    
    root = ElementTree.fromstring(sequences_response)
    results = root.find('sparql_results:results', ns)

    for result in results.findall('sparql_results:result', ns):
        bindings = result.findall('sparql_results:binding', ns)

        for binding in bindings:
            if binding.attrib['name'] == 'subject':
                subject = binding.find('sparql_results:uri', ns).text

        for binding in bindings:
            if binding.attrib['name'] == 'sequence':
                sequence = binding.find('sparql_results:literal', ns).text

        sequences[subject] = sequence
    
    return sequences


def write_fasta(sequences):
    f = open(sequences_filename, 'w')
    
    for subject in sequences.keys():
        f.write('>%s\n' % subject)
        f.write('%s\n' % sequences[subject])
    
    f.close()
    

def run_uclust():
    args = [usearch_binary_filename, '-cluster_fast', sequences_filename, '-id', uclust_identity, '-sort', 'length', '-uc', uclust_results_filename]
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    output = popen.stdout.read()
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
    print('parts: ' + str(total_parts))
    print('hits: ' + str(hits))
    print('average hit identity: ' + str(total_identity / hits))


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
    print('Query for sequences')
    sequences_response = utils.query_sparql(sequence_query)
    print('Query for sequences complete')
    sequences = create_sequences(sequences_response)
    write_fasta(sequences)

    print('Running uclust')
    #run_uclust() # TODO uncomment this on working machine
    print('Running uclust complete')

    analyze_uclust()
    return uclust2clusters()

