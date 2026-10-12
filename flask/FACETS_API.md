# Faceted Search API — a guide (for the undergrad)

This explains **faceted search** in SBOLExplorer: what a facet is, why counting
facets does not need SPARQL at query time, the `/facets` API, and how the
frontend should use it.

---

## 1. What is a "facet"? (the big picture)

Look at the search UI: you type `rbs`, get results, and on the left there are
dropdowns — **Part Type**, **Part Role**, **Object Type**, **Collections**,
**Creator** — each value with a number:

```
Select Part Role
  engineered_region (3789)
  Composite (1552)
  Generator (493)
  ...
```

A **facet** is one of those category fields. A **facet count** is "how many of the
*current* results fall under each value." Click one, and the results narrow to
that value.

Two different things:
- **Facet counts**: the numbers, used to *build* the dropdown.
- **Facet filtering**: clicking a value *narrows* the result list.

---

## 2. Does this need SPARQL?

### Index build (on `/update`): SPARQL required
Every part's data is pulled out of **Virtuoso** with SPARQL and stored as one
**document** per part in **Elasticsearch**. After the parts are indexed, the facet
values are added in a second pass (`index.index_facet_fields`), one SPARQL query
stream per facet, because a part can have **several** roles or collections.

### Serving a search: no SPARQL
Elasticsearch already has everything. It computes the facet counts itself with an
**aggregation**, in the same request that applies the search text and the
selected filters.

```
/update (once):   Virtuoso --SPARQL--> facet_role, facet_type, ... --> ES docs
/facets (each q): ES counts its own docs                   (Virtuoso not touched)
```

### What the current SynBioHub 3 UI does
Today `synbiohub3/frontend` sends one SPARQL query **per facet** to Virtuoso
(`sparql/getRoles.js`, `getTypes.js`, ...) plus one for the total. Those match
text with `CONTAINS` (substring, every word required) while the result list comes
from Elasticsearch (fuzzy, any word), so the numbers and the list disagree. Using
`/facets` fixes that: the counts come from the same query as the results.

---

## 3. The backend API

### Fields

| facet name (API) | what it is | ES field | filled from (SPARQL) |
|---|---|---|---|
| `role` | Part Role (SO term or iGEM part type) | `facet_role` | `?subject sbol2:role ?value` |
| `sboltype` | Part Type (DnaRegion, Protein, ...) | `facet_sboltype` | `?subject sbol2:type ?value` |
| `type` | Object Type (ComponentDefinition, Collection, ...) | `facet_type` | `?subject a ?value` |
| `creator` | Creator | `facet_creator` | `?subject dc:creator ?value` |
| `collections` | Collections the part belongs to | `facet_collections` | `?value sbol2:member ?subject` |

All of them are `keyword` arrays: a part with two roles is counted under both.
Definitions live in `facets.py` (`FACETS`). The fields only exist after a full
`/update`.

### Endpoint: `GET /facets`

```
GET /facets?query=rbs&graph=https://synbiohub.org/public&facet_by=role,type
```

| param | meaning | default |
|---|---|---|
| `query` | search text, matched exactly like `/search` | '' (everything) |
| `graph` | graph the caller may see; **repeat** for several (public + the user's private graph) | public graphs only |
| `facet_by` | comma-separated facets to count | all five |
| `size` | max values per facet (1–500) | 50 |
| `role`, `sboltype`, `type`, `creator`, `collections` | selected filter values; **repeat** a param to select several | none |

Filter semantics: **OR within a facet, AND across facets.**
`role=A&role=B&creator=X` means "(role A or B) and creator X".

Response:
```json
{
  "found": 4908,
  "facets": {
    "role": [
      {"value": "http://identifiers.org/so/SO:0000804", "label": "engineered_region", "count": 3789},
      {"value": "http://wiki.synbiohub.org/wiki/Terms/igem#partType/Composite", "label": "Composite", "count": 1552}
    ],
    "collections": [
      {"value": "https://synbiohub.org/public/igem/igem_collection/1", "label": "iGEM Parts Registry", "count": 4863}
    ]
  }
}
```

- `found`: number of results with **all** selected filters applied. Use it for
  "Showing 1–50 of N".
- `facets.<name>`: one entry per value, sorted by count. Send `value` back as the
  filter; show `label`.
- Each facet's counts ignore **its own** selection but honour all others
  ("self-exclusion"). After picking role A, the role list still shows how many
  results B, C, ... would give, instead of collapsing to just A.
- Values are exact keyword matches. Pass `value` back exactly as received.

### Privacy
- Without `graph`, only public documents are counted.
- Collections are listed only if the collection itself is in a visible graph, so a
  user's private collection never shows up for others.
- `graph` is trusted as given. The browser must **not** call SBOLExplorer
  directly; the SynBioHub backend should forward the request and add the logged-in
  user's graph, as it already does for search.

### The code (where to look)
- `facets.py`: `FACETS`, `facet_search()` (builds the single ES request), labels.
- `explorer.py::facets_by_string()`: the `/facets` route.
- `index.py`: `index_facet_fields()` (full update) and `add_facet_fields()`
  (incremental updates).
- `query.py::query_subject_values()`: streams `(subject, values)` from Virtuoso.
- `tests/test_facets.py`: unit tests.

### Not supported (yet)
- The UI's free-form "additional filters" (any predicate = value). Keep the
  existing SPARQL path for those.
- Private parts are counted from the ES index. Private results in the list come
  from Virtuoso (#158), so a private part added since the last index update can
  appear in the list before it is counted.

---

## 4. What the frontend should do

Two columns: the **facet sidebar** (left, from `/facets`) and the **results list**
(right, from the existing search). Send the **same** query and selections to both.

```js
const BASE = "/api/explorer";   // via the SynBioHub backend, not SBOLExplorer directly

async function runSearch(query, selected) {      // selected = {role: [...], creator: [...]}
  const params = new URLSearchParams({ query });
  for (const [facet, values] of Object.entries(selected))
    for (const v of values) params.append(facet, v);

  const facets = await fetch(`${BASE}/facets?${params}`).then(r => r.json());
  renderCount(facets.found);          // "Showing 1-50 of N"
  renderFacets(facets.facets);        // label + (count); clicking toggles value in `selected`
  // results: the existing search request with the same query + filters
}
```

`facets_frontend_example.html` is a self-contained demo of the layout. It was
written for the earlier Typesense prototype, so update its response handling to
the shape above (`found`, `facets.<name>[].label`).

---

## 5. TL;DR
- **Facet counts at query time come from Elasticsearch only. No SPARQL.**
- **SPARQL runs at index build**, to load every value of each facet.
- **One request** returns the total and all facet counts, consistent with the result list.
- Run one full `/update` before using `/facets`.
