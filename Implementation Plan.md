# AI Discovery Engine — Phase-wise Implementation Plan

**Document type**: Implementation plan  
**Aligned to**: [System Architecture.md](./System%20Architecture.md) v1.2, [Edge Cases.md](./Edge%20Cases.md) v1.1, [Problem Statement .md](./Problem%20Statement%20.md) v2.2  
**Scope**: Build and freeze the one-time four-source discovery snapshot (Play Store, App Store, Reddit, Google Photos Help Community)  
**Not this plan**: Product-team review (problem statement §8 Phase 2) and product roadmap / in-Photos search features (Phase 3)

---

## 1. How this plan maps to the source docs

Architecture §14 is the build sequence. Problem statement §8 Phase 1 is the *outcome* of this entire plan (dashboard + RAG + methodology artifact). Edge Cases.md is the **phase-gate contract**: a phase is not done if its blocker/must cases are unhandled or untested.

| This plan | Architecture §14 | Problem statement | Primary edge-case sections |
|-----------|------------------|-------------------|----------------------------|
| Phase 0 Foundation | 0 | Enables all deliverables | §6 freeze rules, §12 privacy (schema-level) |
| Phase 1 Collection | 1 | §3 collection, §6 “sufficient data” | §§2–6 |
| Phase 2 Analysis | 2 | §3 analysis / hypothesis, §6 classification | §§7–9 |
| Phase 3 RAG | 3 | §4.2 search | §10 |
| Phase 4 Artifact UI | 4 | §4.1–4.3, §7 metrics | §11 |
| Phase 5 Handoff | 5 | §8 Phase 1 complete → Phase 2 review | §§12–14 |

**Hard constraints (do not reopen in implementation):** public data only; exactly four adapters; free stack (local models, no paid collection/LLM APIs); one-time batch snapshot; RAG answers only Google Photos photo search/retrieval questions; serving is read-only after freeze.

---

## 2. Suggested repo layout

Monorepo is sufficient (architecture §7). Keep the Python pipeline and Next.js app in one tree.

```
pipeline/                 # Python batch: adapters, normalize, classify, cluster, score, freeze
  adapters/
  normalize/
  analysis/
  rag/
  tests/fixtures/         # Play RPC envelopes, RSS pages, Arctic Shift JSON, community HTML
app/                      # Next.js research UI + route handlers
data/                     # gitignored raw payloads, SQLite snapshot, chroma/sqlite-vec, exports
config/                   # run spec, taxonomy v0, keyword lists, storefronts
docs/                     # these markdown specs
```

Default stores: SQLite + Chroma or sqlite-vec; embeddings via sentence-transformers or Ollama; classification via local Ollama LLM with Hugging Face zero-shot fallback. Same embedding model at index and query time (edge case §9).

---

## 3. Dependency graph

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
              │            │            │
              │            └─ gold set ─┘  (labels used for eval + RAG citation tests)
              └─ receipts feed methodology copy in Phase 4
```

Phase 3 can start **chunk + embed schema** in parallel with late Phase 2, but **must not** serve search until classified items and freeze model ids exist. Phase 4 UI shells can start after Phase 0 APIs are stubbed; they must bind to frozen aggregates, not live pipeline mutation.

---

## 4. Phase 0 — Foundation

**Goal**: Canonical schema, taxonomy v0, run config, empty stores, and a reproducible run command. No production collection yet.

### Work

1. **Run spec** (`config/run.yaml` or equivalent): date window, App Store storefronts, Play package `com.google.android.apps.photos`, Play `hl`/`gl`, Reddit subs + keywords, community CSE vs browse-HTML, model ids (embed + classify), taxonomy version, corpus target 500 relevant.
2. **Schema** matching architecture §5: `SourceRun`, `RawRecord`, `FeedbackItem`, `Classification`, `TaxonomyNode`, `Cluster`, `CategoryAggregate`, `EmbeddingChunk`, `MethodologySnapshot`. Support spilling large raw payloads to `data/` with path on `RawRecord` (edge §6).
3. **Taxonomy v0** as versioned config, seed from problem statement incomplete-memory scenarios, plus distinct nodes for: query/product failure with *complete* info; deleted/locked/partner-sharing “can’t find”; backup/sync/storage; search abandonment; successful workarounds. Do not hardcode UI copy to node names.
4. **Record model-run logging** fields: prompt version, model, temperature, input hash (architecture §4.3).
5. **CLI skeleton**: `collect` / `normalize` / `analyze` / `index` / `aggregate` / `freeze` as separate stages so a failed adapter does not imply a full abort.
6. **Local-only defaults**: bind later serving to localhost; document auth as optional (edge §13).
7. **Record open decisions** (architecture §16) into the first MethodologySnapshot template even if values are still TBD.

### Edge cases to design for now

- Re-run after freeze = new `run_id`; never overwrite frozen aggregates (edge §6, §11).
- `authored_at` vs `captured_at` both stored; trends/filters use `authored_at` when present.
- No identity join across sources (edge §6).
- Redaction flag on items for shared exports (edge §8, §12).

### Exit criteria

- Empty snapshot DB can be created from schema.
- Taxonomy v0 loads and is referenced by id, not strings in code.
- Pipeline stages are independently invokable and write receipts even on no-op.
- README states: public data only, no Community Console, no paid APIs, localhost default.

---

## 5. Phase 1 — Collection and relevance

**Goal**: Four adapters + receipts + normalize + relevance filter. Target **≥500 relevant** items, or a *visible* miss (do not hide it).

Implement adapters in this order (increasing brittleness): **App Store RSS → Reddit Arctic Shift → Play `batchexecute` → Help Community**. App Store and Reddit prove the pipeline; Play needs fixture-tested parsing; community needs CSE quota + HTML/Playwright.

### 5.1 Apple App Store RSS (edge §2)

- JSON feed, pages 1–10 per configured storefront; skip first entry if it is app metadata (`im:rating` / review id required).
- Empty body / title-only / ratings-without-text: raw store only, not analysis corpus.
- Dedupe by native review id across storefronts; record storefronts seen.
- 404/unknown country: skip storefront, do not abort App Store `SourceRun`.
- Parse failure / XML vs JSON surprise: **fail that SourceRun**, do not guess fields.
- 429: backoff and resume; partial receipt with last successful page.
- Keep non-English reviews; set `locale` from storefront.
- Receipt must state ~500 most-recent-written-reviews-per-country cap (methodology copy later).

### 5.2 Reddit Arctic Shift (edge §4)

- Always subreddit-scoped (`googlephotos` + run-spec list). Never unscoped “all of Reddit.”
- Posts + comments; rebuild `thread_context`; fetch parent if comment retained without post.
- `[deleted]`/`[removed]`: keep title; mark body missing.
- Honor `after`/`before`; do not widen the snapshot window.
- Arctic Shift down: **do not** switch to paid Reddit API; freeze Reddit as documented gap.
- Backup/storage keyword hits stay in raw; relevance classifier drops them from corpus.

### 5.3 Google Play `batchexecute` (edge §3)

- Isolate parser; fixture-test `)]}'` unwrap and nested JSON-as-string.
- Fail fast if package ≠ `com.google.android.apps.photos`.
- Fail `SourceRun` on payload-shape change or HTML/CAPTCHA interstitial — never “best guess” array indexes, never parse HTML as reviews.
- Continuation token: stop if missing, unchanged, or already seen.
- Dedupe by Play review id across `hl`/`gl`.
- Store developer reply separately; never classify it as user pain.

### 5.4 Help Community (edge §5)

- Discover via CSE (`site:support.google.com/photos/thread`) within 100 queries/day; fallback polite public browse/search HTML.
- Discard any URL not under `support.google.com/photos/thread` (blocker).
- Canonicalize thread id (http/https, `hl=`, trailing slug).
- Fetch public HTML; if JS-rendered, Playwright + Firefox on the **same public URL**. Abort on login wall; never Community Console.
- Preserve recommended/relevant reply flags; classify user question + user replies, not Product Expert boilerplate as user memory.
- Long threads: chunk by post, keep thread id on every chunk.
- 404 after discovery: skip; count discovery-without-fetch on receipt.
- Quota exhaustion: stop CSE, fall back or resume next day; receipt records both.

### 5.5 Normalize and relevance (edge §7)

- Canonical `FeedbackItem`; strip HTML/markdown to readable text; keep original in raw.
- Relevance labels: `retrieval_related` | `unrelated` | `ambiguous`. Ambiguous **excluded from headline frequency** until a human accepts it.
- Watch confusion: library value degradation / incomplete memory vs deleted/trashed vs backup-sync-device-change vs “search settings / people to share with.”
- Synthesize `source_url` from source + native id when possible; items without a citable URL cannot appear in RAG.

### 5.6 Cross-source (edge §6)

- Partial snapshot allowed if receipts show which source is missing; later dashboard banner required.
- Same story on Play and Reddit: near-dup **theme** clustering only — never merge identities.
- Relevant count &lt; 500: proceed only with explicit miss on methodology; widening keywords is a **new run**.

### Exit criteria

- Four `SourceRun` receipts exist (success, partial, or explicit gap) — never a silent skip (acceptance §14.1).
- Analysis corpus count is computed; ≥500 relevant **or** miss is stored as first-class metadata.
- Fixture tests for: RSS metadata-first entry, Play envelope unwrap, CSE off-site URL discard, continuation-token loop.
- No login, no Console APIs, no paid collectors.

---

## 6. Phase 2 — Analysis

**Goal**: Classify, extract snippets, cluster, segment-tag, score, overlay the incomplete-memory hypothesis, and publish gold-set quality metrics.

### Work

1. **Gold set**: human-labeled sample covering retrieval vs backup/delete, complete-info search failure, incomplete-memory phrasing **that is not** the Goa/café prompt examples, workarounds, abandonment-only, multi-label items (edge §8–9).
2. **Problem classification**: multi-label to taxonomy nodes; store `confidence`, `rationale`, `snippets[]`. Invalid LLM JSON: retry once, else unclassified — no regex-guessed labels.
3. **Evidence extraction**: short quotes that must appear verbatim in stored text.
4. **Clustering**: embeddings of classified items; n=1–2 clusters are not new roots without human review; giant “other” is not a ranked opportunity.
5. **Segment tagging**: library size, photo age, geo, device only when the **user** states it; else `unknown`. Do not infer geo from prompt examples (Goa).
6. **Scoring**: frequency, frustration language (not star rating alone), source diversity, emotional-value markers. Ordinal **within this snapshot**, not prevalence (architecture §9, edge §9).
7. **Hypothesis overlay**: `support` | `contradict` | `insufficient` for the incomplete-memory thesis; contradict must be visible, not buried (edge §8).
8. **Local-only inference**: Ollama or HF zero-shot; CPU/Ollama failure fails the stage — no paid API fallback.

### Exit criteria

- Confusion matrix / accuracy notes ready for methodology tab (architecture §10).
- Multi-label counting rule documented (item may increment more than one category).
- “Consistent across sources” is a computed flag (need ≥2 sources), not a label the model prints (acceptance §14.4).
- Segment unknown rates stored on aggregates (acceptance §14.5).
- Hypothesis overlay can be all three values (acceptance §14.6).

---

## 7. Phase 3 — RAG

**Goal**: Chunk, embed, index, and serve `POST /search` with a **scope gate**, reviewer-oriented **answers**, and up to two **illustrative quotes**. Optional LLM synthesis (Groq / Gemini / Hugging Face Inference) auto-enables when env keys are set; default narrative uses dashboard metrics + extractive evidence (edge §10).

### Work

1. Chunk classified (and relevant) items + optional thread context; metadata: category, source, date, severity, confidence, `item_id`. Embed text may prefix taxonomy themes for retrieval.
2. Embed with the **frozen** model id (`sentence-transformers`, e.g. BGE); persist id on index JSON and `MethodologySnapshot`.
3. Query path (architecture §4.4):

   `NL query → scope gate → embed → vector search → filters → hybrid lexical boost → cross-encoder rerank (optional) → compose answer (stats/bullets + ≤2 evidence) → optional cited LLM synthesis → related themes`

   Aggregate reviewer questions (e.g. sentiment, pain points) may answer from **precomputed dashboard metrics** when retrieval is thin; evidence is chosen by sentiment/theme, not only top vector hits.

4. **Scope gate**: in-scope only if about Google Photos photo search/retrieval (finding photos, incomplete memory, metadata/people/date/place, abandonment, workarounds for finding photos). Problem-statement example queries and synonyms (“old pictures,” “can’t remember when”) must pass.
5. Out of scope: `in_scope: false`, `hits: []`, no `cited_summary`, no related themes, explicit message. **Do not** vector-search or return weak neighbors (edge §10, acceptance §14.8).
6. In-scope with no evidence: different empty state (“no matching feedback in this snapshot”).
7. Filters excluding everything: “0 items match filters.”
8. Quotes only from stored text; evidence drawer expands truncated snippets to sentence/item boundary.
9. Missing index file: RAG tab errors with rebuild instruction; dashboard can still load (edge §13).
10. Queries stay local; do not log full queries to external services.

### Exit criteria

- Contract tests: out-of-scope queries (train the model, scraper, billing, RAG-the-system, world knowledge) return zero hits.
- In-scope synonym queries return attributed hits when corpus contains them.
- No citation whose quote is not a substring of the stored `FeedbackItem` (acceptance §14.3).
- Related themes hidden when empty — never invented.

---

## 8. Phase 4 — Artifact UI

**Goal**: Next.js research app — Dashboard, RAG search, How the Engine Works, shared evidence drawer — served from a **frozen** snapshot.

### 8.1 APIs (architecture §8)

| Route | Backing |
|-------|---------|
| `GET /insights`, `GET /categories` | `CategoryAggregate`, taxonomy |
| `POST /search`, `GET /items/:id` | vector index + `FeedbackItem` |
| `GET /methodology`, `GET /quality` | `MethodologySnapshot`, coverage/bias |

Chrome always shows `run_id` and freeze date (edge §13).

### 8.2 Dashboard (problem statement §4.1, §7)

- Total relevant data points vs 500 success bar (visible miss if below).
- Category list, frequency, relative severity, source breakdown, confidence, workarounds, segments with **unknown** shown, analysis scope.
- High-impact highlight suppressed or “low support” if n&lt;5 or single source (edge §11).
- Incomplete source mix banner if an adapter failed (edge §6, §11).
- Ranking copy: **within this snapshot**, not user-base incidence (blocker).
- Every metric click opens evidence that **sums to the number** (blocker). Empty filter state is explicit, not a blank page.
- If a trend chart exists: only within `authored_at` window; subtitle that it is not live post-analysis.

### 8.3 RAG UI (problem statement §4.2)

- **Ask the snapshot**: headline, stat tiles (for sentiment/pain themes), bullet notes, and **at most two illustrative quotes** with “why this quote” context—not a long ranked hit list.
- Starter prompts (pain points, sentiment, AI search, etc.); optional source filter.
- Next.js proxies `POST /search` via `/rag-search` to the Python read API (`8765`).
- Out-of-scope, no-match, and filter-empty are three distinct messages.

### 8.4 How the Engine Works (problem statement §4.3)

Required copy (edge §11): App Store RSS recency cap; Play RPC brittleness; Arctic Shift subreddit/keyword limits and possible gap; community CSE ranking + browse recency/recovery bias; English/public-complainer/store-extreme bias; social media excluded; no Photos telemetry; human review when confidence is low or a category would drive a roadmap bet.

### 8.5 Freeze

- Versioned export of DB + index + prompts + receipts.
- Writers cannot mutate freeze id; a new collect is a new snapshot (acceptance §14.7).
- Optional username redaction on export (edge §12).

### Exit criteria

- Three tabs + evidence drawer wired to frozen data.
- Acceptance checks 1–8 in Edge Cases §14 all pass on the candidate freeze.

---

## 9. Phase 5 — Handoff

**Goal**: Read-only hosting, export, and a limitations pack so product review (problem statement §8 Phase 2) can proceed without re-running the engine.

### Work

- Bind localhost (or internal URL + optional basic auth); warn if binding `0.0.0.0` without auth.
- Snapshot export + redaction mode for sharing outside the research team.
- One-page “how to rebuild from raw + run spec” (reproducibility target, architecture §15).
- Explicit non-claims: not a census; not causal for all Photos users; not a search product; findings evolve only with future research.
- List known gaps from receipts (failed adapter, &lt;500 relevant, CSE quota, Arctic Shift outage).

### Exit criteria

- Stakeholders can use dashboard + RAG without pipeline jobs running.
- Rebuild instructions work from stored raw + config.
- Phase 2/3 product work is documented as **out of this repo’s scope**.

---

## 10. Cross-cutting quality bar

From architecture §10 and Edge Cases §14. Track these as a single checklist at freeze:

1. Each of four sources has a receipt (success, partial, or explicit gap).
2. Relevant count and ≥500 bar (or visible miss) on the dashboard.
3. No RAG citation without a stored item containing the quote.
4. No “consistent across sources” unless ≥2 sources contribute.
5. Segment charts include `unknown`.
6. Hypothesis overlay is support / contradict / insufficient — not support-only.
7. Freeze is immutable; second collect = new run id.
8. Out-of-scope RAG: zero hits + explanation, never parametric or weak neighbors.

Non-functional (architecture §15): corpus 500+ (tolerate low thousands); precomputed aggregates; RAG interactive on this size; same config + raw rebuilds aggregates.

---

## 11. Suggested sequencing inside a small team

| Slice | Focus | Parallelism |
|-------|--------|-------------|
| Week-scale A | Phase 0 + App Store adapter + normalize + relevance v0 | UI shell stubs |
| Week-scale B | Reddit + Play fixtures/parser + receipts dashboard prototype | Gold-set labeling |
| Week-scale C | Community adapter + corpus push to 500 | Classification prompts |
| Week-scale D | Phase 2 classify/cluster/score + hypothesis overlay + evals | Chunk schema |
| Week-scale E | Phase 3 index + scope gate + search API tests | Dashboard aggregates UI |
| Week-scale F | Phase 4 polish, freeze, methodology completeness | Phase 5 export/README |

Calendar is indicative; **gates are the exit criteria**, not the week labels. Do not freeze to hit a date if acceptance §14 fails.

---

## 12. Out of scope (do not schedule)

| Item | Why |
|------|-----|
| Fifth channel, social, SerpApi, Apify, App Store Connect, Play Developer API, official Reddit API as primary | Architecture §§4.1, 12 |
| Paid LLM APIs | Free-stack constraint |
| Community Console / login-walled fetch | Edge §5, §12 |
| Continuous collectors / live trends after freeze | One-time snapshot |
| In-product Photos retrieval ML | This engine studies the problem |
| Joining public handles to Google accounts | Edge §12 blocker |
| Problem statement Phase 2–3 product roadmap | Downstream of handoff |

---

**Document version**: 1.0  
**Date**: 21 September 2026  
**Status**: Implementation plan for engineering  
**Depends on**: System Architecture v1.2, Edge Cases v1.1, Problem Statement v2.2
