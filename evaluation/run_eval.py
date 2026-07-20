"""
Phase 0 evaluation runner.

Runs every ranker in rankers.RANKERS over the gold query set and prints a
comparison table (mean precision@k, MRR, NDCG@10) plus mean latency. This is
the "ruler": use it to decide ranking changes (e.g. buckets vs multiplicative
re-rank) on evidence, not on a single eyeballed query.

Usage:
    python run_eval.py                 # summary table over all rankers
    python run_eval.py --per-query     # also show per-query NDCG + top-gold rank
    python run_eval.py --raw-ranks     # grid of top-gold RAW RANK: query x ranker
    python run_eval.py --gold mygold.json

Requires Typesense to be running (docker start typesense).
"""
import argparse
import json
import os
import time

import metrics
import rankers

GOLD_DEFAULT = os.path.join(os.path.dirname(__file__), 'gold_queries.json')


def load_gold(path):
    with open(path) as f:
        return json.load(f)


def print_raw_rank_grid(gold_set, ranker_names, rank_matrix):
    """Grid of the top-gold RAW RANK for every (query, ranker). '-' = not found.

    rank_matrix[ranker_name][query] -> int rank or None. This is the position
    view the summary metrics compress away -- it exposes catastrophic burials
    (e.g. terminator -> rank 64) that a mean NDCG hides.
    """
    queries = [e['query'] for e in gold_set]
    qw = max(len(q) for q in queries)
    # shorten ranker headers so the grid stays narrow
    def short(n):
        return n if len(n) <= 11 else n[:10] + '.'
    headers = [short(n) for n in ranker_names]
    colw = [max(len(h), 5) for h in headers]

    header = f'{"query":<{qw}}' + ''.join(f'  {h:>{w}}' for h, w in zip(headers, colw))
    print('=== top-gold RAW RANK grid (lower is better; - = not retrieved) ===')
    print(header)
    print('-' * len(header))
    for q in queries:
        row = f'{q:<{qw}}'
        for name, w in zip(ranker_names, colw):
            r = rank_matrix[name].get(q)
            row += f'  {(str(r) if r is not None else "-"):>{w}}'
        print(row)
    print()


def run(gold_path, per_query, raw_ranks):
    gold_set = load_gold(gold_path)
    print(f'Gold set: {len(gold_set)} queries from {os.path.basename(gold_path)}\n')

    summary = {}
    rank_matrix = {}  # ranker_name -> {query: top_gold_rank}
    for name, fn in rankers.RANKERS.items():
        agg = {'P@1': 0.0, 'P@5': 0.0, 'P@10': 0.0, 'MRR': 0.0, 'NDCG@10': 0.0}
        latencies = []
        per_query_rows = []
        rank_matrix[name] = {}

        for entry in gold_set:
            q, gold = entry['query'], entry['gold']
            t0 = time.perf_counter()
            ranked = fn(q)
            latencies.append((time.perf_counter() - t0) * 1000)

            m = metrics.evaluate_query(ranked, gold)
            for key in agg:
                agg[key] += m[key]
            per_query_rows.append((q, m['NDCG@10'], m['top_gold_rank']))
            rank_matrix[name][q] = m['top_gold_rank']

        n = len(gold_set)
        for key in agg:
            agg[key] /= n
        agg['latency_ms'] = sum(latencies) / len(latencies)
        summary[name] = agg

        if per_query:
            print(f'--- {name} (per-query) ---')
            for q, nd, rank in per_query_rows:
                rank_s = str(rank) if rank is not None else '-'
                print(f'  {q:28} NDCG@10={nd:.3f}  top_gold_rank={rank_s}')
            print()

    if raw_ranks:
        print_raw_rank_grid(gold_set, list(rankers.RANKERS.keys()), rank_matrix)

    # Summary table
    cols = ['P@1', 'P@5', 'P@10', 'MRR', 'NDCG@10', 'latency_ms']
    header = f'{"ranker":22}' + ''.join(f'{c:>12}' for c in cols)
    print(header)
    print('-' * len(header))
    for name, agg in summary.items():
        row = f'{name:22}'
        for c in cols:
            row += f'{agg[c]:>12.3f}'
        print(row)
    print('\nHigher is better for all columns except latency_ms.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--gold', default=GOLD_DEFAULT)
    ap.add_argument('--per-query', action='store_true')
    ap.add_argument('--raw-ranks', action='store_true',
                    help='print a query x ranker grid of the top-gold raw rank')
    args = ap.parse_args()
    run(args.gold, args.per_query, args.raw_ranks)
