# SBOLExplorer 2.0 — Paper & Development Plan / 论文与开发计划

> Working document. Bilingual (English + 中文). Each engineering phase must produce a concrete paper artifact (figure/table), otherwise it is out of scope.
>
> 工作底稿。中英双语。每个工程阶段都必须产出明确的论文素材（图/表），否则不在范围内。

---

## 1. Target & Framing / 目标与定位

**EN.** SBOLExplorer 2.0 is positioned as a **tool / web-server paper**, not a pure methods paper. It builds on the existing published SBOLExplorer, so the "2.0" upgrade path is natural and credible.

**Target venues:** NAR Web Server Issue · Bioinformatics (Application Note) · ACS Synthetic Biology. These venues explicitly accept "integrating known techniques into a useful system" as a contribution.

**中文。** SBOLExplorer 2.0 定位为**工具 / Web server 论文**，而非纯方法论文。它建立在已发表的 SBOLExplorer 之上，"2.0" 升级路径自然可信。

**目标期刊：** NAR Web Server Issue · Bioinformatics (Application Note) · ACS Synthetic Biology。这类期刊明确认可"把已知技术整合成有用系统"作为贡献。

---

## 2. Core Thesis / 核心论点

**EN.** SBOLExplorer 2.0 fuses **sequence semantics (bio foundation models) + text semantics + graph signal (PageRank)** into unified **hybrid retrieval**, complemented by **ontology faceted browsing** and **composition-graph navigation** — moving genetic-part discovery from *keyword matching* to *semantic + structural discovery*.

**中文。** SBOLExplorer 2.0 把**序列语义（生物基础模型）+ 文本语义 + 图结构信号（PageRank）**融合成统一的 **hybrid 检索**，配合**本体 faceted 浏览**和**组成关系图导航**，让合成生物学 part 的发现从"关键词匹配"升级为"语义 + 结构发现"。

### Contributions / 贡献点

1. **Hybrid retrieval** — multi-recall (keyword + text-vector + sequence-vector) fused via **RRF (Reciprocal Rank Fusion)** in the Flask layer, then re-ranked with `log(pagerank+1)`. / 多路召回（关键词 + 文本向量 + 序列向量）在 Flask 层用 **RRF** 融合，再用 `log(pagerank+1)` 重排。
2. **Sequence embeddings** from bio foundation models (Nucleotide Transformer / Evo / ESM-2) — enables "functionally similar but non-homologous" retrieval that VSEARCH cannot do. / 来自生物基础模型的**序列 embedding**，支持 VSEARCH 做不到的"功能相似但非同源"检索。
3. **Faceted browsing** over ontology/host fields. / 基于本体 / 宿主字段的 **faceted 浏览**。
4. **Composition-graph navigation** (part ↔ device) — surfaces the existing PageRank usage graph as a clickable bidirectional structure. / **组成关系图导航**（part ↔ device），把已有的 PageRank 使用图变成可点击的双向结构。
5. **Efficiency** — keep **VSEARCH** (selection justified by a prior group paper showing VSEARCH > BLAST), but **engineer the pipeline**: async/non-blocking, remove repeated `.uc` linear scans, incremental indexing instead of full rebuild. / **效率提升**——保留 **VSEARCH**（选型由本组前作 VSEARCH > BLAST 证明），但**把流水线工程化**：异步/非阻塞、去掉对 `.uc` 的反复线性扫描、增量索引替代全库重建。

---

## 3. Current Architecture (baseline) / 现状架构（基线）

| Area / 模块 | Current state / 现状 | File / 文件 |
|---|---|---|
| Full-text search / 全文检索 | Elasticsearch **6.3** (2018, EOL); `function_score` + `log(pagerank+1)` ranking | `flask/search.py`, `flask/elasticsearchManager.py` |
| Graph signal / 图信号 | PageRank over 1-hop/2-hop part-usage graph on Virtuoso; used **only** for ranking | `flask/pagerank.py` |
| Clustering / 聚类 | VSEARCH/UCLUST, single 0.8 threshold, full rebuild every time | `flask/cluster.py` |
| Sequence search / 序列搜索 | Synchronous blocking subprocess + repeated linear scans over `.uc` files | `flask/sequencesearch.py` |
| Indexed fields / 已索引字段 | displayId, name, description, type, role (SO term), sboltype, keywords, pagerank | `flask/index.py`, `flask/query.py` |
| Data backend / 数据后端 | Virtuoso SPARQL (SBOL2) | `flask/query.py`, `flask/wor_client.py` |

**Gap / 缺口:** `organism` / `strain` / `chassis` is **not** in the data model (SBOL2 ComponentDefinition has no first-class species field) — must be **extracted** from free-text description.

---

## 4. Key Architecture Decisions / 关键架构决策

**EN.**
- **Backend:** migrate ES 6.3 → **Typesense** (bundles facets, typo-tolerance, vector search, hybrid in one engine).
- **Fusion location:** Typesense natively supports only *keyword + single-vector* hybrid. We need *two vector paths + keyword + PageRank*, so **fusion lives in the Flask layer**: multi-recall → **RRF** merge → `log(pagerank+1)` re-rank. **This fusion layer is the core method figure of the paper.**
- **Sequence embeddings:** parts store **DNA**, but function often lives at the protein level. **v1:** one DNA model (Nucleotide Transformer / Evo) over all sequences, embeddings precomputed **offline** (GPU, only at index rebuild) and stored in Typesense. **v2 (optional):** translate CDS parts to protein → ESM-2.
- **Terminology fix:** do **not** call this a "phylogenetic tree" — parts are mostly non-homologous, there is no common tree. Use **similarity graph / composition graph**.

**中文。**
- **后端：** ES 6.3 → **Typesense** 迁移（facet、typo 容错、向量检索、hybrid 一个引擎打包）。
- **融合位置：** Typesense 原生只支持"关键词 + 单一向量"hybrid。我们要"两路向量 + 关键词 + PageRank"，所以**融合放在 Flask 层**：多路召回 → **RRF** 合并 → `log(pagerank+1)` 重排。**这个融合层就是论文的核心方法图。**
- **序列 embedding：** part 存的是 **DNA**，但功能常在蛋白层面。**v1：** 用一个 DNA 模型（Nucleotide Transformer / Evo）对所有序列**离线**预计算（GPU，只在重建索引时跑）存入 Typesense。**v2（可选）：** CDS 类 part 译成蛋白 → ESM-2。
- **术语修正：** 不要叫"进化树"——part 大多不同源，没有共同的树。用**相似度图 / 组成关系图**。

---

## 4b. Rewrite / Restructure Strategy / 重写与重构策略

**EN.** The core backend is only **~2,200 lines of Python** (`flask/`), so "rewrite vs incremental" is largely moot — much of it gets rewritten anyway as part of the planned phases. The real decision is **what to retype vs what to port**. A clean new repo skeleton (modern deps, Docker, real tests, optionally Flask → **FastAPI** for native async) is acceptable at this size, under **two hard rules**:

1. **Port, don't retype, the domain logic.** `query.py` (Virtuoso SPARQL / SBOL2 extraction) + `pagerank.py` (usage graph + PageRank) ≈ **490 lines** are correct, hard-won scientific assets. Copy + light-clean them; retyping from a blank page only reintroduces bugs for zero scientific payoff.
2. **Time-box the rewrite.** Non-artifact plumbing (routes / config / logging) is rewritten to "clean and working", then stop. Every extra day polishing plumbing is a day stolen from Phase 3. **Rewriting is worth 0 points in the paper** — treat it as sharpening the axe, not chopping the wood.

Per-file plan:

| File / 文件 | LOC | Action / 处置 |
|---|---|---|
| `search.py` | 626 | **Rewrite** (already planned: ES → Typesense + fusion layer) |
| `elasticsearchManager.py` | 16 | **Delete** (Typesense) |
| `index.py` | 244 | **Adapt** (keep SBOL field mapping, retarget to Typesense) |
| `query.py` | 179 | **Port as-is** ⚠️ domain logic |
| `pagerank.py` | 117 | **Port as-is** ⚠️ reused in Phase 4 |
| `explorer.py` | 212 | **Rewrite as routes** (keep endpoints/interface stable). If FastAPI: parameters replace `request.args.get`, drop per-route `try/except` + `jsonify`, dedupe the repeated ES health-check via `Depends`, replace the hand-rolled `threading.Thread` auto-update with `lifespan`. / **重写成路由**（接口稳定）。换 FastAPI 则：参数替代 `request.args.get`、删掉每个接口的 `try/except`+`jsonify`、用 `Depends` 去掉重复的 ES 健康检查、用 `lifespan` 替代手搓的 `threading.Thread` 自动更新。 |
| `cluster.py` / `sequencesearch.py` | 112 + 140 | **Engineer** (undergrad; keep VSEARCH) |
| configManager / dataManager / wor_client / logger | ~196 | **Port** (infra; light clean) |
| `explorer_test.py` / `test.py` | 234 + 97 | **Rewrite** (tests should be redone anyway) |

**FastAPI (optional):** migrating Flask → FastAPI gives native async — directly helps the Phase 1 async-pipeline goal. Team impact is **minimal**: the undergrad builds the VSEARCH pipeline as a framework-agnostic module, the PhD colleague is unaffected. Recommended **if** Sophia is comfortable with it; otherwise stay on Flask — not a paper-relevant choice either way.

**Also (cheap, do separately from any rewrite):** purge repo junk (`denv/`, `jammy/`, `mprofile_*.dat`, `profile_output.prof`, `flask/1`, stray test files), pin dependencies, containerize.

**中文。** 核心后端只有 **~2200 行 Python**（`flask/`），所以"重写 vs 增量"基本是伪命题——按计划其中一大半本就要重写。真正的决策是**哪些重敲、哪些移植**。在这个量级，开个干净的新 repo 骨架（现代依赖、Docker、像样测试，可选 Flask → **FastAPI** 拿原生 async）是可接受的，但有**两条铁律**：

1. **领域逻辑是"搬"不是"重敲"。** `query.py`（Virtuoso SPARQL / SBOL2 抽取）+ `pagerank.py`（使用图 + PageRank）≈ **490 行**，是踩坑踩对的科学资产。复制 + 轻清理；从空白页重打只会重新引 bug、科学收益为零。
2. **给重写设时间盒。** 非素材的管道代码（routes / config / logging）重写到"干净且能跑"就停。每多花一天雕花，就是从 Phase 3 偷一天。**重写在论文里值 0 分**——当磨刀，别当砍柴。

逐文件计划见上表。

**FastAPI（可选）：** Flask → FastAPI 给原生 async，直接帮到 Phase 1 异步流水线目标。团队影响**很小**：本科生把 VSEARCH 流水线做成框架无关的模块，博士同事不受影响。Sophia 上手没压力就**推荐换**；否则留在 Flask——这本身不是论文相关的选择。

**另外（便宜，和重写分开做）：** 清掉 repo 垃圾（`denv/`、`jammy/`、`mprofile_*.dat`、`profile_output.prof`、`flask/1`、散落 test 文件）、锁依赖、容器化。

---

## 5. Phased Roadmap / 分阶段路线

> Each phase = one paper artifact. / 每个阶段 = 一份论文素材。

### Phase 0 — Evaluation harness / 评估地基 ⭐ start early / 尽早开始

**EN.** The most-neglected, most-fatal part. Without it, this is at best a preprint. Start in parallel with Phase 1.
- Build a **query test set + gold relevant parts**. Sources: iGEM/SynBioHub curated collections as weak labels; cluster members as similarity labels; a small expert-annotated query set.
- Freeze **metric scripts**: precision@k / MRR / NDCG (retrieval quality); latency / throughput (efficiency).
- **Artifact:** Table 1 + Evaluation section.

**中文。** 最容易被忽视、又最致命。没有它最多只能发 preprint。和 Phase 1 并行起步。
- 建一个**查询测试集 + gold 相关 part**。来源：iGEM/SynBioHub 策展 collection 当弱标签；cluster 成员当相似性标签；一小批专家标注查询。
- 固化**指标脚本**：precision@k / MRR / NDCG（检索质量）；latency / throughput（效率）。
- **产出：** Table 1 + 评估章节。

### Phase 1 — Backend foundation / 后端基座

**EN.**
- ES 6.3 → Typesense migration.
- **Keep VSEARCH** (do NOT switch tools — selection justified by the prior group paper showing VSEARCH > BLAST). Engineer the existing pipeline: make `sequencesearch.py` async/non-blocking; remove repeated `.uc` linear scans (parse once into an in-memory index); incremental indexing (re-cluster only new/changed parts) instead of full rebuild.
- **Artifact:** before/after pipeline speedup figure (latency / throughput / rebuild time).

**中文。**
- ES 6.3 → Typesense 迁移。
- **保留 VSEARCH**（不换工具——选型由本组前作 VSEARCH > BLAST 证明）。把现有流水线工程化：`sequencesearch.py` 改异步/非阻塞；去掉对 `.uc` 的反复线性扫描（一次解析进内存索引）；增量索引（只对新增/变更的 part 重聚类）替代全库重建。
- **产出：** 流水线 before/after 加速图（延迟 / 吞吐 / 重建耗时）。

### Phase 2 — Faceted search / Faceted 浏览 (not a standalone phase / 非独立阶段)

**EN.** Faceted browsing is **table-stakes** for a web-server paper, not a contribution highlight. It does not get its own headcount — split by cost:
- **Ready-now facets** (role/SO, type, collection, length buckets): near-free once Typesense is in. **Folded into Phase 1 (Sophia)** — declare the facet fields at index build + add filter UI.
- **organism/strain extraction** (NER or LLM from description → map to NCBI Taxonomy): high-cost, may not be extractable. **Gated stretch goal (undergrad).** Decision rule: if a 200-description feasibility study hits **≥ ~60%** extraction accuracy → promote to a real task; else **drop** and state in the paper that host info is absent from the SBOL2 data model and unreliable to extract from free text (an honest negative finding).
- **Artifact:** faceted UI figure (from the ready-now facets).

**中文。** Faceted 浏览是 web-server 论文的**标配**，不是贡献亮点，不单独占编制——按成本拆：
- **就绪 facet**（role/SO、type、collection、长度分桶）：Typesense 进来后近乎免费。**并入 Phase 1（Sophia）**——建索引时声明 facet 字段 + 前端加筛选框。
- **organism/strain 抽取**（NER 或 LLM 从 description 抽 → 映射 NCBI Taxonomy）：高成本，可能抽不出来。**门控 stretch goal（本科生）。** 决策规则：200 条 description 可行性研究命中率 **≥ ~60%** → 提为正式任务；否则**砍掉**，论文里一句话说明宿主信息不在 SBOL2 数据模型里、自由文本抽取不可靠（一个诚实的负面发现）。
- **产出：** faceted UI 图（来自就绪 facet）。

### Phase 3 — Hybrid semantic retrieval / Hybrid 语义检索 ⭐ core novelty / 核心新意

**EN.**
- Offline-compute two embedding paths (text + sequence) into Typesense.
- Implement the RRF + PageRank re-rank fusion layer.
- Evaluate against the old ES fuzzy match on the Phase 0 benchmark → prove improvement.
- **Artifact:** method figure + main results table.

**中文。**
- 离线算两路 embedding（文本 + 序列）入 Typesense。
- 实现 RRF + PageRank 重排融合层。
- 在 Phase 0 benchmark 上对比旧 ES 模糊匹配 → 证明提升。
- **产出：** 方法图 + 主结果表。

### Phase 4 — Composition-graph navigation / 组成关系图导航 ⭐ differentiator / 差异化卖点

**EN.**
- Turn the existing PageRank part↔device usage graph from a hidden ranking signal into a clickable bidirectional navigation (which sub-parts a part uses / which devices use it).
- Seed of the "next project" knowledge graph.
- **Artifact:** UI / case-study figure.

**中文。**
- 把已有的 PageRank part↔device 使用图从"隐藏的排序信号"变成可点击的双向导航（这个 part 用了哪些子 part / 又被哪些 device 使用）。
- 这是"下个 project 知识图谱"的雏形。
- **产出：** UI / case study 图。

---

## 6. Paper Artifact Map / 论文素材对照表

| Phase | Paper artifact / 论文素材 |
|---|---|
| 0 | Table 1 (eval setup + metrics) / 评估设置与指标表 |
| 1 | Pipeline before/after speedup figure / 流水线 before/after 加速图 |
| 2 | Faceted UI figure (folded into Phase 1) / Faceted UI 图（并入 Phase 1） |
| 3 | Method figure + main results table / 方法图 + 主结果表 |
| 4 | UI / case-study figure / UI / 案例研究图 |

---

## 7. Evaluation Plan (cross-cutting) / 评估计划（贯穿始终）

**EN.** Evaluation runs through every phase, not bolted on at the end.
- **Retrieval quality:** query test set + known relevant parts → precision@k / MRR / NDCG; show semantic retrieval beats old ES fuzzy match.
- **Efficiency:** before/after VSEARCH-pipeline latency/throughput/rebuild-time curves (engineering optimization, same tool).
- **Optional:** small-scale user study.
- **Rule:** for every feature shipped, build its benchmark at the same time.

**中文。** 评估贯穿每个阶段，不是最后补。
- **检索质量：** 查询测试集 + 已知相关 part → precision@k / MRR / NDCG；证明语义检索优于旧 ES 模糊匹配。
- **效率：** MMseqs2 vs VSEARCH 延迟/吞吐曲线。
- **可选：** 小规模用户研究。
- **铁律：** 每做一个功能，就同步把对应 benchmark 建起来。

---

## 8. Deferred / 暂缓

RAG / LLM / full knowledge graph → a later, separate project. Phase 4's composition graph is the bridge to it.

RAG / LLM / 完整知识图谱 → 留到后续独立 project。Phase 4 的组成关系图是通往它的桥。
