"""
Pluggable ranking strategies for the Phase 0 eval harness.

Each ranker takes a query string and returns a list of displayIds in ranked
order, deduped by displayId (a part that appears in several graphs is counted
once, at its best position). Rankers talk to Typesense directly over HTTP so
the harness does NOT import the Flask app (which would trigger startup()).

This is the "ruler": add a ranker here, run run_eval.py, and compare. The
multiplicative ranker mirrors the idea in search.py's SPARQL re-rank
(pagerank * text-relevance) -- it is the candidate "option B" for /search.
"""
import json
import os
from math import log1p
import requests

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'flask', 'config.json')

with open(_CONFIG_PATH) as f:
    _cfg = json.load(f)

HOST = _cfg.get('typesense_host', 'localhost')
PORT = _cfg.get('typesense_port', '8108')
PROTOCOL = _cfg.get('typesense_protocol', 'http')
API_KEY = _cfg.get('typesense_api_key', 'xyz')
COLLECTION = _cfg.get('typesense_collection_name', 'part')

_URL = f'{PROTOCOL}://{HOST}:{PORT}/collections/{COLLECTION}/documents/search'
_HEADERS = {'X-TYPESENSE-API-KEY': API_KEY}

# Mirror search.py's text query config so we compare apples to apples.
QUERY_BY = 'subject,displayId,version,name,description,type,keywords'
QUERY_BY_WEIGHTS = '1,3,1,1,1,1,1'
NUM_TYPOS = '2'
CANDIDATE_POOL = 250  # how many hits to pull for Python re-rankers


def _raw_search(query, sort_by, per_page=250):
    params = {
        'q': query,
        'query_by': QUERY_BY,
        'query_by_weights': QUERY_BY_WEIGHTS,
        'num_typos': NUM_TYPOS,
        'sort_by': sort_by,
        'per_page': per_page,
    }
    r = requests.get(_URL, headers=_HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get('hits', [])


def _dedup_by_displayid(hits):
    """Keep first (best-ranked) occurrence of each displayId."""
    seen = set()
    out = []
    for h in hits:
        did = h['document'].get('displayId')
        if did and did not in seen:
            seen.add(did)
            out.append(did)
    return out


# ---- Rankers ----------------------------------------------------------------

def ranker_current(query):
    """The live /search config: _text_match bucketed into 10, then pagerank."""
    hits = _raw_search(query, '_text_match(buckets: 10):desc,pagerank:desc')
    return _dedup_by_displayid(hits)


def ranker_buckets1(query):
    """One text bucket => effectively pure pagerank ordering among matches."""
    hits = _raw_search(query, '_text_match(buckets: 1):desc,pagerank:desc')
    return _dedup_by_displayid(hits)


def ranker_multiplicative(query, pr_scale=1e6):
    """
    Option B candidate: pull a pagerank-rich candidate pool of matches, then
    re-rank by  normalized_text_match * log1p(pagerank * pr_scale).

    Mirrors ES's BM25 x log(pagerank+1): text relevance sets the field,
    pagerank gives canonical (highly-used) parts a multiplicative lift.
    pr_scale lifts the tiny pageranks (~1e-4) into a useful log range; it is
    the main knob to tune against the gold set.

    NOTE: the candidate pool is fetched with a pagerank-aware sort (buckets:1)
    so canonical high-pagerank parts are actually IN the pool before we
    re-score -- pulling the pool by pure text_match excludes them when there
    are >pool exact-name matches (the bug in the first version).
    """
    hits = _raw_search(query, '_text_match(buckets: 1):desc,pagerank:desc',
                       per_page=CANDIDATE_POOL)
    if not hits:
        return []
    max_tm = max(h.get('text_match', 0) for h in hits) or 1
    scored = []
    seen = set()
    for h in hits:
        doc = h['document']
        did = doc.get('displayId')
        if not did or did in seen:
            continue
        seen.add(did)
        norm_text = h.get('text_match', 0) / max_tm
        pr = doc.get('pagerank', 0) or 0
        score = norm_text * log1p(pr * pr_scale)
        scored.append((did, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [d for d, _ in scored]


def ranker_weighted_sum(query, alpha=0.5, exact_boost=0.5, pr_scale=1e6):
    """
    Option B (proper form): re-rank a pagerank-rich candidate pool by a WEIGHTED
    SUM of independently-normalized text and pagerank signals, plus an
    exact-match boost. Unlike the multiplicative form, this does NOT collapse to
    pagerank order -- alpha genuinely trades off the two signals.

        norm_text =  text_match / max(text_match in pool)            in [0, 1]
        pr_signal =  log1p(pagerank * pr_scale)                      log-compressed
        norm_pr   =  pr_signal / max(pr_signal in pool)              in [0, 1]
        exact     =  1 if query == name or displayId (case-insensitive) else 0
        score     =  alpha * norm_text + (1 - alpha) * norm_pr + exact_boost * exact

    Knobs (tune on the ruler):
      alpha       -- text vs pagerank weight. 1.0 = pure text, 0.0 = pure pagerank.
      exact_boost -- lift for canonical exact-name/displayId matches; this is what
                     pushes a standard part (e.g. BBa_E0040 "GFP") above a
                     high-pagerank user construct merely *named* "..._GFP_...".
      pr_scale    -- log compression of the heavy-tailed pagerank; larger = pagerank
                     differences matter more before the log squashes them.
    """
    hits = _raw_search(query, '_text_match(buckets: 1):desc,pagerank:desc',
                       per_page=CANDIDATE_POOL)
    if not hits:
        return []

    max_tm = max(h.get('text_match', 0) for h in hits) or 1
    pr_signals = [log1p((h['document'].get('pagerank', 0) or 0) * pr_scale) for h in hits]
    max_pr = max(pr_signals) or 1
    q_lower = query.strip().lower()

    scored = []
    seen = set()
    for h, pr_sig in zip(hits, pr_signals):
        doc = h['document']
        did = doc.get('displayId')
        if not did or did in seen:
            continue
        seen.add(did)
        norm_text = h.get('text_match', 0) / max_tm
        norm_pr = pr_sig / max_pr
        name = (doc.get('name') or '').strip().lower()
        exact = 1.0 if q_lower in (name, did.strip().lower()) else 0.0
        score = alpha * norm_text + (1 - alpha) * norm_pr + exact_boost * exact
        scored.append((did, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [d for d, _ in scored]


# Registry the runner iterates over. Add new strategies here.
# Original strategies are kept untouched for experiment reproducibility.
RANKERS = {
    'current(buckets10)': ranker_current,
    'buckets1': ranker_buckets1,
    'multiplicative': ranker_multiplicative,
    # tuned on the seed gold: alpha=0.3, exact_boost=0.5 is the only config that
    # ranks gfp, rbs AND terminator near the top simultaneously (see sweep).
    'weighted_sum(a=.3,b=.5)': lambda q: ranker_weighted_sum(q, alpha=0.3, exact_boost=0.5),
}
