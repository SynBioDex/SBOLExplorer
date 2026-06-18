import csv
import os
import random
import subprocess
import tempfile
import time
import tracemalloc
from sys import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(BASE_DIR, "dumps/sequences.fsa")
UCLUST_RESULTS = os.path.join(BASE_DIR, "benchmark/benchmark_uclust.uc")
CSV_OUTPUT = os.path.join(BASE_DIR, "benchmark/baseline.csv")

UCLUST_IDENTITY = '0.8'
CSV_FIELDNAMES = ['hotspot', 'run', 'seq_len', 'elapsed_s', 'peak_kb']

# Load correct vsearch binary for OS
vsearch_binaries = {
    "linux": os.path.join(BASE_DIR, "usearch/vsearch_linux"),
    "darwin": os.path.join(BASE_DIR, "usearch/vsearch_macos")
}

vsearch_binary_filename = vsearch_binaries.get(platform, None)
if not vsearch_binary_filename:
    print("Sorry, your OS is not supported for this benchmark.")
    exit(1)


def load_fasta(path):
    """
    Loads a FASTA file and returns its contents.

    Arguments:
        path {str} -- Path to FASTA file

    Returns:
        list -- List of sequences
    """
    sequences = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith(">"):
                sequences.append(line)
    return sequences


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


def get_uris(uc_file):
    """
    Gets the hit URIs from a UC file.

    Arguments:
        uc_file {str} -- Path to .uc file

    Returns:
        list -- List of URIs
    """
    uris = []
    with open(uc_file) as file:
        for line in file:
            parts = line.split()
            if parts[0] == 'H':
                uris.append(parts[9])
    return uris


def run_vsearch(file_name):
    """
    Runs vsearch usearch_global on a query file against the corpus and writes results to a .uc file.

    Arguments:
        file_name {str} -- Path to query FASTA file
    """
    args = [vsearch_binary_filename, '--usearch_global', file_name, '--db', CORPUS_PATH,
            '--uc', file_name[:-4] + '.uc', '--uc_allhits']

    global_args = {
        'maxaccepts': '50',
        'id': '0.8',
        'iddef': '2',
        'maxrejects': '0',
        'maxseqlength': '5000',
        'minseqlength': '20'
    }

    for flag in global_args:
        args.append("--" + flag)
        args.append(global_args[flag])

    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def run_uc_scan(uc_file, uris):
    """
    Simulates the per-hit .uc file scans performed by get_info_from_uc_table in search.py
    -- reads percent match, strand, and CIGAR for each hit URI.

    Arguments:
        uc_file {str} -- Path to .uc file
        uris {list} -- List of hit URIs
    """
    hits = []

    for uri in uris:
        for col in [3, 4, 7]:  # percent_match, strand, CIGAR
            with open(uc_file) as file:
                for line in file:
                    parts = line.split()
                    if parts[9] == uri:
                        hits.append(parts[col])
                        break

    return hits


def run_uclust():
    """
    Runs vsearch cluster_fast on the full corpus and writes results to a .uc file.
    """
    args = [vsearch_binary_filename, '--cluster_fast', CORPUS_PATH, '--id', UCLUST_IDENTITY, '--uc', UCLUST_RESULTS]
    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def benchmark_function(fn, *args, **kwargs):
    """
    Runs fn(*args, **kwargs) and benchmarks its execution time and memory usage.

    Arguments:
        fn {function} -- Function to run
        *args {list} -- List of arguments
        **kwargs {dict} -- Keyword arguments

    Returns:
        tuple -- (elapsed time in seconds, peak memory usage in bytes)
    """
    tracemalloc.start()
    t0 = time.perf_counter()

    fn(*args, **kwargs)

    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return elapsed, peak


def print_results(label, elapsed, peak):
    """
    Prints benchmark results in a readable format.

    Arguments:
        label {str} -- Name of the hotspot being benchmarked
        elapsed {float} -- Elapsed time in seconds
        peak {int} -- Peak memory usage in bytes
    """
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"{'='*50}")
    print(f"  Elapsed time : {elapsed:.4f}s")
    print(f"  Peak memory  : {peak / 1024:.2f} KB")


def benchmark_search_pipeline(sequences, n=20):
    """
    Runs the hotspot 1 and 2 pipeline n times on random sequences and returns averages.
    Only samples sequences up to 5000bp to match vsearch's maxseqlength limit.

    Arguments:
        sequences {list} -- List of sequences to sample from
        n {int} -- Number of iterations

    Returns:
        tuple -- (rows, avg_elapsed_1, avg_peak_1, avg_elapsed_2, avg_peak_2)
    """
    rows = []
    eligible = [s for s in sequences if len(s) <= 5000]

    for i in range(n):
        random_sequence = random.choice(eligible)
        tmp_fasta = write_to_temp(random_sequence)

        # Hotspot 1: Synchronous blocking subprocess
        elapsed_1, peak_1 = benchmark_function(run_vsearch, tmp_fasta)

        uc_file = tmp_fasta[:-4] + '.uc'
        uris = get_uris(uc_file)

        # Hotspot 2: Repeated linear .uc file scans per hit
        elapsed_2, peak_2 = benchmark_function(run_uc_scan, uc_file, uris)

        rows.append({'hotspot': 1, 'run': i + 1, 'seq_len': len(random_sequence), 'elapsed_s': round(elapsed_1, 4), 'peak_kb': round(peak_1 / 1024, 2)})
        rows.append({'hotspot': 2, 'run': i + 1, 'seq_len': len(random_sequence), 'elapsed_s': round(elapsed_2, 4), 'peak_kb': round(peak_2 / 1024, 2)})

    h1_rows = [r for r in rows if r['hotspot'] == 1]
    h2_rows = [r for r in rows if r['hotspot'] == 2]
    avg_elapsed_1 = sum(r['elapsed_s'] for r in h1_rows) / n
    avg_peak_1 = sum(r['peak_kb'] for r in h1_rows) / n
    avg_elapsed_2 = sum(r['elapsed_s'] for r in h2_rows) / n
    avg_peak_2 = sum(r['peak_kb'] for r in h2_rows) / n

    return rows, avg_elapsed_1, avg_peak_1, avg_elapsed_2, avg_peak_2


def main():
    os.makedirs(os.path.join(BASE_DIR, "benchmark"), exist_ok=True)

    sequences = load_fasta(CORPUS_PATH)
    n = 20

    # Hotspots 1 & 2: averaged over n runs
    rows, avg_elapsed_1, avg_peak_1, avg_elapsed_2, avg_peak_2 = benchmark_search_pipeline(sequences, n)
    print_results(f"Hotspot 1: Synchronous blocking subprocess (avg {n} runs)", avg_elapsed_1, avg_peak_1 * 1024)
    print_results(f"Hotspot 2: Repeated linear .uc file scans per hit (avg {n} runs)", avg_elapsed_2, avg_peak_2 * 1024)

    # Hotspot 3: Full-corpus re-cluster on every index rebuild (single run)
    elapsed_3, peak_3 = benchmark_function(run_uclust)
    print_results("Hotspot 3: Full-corpus re-cluster on every index rebuild", elapsed_3, peak_3)

    # Write results to CSV
    with open(CSV_OUTPUT, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
        h1_rows = [r for r in rows if r['hotspot'] == 1]
        avg_seq_len = round(sum(r['seq_len'] for r in h1_rows) / len(h1_rows), 1)
        writer.writerow({'hotspot': 1, 'run': 'AVERAGE', 'seq_len': avg_seq_len, 'elapsed_s': round(avg_elapsed_1, 4), 'peak_kb': round(avg_peak_1, 2)})
        writer.writerow({'hotspot': 2, 'run': 'AVERAGE', 'seq_len': avg_seq_len, 'elapsed_s': round(avg_elapsed_2, 4), 'peak_kb': round(avg_peak_2, 2)})
        writer.writerow({'hotspot': 3, 'run': 1, 'seq_len': 'full_corpus', 'elapsed_s': round(elapsed_3, 4), 'peak_kb': round(peak_3 / 1024, 2)})

    print(f"\nResults written to {CSV_OUTPUT}")

if __name__ == "__main__":
    main()
