# Phase 0 — Retrieval Evaluation Harness

The "ruler" for SBOLExplorer 2.0. Every ranking change (bucketing, multiplicative
re-rank, hybrid semantic retrieval) is judged here on evidence, not on a single
eyeballed query.

## Files
- `gold_queries.json` — query test set with **graded relevance** labels (the seed).
- `metrics.py` — precision@k, MRR, NDCG@k.
- `rankers.py` — pluggable ranking strategies (talk to Typesense directly over HTTP).
- `run_eval.py` — runs every ranker over the gold set, prints a comparison table.

## Run
```bash
# Typesense must be up:  docker start typesense
cd evaluation
python3 run_eval.py              # summary table over all rankers
python3 run_eval.py --per-query  # per-query NDCG + rank of the top gold item
python3 run_eval.py --gold mygold.json
```

## Relevance scale (graded, for NDCG)
| grade | meaning |
|---|---|
| 3 | the canonical / textbook answer for this query |
| 2 | clearly relevant |
| 1 | marginally related |
| 0 | not relevant (any displayId not listed) |

Binary metrics (precision, MRR) treat grade > 0 as relevant.

## Extending the gold set (for the annotator)
1. Add entries to `gold_queries.json`: `{"query": "...", "gold": {"BBa_XXXX": 3, ...}}`.
2. Labels key on **displayId**; results are deduped by displayId before scoring.
3. **Avoid pool bias:** when judging, draw candidate parts from *all* rankers'
   top results, not just one — otherwise the metric silently favors that ranker.
4. The current file is a **seed** (~10 queries, weak labels from domain knowledge).
   It needs expert review and expansion. Some labels are deliberately hard
   (synonyms/abbreviations) to expose keyword-search recall gaps.

## Adding a ranking strategy
Add a function to `rankers.py` returning a deduped list of displayIds, then
register it in the `RANKERS` dict. Re-run `run_eval.py` to compare.

## Findings snapshot (seed gold, 2026-06)
- `current(buckets10)` NDCG@10 ≈ 0.40 — strong on exact-name queries (gfp, luxr),
  but buries canonical parts that match via description (rbs → rank 36,
  terminator → rank 64).
- `buckets1` ≈ `multiplicative` ≈ 0.53 — pagerank-dominated ordering rescues the
  buried canonical parts (rbs/terminator/tetr → rank 1) but can demote exact
  matches (gfp → rank 6). `multiplicative`'s `pr_scale` knob is meant to find the
  text-vs-pagerank balance that beats both (Option B tuning, ongoing).
- **3/10 queries are pure keyword-recall misses** — the gold part contains the
  *concept* but not the query string: `rfp`→"red fluorescent protein"/"mRFP1",
  `ribosome binding site`→"RBS", `lac promoter`→"lacI". No ranking config can fix
  these; they are the quantified motivation for **Phase 3 hybrid semantic retrieval**.
