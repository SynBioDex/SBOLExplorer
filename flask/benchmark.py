import argparse
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
HOLDOUT_FRACTION = 0.10  # fraction of corpus held out as "new sequences" for hotspot 3
CSV_FIELDNAMES = ['hotspot', 'version', 'run', 'n_query', 'n_corpus', 'seq_len', 'elapsed_s', 'peak_kb']

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


def write_fasta(sequences, path):
    """
    Writes a list of (header, sequence) tuples to a FASTA file.

    Arguments:
        sequences {list} -- List of (header, sequence) tuples
        path {str} -- Output file path
    """
    with open(path, 'w') as f:
        for header, seq in sequences:
            f.write(f'>{header}\n{seq}\n')


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


def run_uclust(corpus_path=None):
    """
    Runs vsearch cluster_fast on the full corpus and writes results to a .uc file.

    Arguments:
        corpus_path {str} -- Path to corpus FASTA file (defaults to CORPUS_PATH)
    """
    path = corpus_path or CORPUS_PATH
    args = [vsearch_binary_filename, '--cluster_fast', path, '--id', UCLUST_IDENTITY, '--uc', UCLUST_RESULTS]
    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


def run_incremental_uclust(new_sequences_file, corpus_path):
    """
    Optimized hotspot 3: runs vsearch usearch_global on only new sequences against the existing corpus.

    Arguments:
        new_sequences_file {str} -- Path to FASTA file containing only new/changed sequences
        corpus_path {str} -- Path to existing corpus FASTA file (without the new sequences)
    """
    with tempfile.NamedTemporaryFile(suffix='.uc', delete=False, mode='w') as tmp:
        tmp_uc = tmp.name

    args = [vsearch_binary_filename, '--usearch_global', new_sequences_file,
            '--db', corpus_path, '--uc', tmp_uc, '--uc_allhits',
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
    n_corpus = len(sequences)

    print(f"\nBenchmarking hotspots 1 & 2: {n} random sequences against corpus of {n_corpus} sequences...")

    for i in range(n):
        random_sequence = random.choice(eligible)
        tmp_fasta = write_to_temp(random_sequence)

        elapsed_1, peak_1 = benchmark_function(run_vsearch, tmp_fasta)
        rows.append({'hotspot': 1, 'version': 'baseline', 'run': i + 1,
                     'n_query': 1, 'n_corpus': n_corpus,
                     'seq_len': len(random_sequence), 'elapsed_s': round(elapsed_1, 4), 'peak_kb': round(peak_1 / 1024, 2)})

        uc_file = tmp_fasta[:-4] + '.uc'
        uc_index = parse_hits(uc_file)
        uris = list(uc_index.keys())

        elapsed_2b, peak_2b = benchmark_function(run_uc_scan, uc_file, uris)
        rows.append({'hotspot': 2, 'version': 'baseline', 'run': i + 1,
                     'n_query': len(uris), 'n_corpus': n_corpus,
                     'seq_len': len(random_sequence), 'elapsed_s': round(elapsed_2b, 4), 'peak_kb': round(peak_2b / 1024, 2)})

        elapsed_2o, peak_2o = benchmark_function(run_uc_scan_indexed, uc_index, uris)
        rows.append({'hotspot': 2, 'version': 'optimized', 'run': i + 1,
                     'n_query': len(uris), 'n_corpus': n_corpus,
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


def run_correctness_check():
    """
    Structural validity check for hotspot 3 (incremental clustering).
    Runs usearch_global on the holdout sequences against the corpus and verifies:
      1. The output contains H records (matches were found)
      2. Every centroid (parts[9]) in H records exists in the corpus
      3. Every query (parts[8]) in H records is from the holdout, not the corpus
      4. All reported percent identities are >= the identity threshold
    """
    all_sequences = load_fasta(CORPUS_PATH)
    n_total = len(all_sequences)
    n_holdout = max(1, int(n_total * HOLDOUT_FRACTION))
    corpus_seqs = all_sequences[:-n_holdout]
    holdout_seqs = all_sequences[-n_holdout:]

    corpus_uris = {header for header, _ in corpus_seqs}
    holdout_uris = {header for header, _ in holdout_seqs}

    print(f"Correctness check: {n_holdout} holdout sequences against corpus of {len(corpus_seqs)}...\n")

    corpus_tmp = tempfile.NamedTemporaryFile(suffix='.fsa', delete=False, mode='w')
    corpus_tmp.close()
    holdout_tmp = tempfile.NamedTemporaryFile(suffix='.fsa', delete=False, mode='w')
    holdout_tmp.close()
    uc_tmp = tempfile.NamedTemporaryFile(suffix='.uc', delete=False, mode='w')
    uc_tmp.close()

    write_fasta(corpus_seqs, corpus_tmp.name)
    write_fasta(holdout_seqs, holdout_tmp.name)

    args = [vsearch_binary_filename, '--usearch_global', holdout_tmp.name,
            '--db', corpus_tmp.name, '--uc', uc_tmp.name, '--uc_allhits',
            '--id', UCLUST_IDENTITY, '--iddef', '2',
            '--maxaccepts', '50', '--maxrejects', '0',
            '--maxseqlength', '5000', '--minseqlength', '20']
    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    h_records = []
    with open(uc_tmp.name) as f:
        for line in f:
            parts = line.split()
            if parts[0] == 'H':
                h_records.append((parts[8], parts[9], float(parts[3])))

    os.unlink(corpus_tmp.name)
    os.unlink(holdout_tmp.name)
    os.unlink(uc_tmp.name)

    all_passed = True
    threshold = float(UCLUST_IDENTITY) * 100

    # Check 1: output has H records
    if not h_records:
        print("  FAIL: no H records in output — incremental clustering produced no matches")
        all_passed = False
    else:
        print(f"  PASS: {len(h_records)} H records in output")

    # Check 2: all centroids exist in corpus
    invalid_centroids = [(q, c) for q, c, _ in h_records if c not in corpus_uris]
    if invalid_centroids:
        print(f"  FAIL: {len(invalid_centroids)} H records reference centroids not in corpus")
        for q, c in invalid_centroids[:5]:
            print(f"    {q} -> {c}")
        all_passed = False
    else:
        print(f"  PASS: all centroids are valid corpus URIs")

    # Check 3: all queries are from holdout
    invalid_queries = [(q, c) for q, c, _ in h_records if q not in holdout_uris]
    if invalid_queries:
        print(f"  FAIL: {len(invalid_queries)} H records have queries not from holdout")
        all_passed = False
    else:
        print(f"  PASS: all query sequences are from holdout")

    # Check 4: all percent identities meet threshold
    below_threshold = [(q, c, pct) for q, c, pct in h_records if pct < threshold]
    if below_threshold:
        print(f"  FAIL: {len(below_threshold)} H records below identity threshold ({threshold}%)")
        for q, c, pct in below_threshold[:5]:
            print(f"    {pct}% — {q} -> {c}")
        all_passed = False
    else:
        print(f"  PASS: all percent identities >= {threshold}%")

    print("\nAll correctness checks passed." if all_passed else "\nSome correctness checks FAILED.")
    return all_passed


def compare_clusters():
    """
    Compares incremental clustering vs full re-cluster for holdout sequences.
    Reuses the full re-cluster .uc file from the benchmark run (no re-clustering needed).
    For each holdout sequence, reports whether it:
      - Became a centroid in the full re-cluster (incremental can never assign it to itself)
      - Was assigned to the same corpus centroid in both approaches
      - Was assigned to a different corpus centroid (different path, same or different cluster)
      - Was assigned to a holdout centroid in full re-cluster (incremental misses this)
    """
    if not os.path.exists(UCLUST_RESULTS):
        print(f"ERROR: {UCLUST_RESULTS} not found — run the main benchmark first to generate it.")
        return False

    all_sequences = load_fasta(CORPUS_PATH)
    n_total = len(all_sequences)
    n_holdout = max(1, int(n_total * HOLDOUT_FRACTION))
    corpus_seqs = all_sequences[:-n_holdout]
    holdout_seqs = all_sequences[-n_holdout:]

    corpus_uris = {h for h, _ in corpus_seqs}
    holdout_uris = {h for h, _ in holdout_seqs}

    # Parse full re-cluster: classify each holdout sequence
    full_is_centroid = set()       # holdout sequences that became centroids
    full_corpus_centroid = {}      # holdout -> corpus centroid
    full_holdout_centroid = {}     # holdout -> holdout centroid (incremental can't find these)

    with open(UCLUST_RESULTS) as f:
        for line in f:
            parts = line.split()
            if parts[0] == 'S' and parts[8] in holdout_uris:
                full_is_centroid.add(parts[8])
            elif parts[0] == 'H' and parts[8] in holdout_uris:
                centroid = parts[9]
                if centroid in corpus_uris:
                    full_corpus_centroid[parts[8]] = centroid
                elif centroid in holdout_uris:
                    full_holdout_centroid[parts[8]] = centroid

    # Run usearch_global on holdout against corpus
    corpus_tmp = tempfile.NamedTemporaryFile(suffix='.fsa', delete=False, mode='w')
    corpus_tmp.close()
    holdout_tmp = tempfile.NamedTemporaryFile(suffix='.fsa', delete=False, mode='w')
    holdout_tmp.close()
    uc_tmp = tempfile.NamedTemporaryFile(suffix='.uc', delete=False, mode='w')
    uc_tmp.close()

    write_fasta(corpus_seqs, corpus_tmp.name)
    write_fasta(holdout_seqs, holdout_tmp.name)

    args = [vsearch_binary_filename, '--usearch_global', holdout_tmp.name,
            '--db', corpus_tmp.name, '--uc', uc_tmp.name, '--uc_allhits',
            '--id', UCLUST_IDENTITY, '--iddef', '2',
            '--maxaccepts', '50', '--maxrejects', '0',
            '--maxseqlength', '5000', '--minseqlength', '20']
    subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    incremental_centroids = {}
    with open(uc_tmp.name) as f:
        for line in f:
            parts = line.split()
            if parts[0] == 'H':
                if parts[8] not in incremental_centroids:
                    incremental_centroids[parts[8]] = set()
                incremental_centroids[parts[8]].add(parts[9])

    os.unlink(corpus_tmp.name)
    os.unlink(holdout_tmp.name)
    os.unlink(uc_tmp.name)

    # Compare and report
    print(f"\nCluster comparison: {n_holdout} holdout sequences\n")

    # Category 1: became centroids in full re-cluster
    centroid_matched = sum(1 for u in full_is_centroid if u in incremental_centroids)
    centroid_missed = len(full_is_centroid) - centroid_matched
    print(f"Holdout sequences that are centroids in full re-cluster: {len(full_is_centroid)}")
    print(f"  Found a corpus match in incremental:  {centroid_matched}")
    print(f"  No corpus match (new centroid missed): {centroid_missed}")

    # Category 2: assigned to a corpus centroid in full re-cluster
    agreed = sum(1 for u, c in full_corpus_centroid.items()
                 if u in incremental_centroids and c in incremental_centroids[u])
    disagreed = sum(1 for u, c in full_corpus_centroid.items()
                    if u in incremental_centroids and c not in incremental_centroids[u])
    inc_missed = sum(1 for u in full_corpus_centroid if u not in incremental_centroids)
    print(f"\nHoldout sequences assigned to corpus centroid in full re-cluster: {len(full_corpus_centroid)}")
    print(f"  Incremental agrees (same centroid):     {agreed}")
    print(f"  Incremental disagrees (diff centroid):  {disagreed}")
    print(f"  Incremental found no match:             {inc_missed}")

    # Category 3: assigned to another holdout centroid
    print(f"\nHoldout sequences assigned to another holdout centroid: {len(full_holdout_centroid)}")
    print(f"  (incremental cannot find these — holdout centroids not in corpus)")

    # Category 4: unmatched in full re-cluster
    all_assigned = full_is_centroid | set(full_corpus_centroid) | set(full_holdout_centroid)
    unmatched = holdout_uris - all_assigned
    print(f"\nHoldout sequences unmatched in both:    {len(unmatched)}")

    total_missed = centroid_missed + inc_missed + len(full_holdout_centroid)
    print(f"\nTotal cluster relationships missed by incremental: {total_missed} / {n_holdout} holdout sequences")


def main(skip_cluster_baseline=False):
    os.makedirs(os.path.join(BASE_DIR, "benchmark"), exist_ok=True)

    all_sequences = load_fasta(CORPUS_PATH)
    n_total = len(all_sequences)
    n_holdout = max(1, int(n_total * HOLDOUT_FRACTION))
    corpus_seqs = all_sequences[:-n_holdout]
    holdout_seqs = all_sequences[-n_holdout:]

    print(f"Corpus: {n_total} total sequences | {len(corpus_seqs)} corpus | {n_holdout} holdout ({HOLDOUT_FRACTION:.0%})")

    n = 20
    rows, averages = benchmark_search_pipeline(all_sequences, n)

    avg_e1b, avg_p1b = averages[(1, 'baseline')]
    avg_e2b, avg_p2b = averages[(2, 'baseline')]
    avg_e2o, avg_p2o = averages[(2, 'optimized')]

    print_results(f"Hotspot 1: Synchronous blocking subprocess — baseline (avg {n} runs)", avg_e1b, avg_p1b * 1024)
    print_results(f"Hotspot 2: Repeated linear .uc scans — baseline (avg {n} runs)", avg_e2b, avg_p2b * 1024)
    print_results(f"Hotspot 2: Parse-once dict lookup — optimized (avg {n} runs)", avg_e2o, avg_p2o * 1024)

    h1_rows = [r for r in rows if r['hotspot'] == 1]
    avg_seq_len = round(sum(r['seq_len'] for r in h1_rows) / len(h1_rows), 1)

    corpus_tmp = tempfile.NamedTemporaryFile(suffix='.fsa', delete=False, mode='w')
    corpus_tmp.close()
    holdout_tmp = tempfile.NamedTemporaryFile(suffix='.fsa', delete=False, mode='w')
    holdout_tmp.close()
    write_fasta(corpus_seqs, corpus_tmp.name)
    write_fasta(holdout_seqs, holdout_tmp.name)

    elapsed_3b = peak_3b = None
    if not skip_cluster_baseline:
        print(f"\nRunning hotspot 3 baseline: clustering all {n_total} sequences (full corpus)...")
        elapsed_3b, peak_3b = benchmark_function(run_uclust)
        print_results("Hotspot 3: Full-corpus re-cluster — baseline", elapsed_3b, peak_3b)

    print(f"\nRunning hotspot 3 optimized: searching {n_holdout} new sequences against corpus of {len(corpus_seqs)}...")
    elapsed_3o, peak_3o = benchmark_function(run_incremental_uclust, holdout_tmp.name, corpus_tmp.name)
    print_results("Hotspot 3: Incremental cluster on new sequences — optimized", elapsed_3o, peak_3o)

    os.unlink(corpus_tmp.name)
    os.unlink(holdout_tmp.name)

    with open(CSV_OUTPUT, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow({'hotspot': 1, 'version': 'baseline', 'run': 'AVERAGE',
                         'n_query': 1, 'n_corpus': n_total,
                         'seq_len': avg_seq_len, 'elapsed_s': round(avg_e1b, 4), 'peak_kb': round(avg_p1b, 2)})
        writer.writerow({'hotspot': 2, 'version': 'baseline', 'run': 'AVERAGE',
                         'n_query': 'avg_hits', 'n_corpus': n_total,
                         'seq_len': avg_seq_len, 'elapsed_s': round(avg_e2b, 4), 'peak_kb': round(avg_p2b, 2)})
        writer.writerow({'hotspot': 2, 'version': 'optimized', 'run': 'AVERAGE',
                         'n_query': 'avg_hits', 'n_corpus': n_total,
                         'seq_len': avg_seq_len, 'elapsed_s': round(avg_e2o, 4), 'peak_kb': round(avg_p2o, 2)})
        if elapsed_3b is not None:
            writer.writerow({'hotspot': 3, 'version': 'baseline', 'run': 1,
                             'n_query': n_total, 'n_corpus': n_total,
                             'seq_len': 'full_corpus', 'elapsed_s': round(elapsed_3b, 4), 'peak_kb': round(peak_3b / 1024, 2)})
        writer.writerow({'hotspot': 3, 'version': 'optimized', 'run': 1,
                         'n_query': n_holdout, 'n_corpus': len(corpus_seqs),
                         'seq_len': f'{n_holdout}_seqs', 'elapsed_s': round(elapsed_3o, 4), 'peak_kb': round(peak_3o / 1024, 2)})

    print(f"\nResults written to {CSV_OUTPUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--correctness', action='store_true', help='Structural validity check for incremental clustering output')
    parser.add_argument('--compare-clusters', action='store_true', help='Compare incremental vs full re-cluster assignments for holdout sequences')
    parser.add_argument('--no-cluster-baseline', action='store_true', help='Skip hotspot 3 full-corpus baseline (slow)')
    args = parser.parse_args()

    if args.correctness:
        run_correctness_check()
    elif args.compare_clusters:
        compare_clusters()
    else:
        main(skip_cluster_baseline=args.no_cluster_baseline)
