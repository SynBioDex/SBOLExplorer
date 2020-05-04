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

# add valid flags to here
globalFlags = {'maxaccepts': '50', 'id': '0.8', 'iddef': '2', 'maxrejects': '0', 'maxseqlength': '5000', 'minseqlength': '20'}
exactFlags = {}

def write_to_fasta(sequence):
    f = open('usearch/searchsequence.fsa', 'w')
    f.write('>sequence_to_search\n')
    f.write('%s\n' % sequence)
    f.close()


# pass in the sequence to this function, replace searchsequence.fsa with the query sequence
def run_vsearch_global():
    # setting maxaccepts to 0 disables the limit (searches for all possible matches)
    args = [vsearch_binary_filename, '--usearch_global', 'usearch/searchsequence.fsa', '--db', 'usearch/sequences.fsa', '--dbmatched', 'usearch/sbsearch_results.fsa', '--uc', 'usearch/sbsearch_uctable.uc', '--uc_allhits',]
    args = append_flags_to_args(args, globalFlags)
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    output = popen.stdout.read()
    print(output)

def run_vsearch_exact():
    # setting maxaccepts to 0 disables the limit (searches for all possible matches)
    args = [vsearch_binary_filename, '--search_exact', 'usearch/searchsequence.fsa', '--db', 'usearch/sequences.fsa', '--dbmatched', 'usearch/sbsearch_results.fsa', '--uc', 'usearch/sbsearch_uctable.uc', '--uc_allhits']
    args = append_flags_to_args(args, exactFlags)
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    output = popen.stdout.read()
    print(output)

def append_flags_to_args(argsList, flags):
    for flag in flags:
        argsList.append("--" + flag)
        argsList.append(flags[flag])
    return argsList

def add_global_flags(userFlags):
    for flag in userFlags:
        if flag in globalFlags:
            globalFlags[flag] = userFlags[flag]


def add_exact_flags(userFlags):
    for flag in userFlags:
        if flag in exactFlags:
            exactFlags[flag] = userFlags[flag]


def sequence_search(userFlags):
    utils.log('Starting sequence search')

    if "search_exact" in userFlags:
        add_exact_flags(userFlags)
        run_vsearch_exact()
    else:
        add_global_flags(userFlags)
        run_vsearch_global()
    utils.log('Sequence search complete')

    return cluster.uclust2uris()

