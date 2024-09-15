import os
import subprocess
import tempfile
from sys import platform
from logger import Logger
import cluster

logger_ = Logger()

# Handling selection of VSEARCH binary
vsearch_binaries = {
    "linux": "usearch/vsearch_linux",
    "darwin": "usearch/vsearch_macos"
}

vsearch_binary_filename = vsearch_binaries.get(platform, None)
if not vsearch_binary_filename:
    logger_.log("Sorry, your OS is not supported for sequence-based search.")

# Predefined global and exact search flags
global_flags = {
    'maxaccepts': '50',
    'id': '0.8',
    'iddef': '2',
    'maxrejects': '0',
    'maxseqlength': '5000',
    'minseqlength': '20'
}
exact_flags = {}

def write_to_temp(sequence):
    """
    Writes a text sequence to a temporary FASTA file for search.
    
    Arguments:
        sequence {str} -- Sequence to write to file
    
    Returns:
        str -- Path to the temp file
    """
    with tempfile.NamedTemporaryFile(suffix=".fsa", delete=False, mode='w') as temp_file:
        temp_file.write(f'>sequence_to_search\n{sequence}\n')
    return temp_file.name

# pass in the sequence to this function, replace searchsequence.fsa with the query sequence
def run_vsearch_global(fileName):
    """
    Runs the "usearch_global" command
    
    Arguments:
        fileName {string} -- Path to file
    """

    # setting maxaccepts to 0 disables the limit (searches for all possible matches)
    args = [vsearch_binary_filename, '--usearch_global', fileName, '--db', 'dumps/sequences.fsa','--uc', fileName[:-4] + '.uc', '--uc_allhits',]
    args = append_flags_to_args(args, global_flags)

    popen = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    popen.wait()
    output = popen.stdout.read()
    logger_.log(output)
    
def run_vsearch_exact(fileName):
    """
    Runs the "search_exact" command
    
    Arguments:
        fileName {string} -- Path to file
    """
    # setting maxaccepts to 0 disables the limit (searches for all possible matches)
    args = [vsearch_binary_filename, '--search_exact', fileName, '--db', 'dumps/sequences.fsa','--uc', fileName[:-4] + '.uc', '--uc_allhits']
    args = append_flags_to_args(args, exact_flags)
    popen = subprocess.Popen(args, stdout=subprocess.PIPE)
    popen.wait()
    output = popen.stdout.read()
    logger_.log(output)

def append_flags_to_args(argsList, flags):
    """
    Append user flags to VSEARCH command line args
        
    Arguments:
        argsList {list} -- args to appen flags onto
        flags {dict} -- flags with outpins
    
    Returns:
        list -- modified command to be sent to VSEARCH
    """
    for flag in flags:
        argsList.append("--" + flag)
        argsList.append(flags[flag])
    return argsList

def add_global_flags(userFlags):
    """
    Adds flags to global search
    
    Arguments:
        userFlags {dict} -- flags selected by user
    """
    for flag in userFlags:
        if flag in global_flags:
            global_flags[flag] = userFlags[flag]

def add_exact_flags(userFlags):
    """
    Adds flags to exact search
    
    [description]
    
    Arguments:
        userFlags {dict} -- flags selected by user
    """
    for flag in userFlags:
        if flag in exact_flags:
            exact_flags[flag] = userFlags[flag]

def sequence_search(user_flags, file_name):
    """
    Handles all search queries.
    
    Arguments:
        user_flags {dict} -- Flags selected by the user
        file_name {str} -- Path to the temp file
    
    Returns:
        set -- Search results by URI
    """
    logger_.log('Starting sequence search')
    
    if "search_exact" in user_flags:
        add_exact_flags(user_flags)
        run_vsearch_exact(file_name)
    else:
        add_global_flags(user_flags)
        run_vsearch_global(file_name)
    logger_.log('Sequence search complete')
    
    return cluster.uclust2uris(file_name[:-4] + '.uc')

