from xml.etree import ElementTree
import subprocess
import utils
import query
import cluster
from sys import platform



if platform == "linux" or platform == "linux2":
    vsearch_binary_filename = 'usearch/vsearch_linux'
elif platform == "darwin":
    vsearch_binary_filename = 'usearch/vsearch_macos'
else:
    print("Sorry, your OS is not supported for sequence based-search.")
    
defaultFlags = {'maxAccepts': '50', 'id': '0.8'}

def write_to_fasta(sequence):
    f = open('usearch/searchsequence.fsa', 'w')
    f.write('>sequence_to_search\n')
    f.write('%s\n' % sequence)
    f.close()

def get_flags(userFlags):
    for flag in userFlags:
        if flag in defaultFlags:
            defaultFlags[flag] = userFlags[flag]


# pass in the sequence to this function, replace searchsequence.fsa with the query sequence
def run_vsearch_global():
    # setting maxaccepts to 0 disables the limit (searches for all possible matches)
    args = [vsearch_binary_filename, '--usearch_global', 'usearch/searchsequence.fsa', '--db', 'usearch/sequences.fsa', '--id', defaultFlags['id'], '--dbmatched', 'usearch/sbsearch_results.fsa', '--uc', 'usearch/sbsearch_uctable.uc', '--uc_allhits', '--maxaccepts', defaultFlags['maxAccepts']]
    #args = [vsearch_binary_filename, '--search_exact', 'usearch/searchsequence.fsa', '--db', 'usearch/sequences.fsa', '--dbmatched', 'usearch/sbsearch_results.fsa', '--uc', 'usearch/sbsearch_uctable.uc', '--uc_allhits']
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    output = popen.stdout.read()
    print(output)

def run_vsearch_exact():
    # setting maxaccepts to 0 disables the limit (searches for all possible matches)
    args = [vsearch_binary_filename, '--search_exact', 'usearch/searchsequence.fsa', '--db', 'usearch/sequences.fsa', '--dbmatched', 'usearch/sbsearch_results.fsa', '--uc', 'usearch/sbsearch_uctable.uc', '--uc_allhits']
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    output = popen.stdout.read()
    print(output)


def sequence_search(flags):
    get_flags(flags)
    utils.log('Starting sequence search')
    if flags['exactSearch'] == True:
        run_vsearch_exact()
    else:
        run_vsearch_global()
    utils.log('Sequence search complete')

    return cluster.uclust2uris()

