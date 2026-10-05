# Upgrading Elasticsearch 6.3 → 9.x

SBOLExplorer previously ran on Elasticsearch **6.3.2** (EOL) with the Python
client `elasticsearch==6.3.0`. This branch (`upgrade_ES`) moves it to
Elasticsearch **9.5.3** with the `elasticsearch>=9,<10` client.

The index is always rebuilt from Virtuoso, so **no data migration is needed**:
start an empty ES 9 node and run `/update`.

> The ES server and the Python client must be upgraded **together**. The 9.x
> client cannot talk to a 6.x server, and the old code cannot run on a 9.x
> server. Never deploy one without the other.

---

## 1. Code changes (branch `upgrade_ES`)

| File | Change |
| --- | --- |
| `flask/requirements.txt` | `elasticsearch>=9,<10`; removed the unused `elasticsearch-dsl`; `requests>=2.32`; dropped the 2018 pins of `certifi`, `chardet`, `idna`, `urllib3` (they conflicted with the new client) |
| `flask/index.py` | Removed mapping types (ES 8+ rejects them): the `index_name:` level inside `mappings`, `_type` in bulk actions, and `doc_type=` in `delete_by_query` / `index`. `indices.exists` now uses a keyword argument (the 9.x client rejects positional args). `number_of_replicas: 0`, so a single-node index is green instead of yellow |
| `flask/search.py` | All `search()` calls pass `rest_total_hits_as_int=True`, so `hits.total` stays an integer (ES 7+ returns an object). The search code and the JSON returned to SynBioHub are unchanged. `empty_search_es` sets `track_total_hits: True`, so counts above 10,000 stay exact |
| `flask/explorer.py` | Health checks call `cat.indices(index=index_name)` instead of taking `[0]`. ES 9 creates hidden system indices, so `[0]` is not guaranteed to be `part` |
| `flask/docker/docker-compose.yml` | ES image `9.5.3` + `discovery.type=single-node`, `xpack.security.enabled=false`, `ES_JAVA_OPTS=-Xms1g -Xmx1g` |

Unchanged and still working on 9.x: `function_score` + Painless `script_score`
(including the #158 private-graph boost), `multi_match` with
`fuzziness: AUTO`, `ids` queries, and `from + size <= 10000`.

---

## 2. Local development setup (what was done)

### 2.1 Start ES 9 next to the old 6.3 container

Rename the old container so it stays available for rollback and comparison:

```bash
docker rename es01 es01-6.3

docker run -d --name es01 -p 9201:9200 \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  -e "ES_JAVA_OPTS=-Xms1g -Xmx1g" \
  -v es9-data:/usr/share/elasticsearch/data \
  -m 2g \
  docker.elastic.co/elasticsearch/elasticsearch:9.5.3
```

| Flag | Why |
| --- | --- |
| `-p 9201:9200` | `host:container`. The host port is 9201, so it can run alongside the old 6.3 container on 9200 |
| `discovery.type=single-node` | One-node cluster, no discovery |
| `xpack.security.enabled=false` | ES 8+ enables TLS and auth by default. Disabled to keep `http://` without credentials. **Only safe if the port is not publicly reachable** (see §3.4) |
| `-v es9-data:...` | Named volume, so the index survives recreating the container |
| `-m 2g` | A 1 GB heap needs about 2 GB of container memory |

Verify. First startup takes 30–60 s; until then `curl` fails with
`Connection reset by peer`.

```bash
curl localhost:9201                      # "number" : "9.5.3"
docker ps -a --filter "name=es" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
docker logs --tail 50 es01               # if it does not come up
```

The WSL host needs `vm.max_map_count >= 262144`
(`sysctl vm.max_map_count`). It already was.

### 2.2 Upgrade the Python environment

SBOLExplorer runs from the `jammy/` virtualenv (Python 3.11). Use its `pip`, not
the system one or pyenv:

```bash
cd ~/git_repo/SBOLExplorer
jammy/bin/pip uninstall -y elasticsearch-dsl
jammy/bin/pip install "elasticsearch>=9,<10"
jammy/bin/pip install -U "requests>=2.32" certifi   # fixes the idna/urllib3 conflict
jammy/bin/pip check                                 # "No broken requirements found."
```

Resulting versions: `elasticsearch 9.5.1`, `elastic-transport 9.4.2`,
`requests 2.34.2`, `urllib3 2.8.0`, `idna 3.20`.

### 2.3 Point SBOLExplorer at ES 9

In `flask/config.json`:

```json
"elasticsearch_endpoint": "http://localhost:9201/"
```

### 2.4 Run Flask from the virtualenv

```bash
cd ~/git_repo/SBOLExplorer/flask
../jammy/bin/flask --app explorer run --port 13162
```

Running plain `flask` picks up pyenv's Python 3.6, which fails with
`ModuleNotFoundError: No module named 'elasticsearch'`. In VS Code, select
`./jammy/bin/python` as the interpreter.

### 2.5 Rebuild the index

```
GET http://localhost:13162/update
```

Before this, `/` and `/search` return 503 because the `part` index does not
exist yet. The local rebuild took about 8 minutes (2026-10-04). The clustering
step can be much slower on a full corpus and prints no progress.

Result:

```bash
curl 'localhost:9201/_cat/indices/part?v'
# health green, docs.count 132920
curl -s -o /dev/null -w '%{http_code}\n' 'localhost:13162/search?query=gfp'   # 200
```

### 2.6 Rollback (local)

```bash
docker stop es01
docker start es01-6.3        # back on port 9200
# config.json: "elasticsearch_endpoint": "http://localhost:9200/"
# jammy: pip install -r <old requirements.txt from master>
git checkout master
```

---

## 3. Deploying to production

### 3.1 How production is wired

- SynBioHub's production stack is defined in the **`synbiohub/synbiohub-docker`**
  repo (`docker-compose.explorer.yml`, `docker-compose.version.yml`), not in
  this repo. `flask/docker/docker-compose.yml` here is only a standalone
  example.
- Pushing to `master` → `.github/workflows/build.yml` builds
  `myersresearchgroup/sbolexplorer:snapshot` and `:snapshot-synbiohub` from
  `flask/docker/Dockerfile-source` (local `requirements.txt`).
- Publishing a release → `.github/workflows/release.yml` builds
  `myersresearchgroup/sbolexplorer:<tag>-standalone` and **auto-commits the new
  SBOLExplorer tag** into `synbiohub-docker`.
- **That workflow does not change the Elasticsearch image.** The ES version in
  `synbiohub-docker` must be bumped by hand, in the same rollout.

### 3.2 Pre-deployment checklist

- [ ] `upgrade_ES` merged to `master` and the CI image built
- [ ] Coordinated with the `synbiohub-docker` maintainers; the ES image bump is
      ready in the same change set
- [ ] Production host has `vm.max_map_count >= 262144`
      (`sudo sysctl -w vm.max_map_count=262144`, persist in `/etc/sysctl.conf`)
- [ ] At least ~2 GB RAM free for ES (1 GB heap)
- [ ] Production `config.json` values are sane. In June 2026 the Azure instance
      had `pagerank_tolerance: 1` (PageRank stops after 1 iteration) and
      `uclust_identity: 1.8` (vsearch fails, clustering silently reuses a stale
      `.uc`). They should be `0.0001` and `0.8`. A full `/update` runs both
      steps.
- [ ] `elasticsearch_endpoint` still matches the ES service name in compose
      (`http://elasticsearch:9200/` in `config-synbiohub.json`)
- [ ] A maintenance window is planned. Search is unavailable (503) from the
      switch until `/update` finishes

### 3.3 Elasticsearch service in `synbiohub-docker`

Replace the ES service definition with something equivalent to:

```yaml
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:9.5.3
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms1g -Xmx1g
    volumes:
      - es9-data:/usr/share/elasticsearch/data
    # no "ports:" — only SBOLExplorer needs to reach ES, over the compose network

volumes:
  es9-data:
```

Use a **new** volume name. A 9.x node cannot start on a 6.x data directory, and
a fresh volume also keeps the old one intact for rollback.

### 3.4 Security note

With `xpack.security.enabled=false`, anyone who can reach port 9200 can read and
delete the index, and the index contains users' **private** parts. In
production, either:

- do not publish ES's port at all (recommended; containers on the same compose
  network can still reach `elasticsearch:9200`), or bind it to loopback
  (`"127.0.0.1:9200:9200"`); or
- enable security and give `elasticsearchManager.py` credentials. This requires
  a code change.

### 3.5 Rollout steps

```bash
# on the production host, in the synbiohub-docker checkout
git pull                                   # ES 9 image + new SBOLExplorer tag
docker compose -f <compose files> pull
docker compose -f <compose files> stop sbolexplorer elasticsearch
docker compose -f <compose files> up -d elasticsearch
curl <es-host>:9200                        # wait for "number" : "9.5.3"
docker compose -f <compose files> up -d sbolexplorer
curl http://<explorer-host>:13162/update   # rebuild the index
curl http://<explorer-host>:13162/indexinginfo
```

Then verify (§3.7).

**Lower-downtime alternative:** bring up the new ES and the new SBOLExplorer
under different service names/ports, run `/update` there, check results, then
switch SynBioHub's SBOLExplorer endpoint over. Search keeps working on the old
stack during the rebuild.

### 3.6 Rollback (production)

1. Revert the `synbiohub-docker` change: old ES 6.3.2 image, old volume, old
   SBOLExplorer tag.
2. `docker compose ... up -d`. The old volume still holds the 6.x index, so no
   rebuild is needed.

The old SBOLExplorer image and the old ES must go back **together** (see the
note at the top).

### 3.7 Verification

- [ ] `curl <es>:9200` reports `9.5.3`
- [ ] `curl '<es>:9200/_cat/indices/part?v'` is `green`. Compare
      `docs.count` with the old 6.3 index. Locally the ES 9 rebuild gave
      132,920 docs; a June 2026 6.3 index had 220,935. Check whether the gap
      comes from the dedup fix on master or is a regression.
- [ ] SynBioHub search for common terms (`gfp`, `rbs`, `terminator`) returns
      results; typo queries (e.g. `terminatr`) still match
- [ ] A logged-in user sees their private parts first (#158)
- [ ] Count queries (result totals in SynBioHub) look right
- [ ] Optional: run `evaluation/` on the old and the new index and compare
      NDCG@10

---

## 4. Behavior differences to expect

- **Score scale.** Lucene 8+ dropped the `(k1+1)` factor from BM25, so raw
  `_score` values are smaller. Rankings within a query are unaffected, because
  ES scores are only compared with each other. Fuzzy matching and the standard
  analyzer were also updated, so near-tied results can swap order.
- **System indices.** ES 9 creates hidden `.ds-*` indices. Code must address the
  `part` index by name, never by position.
- **License log line.** `license state changed, now [not valid]` in the ES logs
  comes from a paid-only feature. Ignore it; the `basic` license is `valid`.
- **New capabilities** now available: `dense_vector` / kNN (with filters),
  aggregations for facets, and the `retriever` API. Some fusion features (RRF)
  may require a paid license; check before relying on them.
