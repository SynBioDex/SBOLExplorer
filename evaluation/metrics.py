"""
Phase 0 retrieval metrics: precision@k, MRR, NDCG@k.

Relevance is graded (0-3). A result is "relevant" for binary metrics
(precision, MRR) when its grade > 0.

All functions take:
  ranked    -- list of displayIds in ranked order (already deduped)
  gold      -- dict {displayId: grade}, grade in 0..3; missing => 0
"""
from math import log2


def grade(gold, item):
    return gold.get(item, 0)


def precision_at_k(ranked, gold, k):
    if k <= 0:
        return 0.0
    topk = ranked[:k]
    hits = sum(1 for d in topk if grade(gold, d) > 0)
    return hits / k


def reciprocal_rank(ranked, gold):
    for i, d in enumerate(ranked, start=1):
        if grade(gold, d) > 0:
            return 1.0 / i
    return 0.0


def dcg(ranked, gold, k):
    # Discounted Cumulative Gain over the top-k.
    #   gain  = 2^grade - 1   -> grade 3=7, 2=3, 1=1 (exponential: rewards
    #                            highly-relevant hits much more than marginal ones)
    #   discount = log2(rank+1) -> a hit at rank 1 keeps full gain; deeper
    #                            ranks are worth progressively less.
    total = 0.0
    for i, d in enumerate(ranked[:k], start=1):
        g = grade(gold, d)
        if g > 0:
            total += (2 ** g - 1) / log2(i + 1)
    return total


def ndcg_at_k(ranked, gold, k):
    # Normalized DCG = DCG / IDCG, where IDCG is the DCG of the *ideal* ranking
    # (all relevant items sorted by grade, highest first). Result is in [0, 1];
    # 1.0 means this ranking is as good as the best possible ordering.
    ideal_grades = sorted(gold.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / log2(i + 1)
               for i, g in enumerate(ideal_grades, start=1) if g > 0)
    if idcg == 0:  # no relevant items labeled for this query
        return 0.0
    return dcg(ranked, gold, k) / idcg


def evaluate_query(ranked, gold, ks=(1, 5, 10)):
    """Returns a dict of all metrics for a single query."""
    out = {f'P@{k}': precision_at_k(ranked, gold, k) for k in ks}
    out['MRR'] = reciprocal_rank(ranked, gold)
    out['NDCG@10'] = ndcg_at_k(ranked, gold, 10)
    # rank of the top gold item (grade 3 if present, else best available) -- diagnostic
    top_gold = [d for d, g in sorted(gold.items(), key=lambda x: -x[1])]
    out['top_gold_rank'] = next((i for i, d in enumerate(ranked, 1)
                                 if d == top_gold[0]), None) if top_gold else None
    return out
