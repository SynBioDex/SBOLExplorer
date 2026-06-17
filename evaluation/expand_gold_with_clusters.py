"""
Weak-label expansion: turn single-part gold into set-based graded gold using
VSEARCH cluster membership (zero human annotation).

For each canonical part labeled in gold_queries.json, its sequence-similarity
cluster-mates (from flask/dumps/clusters_dump) are added as relevant at a lower
grade. Rationale: parts in the same VSEARCH cluster are sequence-similar, so for
a concept query (gfp, terminator, ...) they are legitimate relevant results --
just not necessarily THE canonical answer.

This does NOT replace expert review; it gives a defensible, reproducible weak
label that scales without an annotator. Output: gold_queries_expanded.json.

Usage:
    python3 expand_gold_with_clusters.py
    python3 run_eval.py --gold gold_queries_expanded.json
"""
import json
import os
import pickle

CLUSTERS = os.path.join(os.path.dirname(__file__), '..', 'flask', 'dumps', 'clusters_dump')
GOLD_IN = os.path.join(os.path.dirname(__file__), 'gold_queries.json')
GOLD_OUT = os.path.join(os.path.dirname(__file__), 'gold_queries_expanded.json')

CLUSTER_MATE_GRADE = 2  # grade assigned to sequence-similar cluster-mates


def displayid_of(uri):
    # .../igem/BBa_E0040/1  ->  BBa_E0040
    parts = uri.rstrip('/').split('/')
    return parts[-2] if len(parts) >= 2 else uri


def cluster_members_for(displayid, clusters):
    """All cluster-mate displayIds for any URI whose path contains /<displayid>/."""
    mates = set()
    needle = f'/{displayid}/'
    for key, members in clusters.items():
        if needle in key:
            for m in members:
                mates.add(displayid_of(m))
    mates.discard(displayid)
    return mates


def main():
    with open(CLUSTERS, 'rb') as f:
        clusters = pickle.load(f)
    with open(GOLD_IN) as f:
        gold_set = json.load(f)

    expanded = []
    for entry in gold_set:
        gold = dict(entry['gold'])  # keep canonical grades
        for did in list(entry['gold'].keys()):
            for mate in cluster_members_for(did, clusters):
                # don't downgrade a part already labeled higher
                gold[mate] = max(gold.get(mate, 0), CLUSTER_MATE_GRADE)
        expanded.append({'query': entry['query'], 'gold': gold})
        added = len(gold) - len(entry['gold'])
        print(f"{entry['query']:28} {len(entry['gold'])} -> {len(gold)} parts (+{added} cluster-mates)")

    with open(GOLD_OUT, 'w') as f:
        json.dump(expanded, f, indent=2)
    print(f'\nWrote {GOLD_OUT}')


if __name__ == '__main__':
    main()
