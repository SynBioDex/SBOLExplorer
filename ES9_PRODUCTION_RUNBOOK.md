# Production runbook: SBOLExplorer on Elasticsearch 9

For the people who run the SynBioHub production VM and maintain
`synbiohub/synbiohub-docker`. Background and code details are in
[ES9_UPGRADE.md](ES9_UPGRADE.md); this page is only what to change and run.

## What changes and why

- Elasticsearch goes from **6.3.2** (end of life since 2020) to **9.5.3**.
- The SBOLExplorer image gets a **9.x Elasticsearch client**. It cannot talk to
  ES 6.3, and the old image cannot talk to ES 9. **Both switch together.**
- New: faceted search counts (`/facets`), and a fix that keeps SBOLExplorer
  from crashing when it starts before Elasticsearch is ready.

**Search downtime: none.** While the new index is built (~30 min),
SBOLExplorer does not answer, and SynBioHub falls back to querying Virtuoso
directly (`SBOLExplorerFallback` defaults to `true`). Search is slower in that
window, but it works.

## The one ordering rule

Production runs `myersresearchgroup/sbolexplorer:snapshot-synbiohub`, which CI
rebuilds on **every merge to SBOLExplorer master**. When the ES 9 branch
(`upgrade_ES`) is merged, that tag immediately becomes the ES 9 version, and
the next time the VM pulls it, it will not work against ES 6.3.

So: **merge `upgrade_ES` only when you are ready to do steps 2–4 right away**,
or do not pull/recreate the explorer on the VM until then.

## 1. Before the window

On the VM:

```bash
sysctl vm.max_map_count                  # must be >= 262144 (ES 9 refuses to start otherwise)
free -g; df -h                           # ~2 GB RAM for ES, a few GB disk for the new index
curl -s localhost:13162/config           # check the live SBOLExplorer config:
                                         #   pagerank_tolerance should be 0.0001 (not 1)
                                         #   uclust_identity should be 0.8  (not 1.8)
```

If either config value is wrong, fix it now (`POST /config` or edit
`/mnt/config/config.json` in the `explorer` volume). The rebuild in step 4 uses
them; with the wrong values PageRank stops after one iteration and clustering
silently reuses stale data.

Record the current explorer image digest, for rollback:

```bash
docker image inspect myersresearchgroup/sbolexplorer:snapshot-synbiohub --format '{{range .RepoDigests}}{{.}}{{end}}'
# as of 2026-10-09 this is ...@sha256:ef904541fe6a... (master 9a56562, ES 6 client)
```

## 2. Change `docker-compose.explorer.yml` (synbiohub-docker PR)

```yaml
version: '3.2'

services:
    explorer:
        image: myersresearchgroup/sbolexplorer:snapshot-synbiohub
        restart: unless-stopped            # NEW: a crash at startup no longer leaves it down
        privileged: true
        ports:
            - "13162:13162"
        depends_on:
            - elasticsearch
            - synbiohub
        dns: 8.8.8.8
        volumes:
            - type: volume
              source: explorer
              target: /mnt
    elasticsearch:
        image: docker.elastic.co/elasticsearch/elasticsearch:9.5.3   # was 6.3.2
        restart: unless-stopped
        environment:                       # NEW: ES 8+ enables TLS + passwords by default
            - discovery.type=single-node
            - xpack.security.enabled=false
            - ES_JAVA_OPTS=-Xms1g -Xmx1g
        depends_on:
            - virtuoso
        ports:
            - "127.0.0.1:9200:9200"        # was "9200:9200": see Security below
        volumes:
            - type: volume
              source: esdata9              # NEW volume: ES 9 cannot open the 6.x data
              target: /usr/share/elasticsearch/data

volumes:
    esdata:                                # keep: the old 6.3 index, for rollback
    esdata9:
    explorer:
```

**Security.** With `xpack.security.enabled=false`, anyone who can reach port
9200 can read and delete the index, which includes users' **private** parts.
Only the `explorer` container needs ES, and it connects over the compose
network (`elasticsearch:9200`). Bind the port to loopback as above, or remove
the `ports:` entry entirely. Also check that the Azure network security group
does not expose 9200.

`depends_on: condition: service_healthy` is **not** used: it is not supported
by the `version: '3.2'` file format with docker-compose v1, which the VM uses.
`restart: unless-stopped` plus the new startup retry in SBOLExplorer cover the
same problem.

## 3. Switch over (on the VM, in the synbiohub-docker directory)

Use the same `-f` list as the normal start command:

```bash
F="-f docker-compose.yml -f docker-compose.explorer.yml -f docker-compose.pluginVisualComponentUse.yml -f docker-compose.pluginSubmitExcel2SBOL.yml"

git pull                                                   # the compose change from step 2
docker pull myersresearchgroup/sbolexplorer:snapshot-synbiohub   # the ES 9 build (after upgrade_ES is merged)
docker pull docker.elastic.co/elasticsearch/elasticsearch:9.5.3

/usr/local/bin/docker-compose $F up -d --no-deps elasticsearch
curl -s localhost:9200 | grep '"number"'                   # wait ~30-60 s; expect "9.5.3"

/usr/local/bin/docker-compose $F up -d --no-deps explorer
docker logs --tail 20 synbiohub-docker_explorer_1          # expect "Index not found, creating new index."
```

`--no-deps` restarts only these two services; SynBioHub, Virtuoso and the
plugins keep running.

## 4. Build the index

With an empty ES, SBOLExplorer builds the index **during startup** ("Index not
found, creating new index"). It does not open port 13162 until the build is
done (~30 min; the clustering step prints no progress), so its HTTP endpoints
do not answer yet. Follow progress inside the container:

```bash
docker exec synbiohub-docker_explorer_1 tail -5 /SBOLExplorer/flask/indexing_log.txt
```

It is done when the last lines are five `Facet ...: updated N parts` lines and
`Successfully updated index`, and `curl localhost:13162/info` answers.
To rebuild again later (with the service running): `curl -s localhost:13162/update`.

## 5. Verify

```bash
curl -s 'localhost:9200/_cat/indices/part?v'          # health green; docs.count in the 100k+ range
curl -s -o /dev/null -w '%{http_code}\n' localhost:13162/info                       # 200
curl -s 'localhost:13162/facets?query=promoter&facet_by=role&size=3'               # non-empty role counts
```

In the SynBioHub UI:
- search `gfp`, `rbs`, `terminator`: results appear
- a typo (`terminatr`) still finds terminators
- a logged-in user sees their private parts at the top
- search text plus a Collections filter (e.g. iGEM) returns results
  (this failed on ES 9 before commit 24a2a32)

## Rollback

```bash
git checkout HEAD~1 -- docker-compose.explorer.yml    # back to ES 6.3.2 + esdata
docker tag myersresearchgroup/sbolexplorer@sha256:ef904541fe6a<full digest from step 1> \
           myersresearchgroup/sbolexplorer:snapshot-synbiohub
/usr/local/bin/docker-compose $F up -d --no-deps elasticsearch explorer
```

The old `esdata` volume still holds the 6.3 index, so no rebuild is needed. The
explorer image and ES must go back **together**.

## Related changes (independent of this window)

These can be deployed before or after; both fall back to the current behavior
when `/facets` is not available:
- synbiohub `facets-via-explorer`: `/facets` proxy that scopes counts to the
  logged-in user's graphs.
- synbiohub3 `facets-via-explorer`: the search sidebar and result count use
  `/facets`.
