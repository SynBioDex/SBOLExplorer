import argparse
import csv
import os
import random
import shutil
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
TEST_SEQUENCES_PATH = os.path.join(BASE_DIR, "benchmark/test_sequences.fsa")
CSV_FIELDNAMES = ['hotspot', 'version', 'run', 'seq_len', 'elapsed_s', 'peak_kb']

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
        list -- List of (header, sequence) tuples
    """
    sequences = []
    header = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                header = line[1:]
            elif header is not None:
                sequences.append((header, line))
                header = None
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


def parse_hits(uc_file):
    """
    Parses a .uc file and returns a dict mapping each hit URI to its (percent_match, strand, cigar).

    Arguments:
        uc_file {str} -- Path to .uc file

    Returns:
        dict -- {uri: (percent_match, strand, cigar)}
    """
    hits = {}
    with open(uc_file) as file:
        for line in file:
            parts = line.split()
            if parts[0] == 'H':
                hits[parts[9]] = (parts[3], parts[4], parts[7])
    return hits


def run_vsearch(file_name):
    """
    Runs vsearch usearch_global on a query file against the corpus and writes results to a .uc file.

    Arguments:
        file_name {str} -- Path to query FASTA file
    """
    vsearch_args = [vsearch_binary_filename, '--usearch_global', file_name, '--db', CORPUS_PATH,
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
        vsearch_args.append("--" + flag)
        vsearch_args.append(global_args[flag])

    subprocess.run(vsearch_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


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


def run_uc_scan_indexed(uc_index, uris):
    """
    Optimized hotspot 2: looks up percent_match, strand, and CIGAR from a pre-built in-memory index.

    Arguments:
        uc_index {dict} -- {uri: (percent_match, strand, cigar)} from parse_hits
        uris {list} -- List of hit URIs
    """
    hits = []
    for uri in uris:
        if uri in uc_index:
            hits.extend(uc_index[uri])
    return hits


def run_uclust():
    """
    Runs vsearch cluster_fast on the full corpus and writes results to a .uc file.
    """
    args = [vsearch_binary_filename, '--cluster_fast', CORPUS_PATH, '--id', UCLUST_IDENTITY, '--uc', UCLUST_RESULTS]
    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def run_incremental_uclust(new_sequences_file):
    """
    Optimized hotspot 3: runs vsearch usearch_global on only new sequences against the existing corpus.

    Arguments:
        new_sequences_file {str} -- Path to FASTA file containing only new/changed sequences
    """
    with tempfile.NamedTemporaryFile(suffix='.uc', delete=False, mode='w') as tmp:
        tmp_uc = tmp.name

    args = [vsearch_binary_filename, '--usearch_global', new_sequences_file,
            '--db', CORPUS_PATH, '--uc', tmp_uc, '--uc_allhits',
            '--id', UCLUST_IDENTITY, '--iddef', '2',
            '--maxaccepts', '50', '--maxrejects', '0',
            '--maxseqlength', '5000', '--minseqlength', '20']

    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    os.unlink(tmp_uc)


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
    Benchmarks hotspots 1 and 2 (baseline and optimized) n times on random sequences.
    Only samples sequences up to 5000bp to match vsearch's maxseqlength limit.

    Arguments:
        sequences {list} -- List of (header, sequence) tuples to sample from
        n {int} -- Number of iterations

    Returns:
        tuple -- (rows, averages dict keyed by (hotspot, version))
    """
    rows = []
    eligible = [seq for _, seq in sequences if len(seq) <= 5000]

    for i in range(n):
        random_sequence = random.choice(eligible)
        tmp_fasta = write_to_temp(random_sequence)

        # Hotspot 1: Synchronous blocking subprocess (no optimized version — sidelined)
        elapsed_1, peak_1 = benchmark_function(run_vsearch, tmp_fasta)
        rows.append({'hotspot': 1, 'version': 'baseline', 'run': i + 1,
                     'seq_len': len(random_sequence), 'elapsed_s': round(elapsed_1, 4), 'peak_kb': round(peak_1 / 1024, 2)})

        uc_file = tmp_fasta[:-4] + '.uc'
        uc_index = parse_hits(uc_file)
        uris = list(uc_index.keys())

        # Hotspot 2 baseline: repeated linear .uc file scans per hit
        elapsed_2b, peak_2b = benchmark_function(run_uc_scan, uc_file, uris)
        rows.append({'hotspot': 2, 'version': 'baseline', 'run': i + 1,
                     'seq_len': len(random_sequence), 'elapsed_s': round(elapsed_2b, 4), 'peak_kb': round(peak_2b / 1024, 2)})

        # Hotspot 2 optimized: parse-once dict lookup
        elapsed_2o, peak_2o = benchmark_function(run_uc_scan_indexed, uc_index, uris)
        rows.append({'hotspot': 2, 'version': 'optimized', 'run': i + 1,
                     'seq_len': len(random_sequence), 'elapsed_s': round(elapsed_2o, 4), 'peak_kb': round(peak_2o / 1024, 2)})

    def avg(hotspot, version, key):
        subset = [r for r in rows if r['hotspot'] == hotspot and r['version'] == version]
        return sum(r[key] for r in subset) / len(subset) if subset else 0.0

    averages = {
        (1, 'baseline'): (avg(1, 'baseline', 'elapsed_s'), avg(1, 'baseline', 'peak_kb')),
        (2, 'baseline'): (avg(2, 'baseline', 'elapsed_s'), avg(2, 'baseline', 'peak_kb')),
        (2, 'optimized'): (avg(2, 'optimized', 'elapsed_s'), avg(2, 'optimized', 'peak_kb')),
    }

    return rows, averages


def save_reference(fsa_path):
    """
    Runs vsearch on each sequence in the FASTA file and saves .uc outputs to benchmark/reference/.

    Arguments:
        fsa_path {str} -- Path to test sequences FASTA file
    """
    ref_dir = os.path.join(BASE_DIR, "benchmark/reference")
    os.makedirs(ref_dir, exist_ok=True)

    for header, seq in load_fasta(fsa_path):
        name = header.split('/')[-2]
        tmp_fasta = write_to_temp(seq)
        run_vsearch(tmp_fasta)
        uc_file = tmp_fasta[:-4] + '.uc'
        ref_path = os.path.join(ref_dir, f"{name}.uc")
        shutil.move(uc_file, ref_path)
        hits = parse_hits(ref_path)
        print(f"  {name} ({len(seq)}bp): {len(hits)} hits saved")

    print(f"\nReference outputs saved to {ref_dir}")


def run_correctness_check(fsa_path):
    """
    Verifies the optimized search pipeline returns the same hits as the saved reference.
    Uses parse_hits (equivalent to load_uc_index in search.py) to validate hotspot 2 fix.

    Arguments:
        fsa_path {str} -- Path to test sequences FASTA file
    """
    ref_dir = os.path.join(BASE_DIR, "benchmark/reference")
    all_passed = True

    for header, seq in load_fasta(fsa_path):
        name = header.split('/')[-2]
        ref_path = os.path.join(ref_dir, f"{name}.uc")
        if not os.path.exists(ref_path):
            print(f"  SKIP {name}: no reference found — run --save-reference first")
            continue

        tmp_fasta = write_to_temp(seq)
        run_vsearch(tmp_fasta)
        uc_file = tmp_fasta[:-4] + '.uc'

        ref_hits = parse_hits(ref_path)
        new_hits = parse_hits(uc_file)

        if ref_hits == new_hits:
            print(f"  PASS {name}: {len(ref_hits)} hits match")
        else:
            missing = ref_hits.keys() - new_hits.keys()
            extra = new_hits.keys() - ref_hits.keys()
            print(f"  FAIL {name}: {len(missing)} hits missing, {len(extra)} extra")
            all_passed = False

    print("\nAll correctness checks passed." if all_passed else "\nSome correctness checks FAILED.")
    return all_passed


def main(skip_cluster_baseline=False):
    os.makedirs(os.path.join(BASE_DIR, "benchmark"), exist_ok=True)

    sequences = load_fasta(CORPUS_PATH)
    n = 20

    # Hotspots 1 & 2: averaged over n runs (baseline + optimized)
    rows, averages = benchmark_search_pipeline(sequences, n)

    avg_e1b, avg_p1b = averages[(1, 'baseline')]
    avg_e2b, avg_p2b = averages[(2, 'baseline')]
    avg_e2o, avg_p2o = averages[(2, 'optimized')]

    print_results(f"Hotspot 1: Synchronous blocking subprocess — baseline (avg {n} runs)", avg_e1b, avg_p1b * 1024)
    print_results(f"Hotspot 2: Repeated linear .uc scans — baseline (avg {n} runs)", avg_e2b, avg_p2b * 1024)
    print_results(f"Hotspot 2: Parse-once dict lookup — optimized (avg {n} runs)", avg_e2o, avg_p2o * 1024)

    h1_rows = [r for r in rows if r['hotspot'] == 1]
    avg_seq_len = round(sum(r['seq_len'] for r in h1_rows) / len(h1_rows), 1)

    if not skip_cluster_baseline:
        print("\nRunning hotspot 3 baseline (full cluster)...")
        elapsed_3b, peak_3b = benchmark_function(run_uclust)
        print_results("Hotspot 3: Full-corpus re-cluster — baseline", elapsed_3b, peak_3b)

    # Hotspot 3 optimized: incremental cluster on only the test sequences
    print("\nRunning hotspot 3 optimized (incremental cluster)...")
    elapsed_3o, peak_3o = benchmark_function(run_incremental_uclust, TEST_SEQUENCES_PATH)
    print_results("Hotspot 3: Incremental cluster on new sequences — optimized", elapsed_3o, peak_3o)

    with open(CSV_OUTPUT, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow({'hotspot': 1, 'version': 'baseline', 'run': 'AVERAGE',
                         'seq_len': avg_seq_len, 'elapsed_s': round(avg_e1b, 4), 'peak_kb': round(avg_p1b, 2)})
        writer.writerow({'hotspot': 2, 'version': 'baseline', 'run': 'AVERAGE',
                         'seq_len': avg_seq_len, 'elapsed_s': round(avg_e2b, 4), 'peak_kb': round(avg_p2b, 2)})
        writer.writerow({'hotspot': 2, 'version': 'optimized', 'run': 'AVERAGE',
                         'seq_len': avg_seq_len, 'elapsed_s': round(avg_e2o, 4), 'peak_kb': round(avg_p2o, 2)})
        if not skip_cluster_baseline:
            writer.writerow({'hotspot': 3, 'version': 'baseline', 'run': 1,
                             'seq_len': 'full_corpus', 'elapsed_s': round(elapsed_3b, 4), 'peak_kb': round(peak_3b / 1024, 2)})
        writer.writerow({'hotspot': 3, 'version': 'optimized', 'run': 1,
                         'seq_len': f'{len(load_fasta(TEST_SEQUENCES_PATH))}_seqs', 'elapsed_s': round(elapsed_3o, 4), 'peak_kb': round(peak_3o / 1024, 2)})

    print(f"\nResults written to {CSV_OUTPUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--save-reference', metavar='FSA', help='Save reference outputs for test sequences')
    parser.add_argument('--correctness', metavar='FSA', help='Run correctness check against saved reference')
    parser.add_argument('--no-cluster-baseline', action='store_true', help='Skip hotspot 3 full-corpus baseline (slow)')
    args = parser.parse_args()

    if args.save_reference:
        save_reference(args.save_reference)
    elif args.correctness:
        run_correctness_check(args.correctness)
    else:
        main(skip_cluster_baseline=args.no_cluster_baseline)
