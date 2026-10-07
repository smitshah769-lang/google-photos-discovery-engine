# AI Discovery Engine — System Architecture

**Document type**: Target system architecture  
**Aligned to**: [Problem Statement .md](./Problem%20Statement%20.md) v2.2 (21 Sep 2026)  
**Scope**: One-time analysis of public user feedback about Google Photos photo retrieval  
**Sources in scope**: Google Play Store, Apple App Store, Reddit, Google Photos Help Community only  
**Audience**: Engineering, research, and product stakeholders implementing the discovery engine

---

## 1. Purpose and architectural intent

Users with large libraries fail to retrieve photos they know exist when memory is incomplete. Product teams currently lack a systematic, evidence-backed view of those failures.

This system is **not** a Google Photos search product. It is a **one-time research platform** that:

1. Collects public feedback about photo retrieval
2. Classifies and clusters that feedback with AI
3. Surfaces quantified problem categories on a dashboard
4. Lets researchers and PMs explore evidence via RAG search
5. Documents methodology, confidence, and limitations in a “How the Engine Works” tab

Architecture is optimized for **reproducible snapshot analysis**, source attribution, and inspectable methodology—not for continuous ingestion, real-time serving, or in-product photo retrieval.

---

## 2. Design principles

| Principle | Implication |
|-----------|-------------|
| Evidence over assumption | Every dashboard claim traces to stored feedback records and snippets |
| One-time snapshot | Pipeline is batch-oriented; no always-on collectors or live trend pipelines |
| Meaning over keywords | Retrieval of evidence uses embeddings + semantic ranking, not only lexical search |
| Transparency by default | Classification confidence, source mix, date range, and known blind spots are first-class UI data |
| Attribution | Every snippet carries channel, URL/id, capture date, and original text |
| Public data only | Ingest reviews and forum posts that are already public; no private Google Photos libraries or user accounts |
| Four sources only | Play Store, App Store, Reddit, and Google Photos Help Community; no social media or paid review APIs |
| Free stack | Collectors, stores, embeddings, and classifiers use no-cost software and local or free-tier models |
| Human-over-AI | Automated labels are hypotheses; the methodology surface states when judgment is required |
| Comparability | Problem categories share the same scoring model so impact can be ranked |

---

## 3. High-level architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Presentation layer                               │
│  Dashboard  │  RAG Search  │  How the Engine Works  │  Evidence drawer  │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│                         Application layer                                │
│  Insights API  │  Semantic search API  │  Methodology / metrics API     │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│                      Intelligence & processing                           │
│  Ingest  →  Normalize  →  Filter  →  Classify  →  Cluster  →  Score     │
│                              ↓                                           │
│                    Embed  →  Index (vector + metadata)                   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────┐
│                           Data layer                                     │
│  Raw store  │  Canonical feedback DB  │  Taxonomy  │  Vector index      │
│  Artifacts (run config, prompts, evals, export snapshots)                │
└──────────────────────────────────────────────────────────────────────────┘
                                ▲
┌───────────────────────────────┴──────────────────────────────────────────┐
│                     Source adapters (batch, four only)                   │
│  Play Store (batchexecute)  │  App Store (RSS)                           │
│  Reddit (Arctic Shift)      │  Photos Help Community (search + HTML)     │
└──────────────────────────────────────────────────────────────────────────┘
```

Three user-facing surfaces map 1:1 to problem-statement deliverables (sections 4.1–4.3):

| Surface | Primary backing stores |
|---------|------------------------|
| Dashboard | Aggregates, category scores, segment rollups |
| RAG search | Vector index + canonical feedback records |
| How the Engine Works | Run metadata, taxonomy, quality metrics, caveats |

---

## 4. Logical components

### 4.1 Source adapters (data collection)

**Role**: Pull public feedback that may describe retrieval difficulty, incomplete memory, search abandonment, or workarounds.

Collection is **exactly four adapters**. Social media, SerpApi, Apify, App Store Connect, Play Developer API, and Reddit’s official API are not used.

Each adapter writes **immutable raw payloads** plus a **collection receipt** (source, endpoint/query used, window, count, captured_at, known coverage limits). Receipts feed the methodology tab.

**Out of collection**: private libraries, authenticated Photos APIs, login-walled community consoles, PII harvest beyond what the public post already contains.

#### 4.1.1 Apple App Store — customer reviews RSS

| | |
|--|--|
| **Method** | Official public RSS/JSON feed on `itunes.apple.com` (no API key) |
| **Target app** | Google Photos (numeric App Store id, configured in run spec) |
| **Endpoint pattern** | `https://itunes.apple.com/{country}/rss/customerreviews/page={1–10}/id={appId}/sortby=mostrecent/json` |
| **Artifacts** | Review id, title, body, star rating, author name, app version, storefront, updated date, review URL |
| **Pagination** | Pages 1–10 per storefront (~50 reviews/page) |
| **Coverage limit** | Roughly **500 most recent written reviews per country**. Ratings-without-text and full history are not available on this feed. |
| **Collection plan** | Iterate a configured list of storefronts (at least `us` plus high-volume locales); dedupe by review id across countries; skip the first feed entry when it is app metadata rather than a review. |

Prefer JSON (`/json`) over Atom. Throttle politely between page and country requests. Do **not** use paid App Store Connect or third-party review APIs.

#### 4.1.2 Google Play Store — `batchexecute` RPC

| | |
|--|--|
| **Method** | Same undocumented Play Store UI RPC the web reviews tab uses (`batchexecute`, RPC id `UsvDTd`) |
| **Target app** | `com.google.android.apps.photos` |
| **Endpoint** | `POST https://play.google.com/_/PlayStoreUi/data/batchexecute` with `rpcids=UsvDTd`, `hl`, `gl` |
| **Body** | URL-encoded `f.req` wrapping package name, sort, page size, and continuation token |
| **Artifacts** | Review id, text, score, date, thumbs-up, optional device/app version, developer reply |
| **Pagination** | Continuation token until cap or empty page |
| **Coverage limit** | Undocumented and can change; no official ceiling like Apple’s 10 pages, but responses are nested unlabeled JSON and parsers must be defensive |

Implementation options (all free): a small in-repo client, or the MIT `google-play-scraper` / fetch-only ports that wrap this RPC. Isolate parsing so a Google payload-shape change does not rewrite the rest of the pipeline.

Sort newest-first for the snapshot window. Vary `hl`/`gl` only as needed for coverage; record locale on each `RawRecord`. Throttle between pages. Treat this adapter as **brittle**: pin a fixture-tested parser and fail the `SourceRun` clearly if the envelope cannot be parsed.

#### 4.1.3 Reddit — Arctic Shift API

| | |
|--|--|
| **Method** | Free research API over Arctic Shift dumps (`https://arctic-shift.photon-reddit.com`) |
| **Endpoints** | `GET /api/posts/search`, `GET /api/comments/search` |
| **Primary subreddit** | `googlephotos` (plus a small configured list of related subs if the run spec includes them) |
| **Query** | Keyword/query on title/selftext/body for retrieval language (`search`, `can't find`, `old photos`, `screenshot`, etc.), bounded by `after` / `before` |
| **Artifacts** | Post/comment id, subreddit, created_utc, title, selftext/body, score, permalink, parent/link id for thread rebuild |
| **Pagination** | `limit` (1–100, or `auto`); walk with `after`/`before` and `sort=asc` |
| **Coverage limit** | Text search is **subreddit- or author-scoped**, not “all of Reddit”. Very large subs may have weaker keyword search. This is a community-run service: rate-limit, cache, and record outages in the receipt. |

Rebuild thread context by fetching comments for retained post ids. Do not use paid Pushshift replacements or authenticated Reddit API unless Arctic Shift is unavailable; if it is down, freeze Reddit coverage as a documented gap rather than switching to a paid source.

#### 4.1.4 Google Photos Help Community — no official API

There is **no free official API** for [Google Photos Help Community](https://support.google.com/photos/community) threads (`support.google.com/photos/thread/...`). Paid Google-forums scrapers (SerpApi, Apify, etc.) are out of stack.

**Chosen free approach (two stages):**

1. **Discover thread URLs (preferred)**  
   Google Programmable Search Engine + Custom Search JSON API, restricted to  
   `site:support.google.com/photos/thread`  
   with retrieval-related queries.  
   **Free quota**: 100 queries/day (enough for a one-time snapshot if queries are batched).  
   Fallback discovery if CSE quota is exhausted: polite crawl of the public browse/search HTML at `https://support.google.com/photos/threads` and community search pages, extracting thread links only.

2. **Fetch public thread pages**  
   HTTP GET each discovered public thread URL. Parse title, original post, replies, recommended/relevant answers, dates, and permalinks from the public HTML.  
   If the list or thread body is client-rendered, use **headless Firefox via Playwright** (free) against the same public URLs—no login, no Community Console.

**Do not** call internal Community Console APIs (e.g. `ViewThread` for Product Experts). Those are not a public collection contract and can expose non-public fields.

| | |
|--|--|
| **Artifacts** | Thread id, URL, title, question body, reply bodies, recommended-answer flags, timestamps, public display names |
| **Coverage limit** | CSE ranking ≠ complete forum census; browse-page crawl is recency-biased. Document both as methodology caveats. |

Each adapter’s `query_spec` is stored on `SourceRun` so the How the Engine Works tab can show exact feeds, RPCs, Arctic Shift params, and CSE queries used.

### 4.2 Normalization and relevance filter

**Role**: Turn heterogeneous source JSON into a canonical `FeedbackItem`.

Canonical fields (minimum):

- `id`, `source`, `source_url`, `captured_at`, `authored_at`
- `author_handle` (public only, optional), `locale`, `geo` (if public)
- `raw_text`, `thread_context`
- `library_size_signal`, `photo_age_signal`, `device_type` (extracted later or unknown)
- `relevance_score`, `relevance_label` (`retrieval_related` | `unrelated` | `ambiguous`)

A **relevance classifier** (local LLM or zero-shot model with keyword rules) keeps items about finding/searching photos, metadata, people, dates, screenshots, albums, and related workarounds. Unrelated store-review noise is retained in raw store but excluded from analysis corpus.

Target corpus size from the problem statement: **500+ relevant data points** after filtering.

### 4.3 Analysis engine (intelligent analysis)

**Role**: Classify, cluster, extract evidence, and quantify impact.

Pipeline stages:

1. **Problem classification** — Map each item to one or more nodes in the retrieval-problem taxonomy (incomplete memory, missing metadata, people search, time/place vagueness, screenshot/object search, abandonment after 2–3 tries, etc.). Store `labels[]`, `confidence`, `rationale`.
2. **Evidence extraction** — Pull short snippets that illustrate the problem type (quotes used in dashboard and RAG).
3. **Clustering / theme detection** — Embed classified items; cluster to find cross-source themes (e.g. “holiday with sibling, unknown year”).
4. **Segment tagging** — Infer or extract library size, photo age, geography, device when the text supports it; else `unknown`.
5. **Scoring** — Per category: frequency, sentiment/severity, source diversity, confidence. Used for “high-impact” highlighting.
6. **Hypothesis overlay** — Compare labeled data against the problem statement’s incomplete-memory hypothesis; record support / contradict / insufficient.

All model calls are **logged** (prompt version, model, temperature, input hash) so the methodology tab can show how classification worked.

### 4.4 RAG subsystem

**Role**: Natural-language exploration of the problem space with semantic retrieval and attribution (problem statement §4.2).

RAG answers **only** Google Photos **photo search / retrieval** questions about this snapshot (finding photos, incomplete memory, metadata/people/date/place search, search abandonment, workarounds for finding photos). It is not a general assistant and must not use parametric knowledge.

**In-scope examples** (must retrieve):

- How do users struggle to find old photos?
- What problems occur with metadata?
- How do users describe incomplete memory scenarios?
- What workarounds do users mention?

**Out-of-scope examples** (must not retrieve):

- How do I train the model?
- How does this discovery engine work? (that belongs on the How the Engine Works tab, not RAG hits)
- Write code / scrape Play Store
- Google Photos billing, backup, or storage unless the query is about **finding** photos
- Unrelated world knowledge

**Out-of-scope contract:** return `hits = []`, no `cited_summary`, no related themes, and an explicit explanation that the query falls outside the Google Photos search/retrieval scope. Do **not** return low-relevance snippets.

**Index units**: chunked feedback (review/comment + optional thread context), tagged with category, source, date, severity, confidence.

**Query path** (as built):

```
NL query → scope gate (retrieval + reviewer snapshot questions, e.g. sentiment/pain themes)
       → if out of scope: empty hits + explanation; stop
       → embed (same model as index) → vector search (fetch_k) → metadata filters
       → hybrid lexical boost → cross-encoder rerank (BGE reranker, optional)
       → compose answer { headline, stats?, bullets?, summary, evidence[≤2] }
       → optional LLM cited synthesis (Groq / Gemini / HF Inference; env keys)
       → related themes (nearest clusters)
```

Evidence quotes are **verbatim** from stored `FeedbackItem` text. For aggregate queries, illustrative quotes are sampled by **labeled sentiment or taxonomy theme**, not only vector rank. UI presents stats + short narrative first; LLM synthesis is optional enrichment, not the default contract.

### 4.5 Insights aggregation (dashboard)

**Role**: Precompute the metrics in problem statement §7 so the UI does not scan the full corpus on every load.

Precomputed views:

- Total relevant data points
- Problem category list + frequency distribution
- Relative severity (volume × sentiment/impact)
- Source breakdown
- Confidence per category
- Top workarounds
- Segment breakdowns (library size, photo age, geography) with `unknown` called out
- Analysis scope (date range, sources, run id)

Trend charts, if shown, are **within the collected window only** (not live post-analysis trends). The methodology tab must state that limitation.

### 4.6 Presentation application

Single web app, three tabs plus an evidence drawer:

| Tab | Behavior |
|-----|----------|
| **Dashboard** | Category cards, charts, severity ranking, segment filters, highlight high-impact problems |
| **RAG search** | Query box, ranked snippets, source links, related problems, “use as evidence” copy |
| **How the Engine Works** | Sources, scope, taxonomy, classification logic, quality metrics, bias notes, what the engine cannot reveal |

The evidence drawer opens from dashboard cells and search hits to the same `FeedbackItem` record.

---

## 5. Data model (conceptual)

```
SourceRun
  id, source, query_spec, started_at, finished_at, item_count, notes

RawRecord
  id, source_run_id, source_native_id, payload_json, captured_at

FeedbackItem
  id, raw_record_id, source, source_url, authored_at, locale
  text, thread_context
  relevance_label, relevance_confidence
  segments { library_size?, photo_age?, geo?, device? }

Classification
  feedback_item_id, taxonomy_node_id, confidence, rationale, model_run_id
  snippets[]

TaxonomyNode
  id, name, definition, parent_id, examples

Cluster
  id, label, member_ids[], cohesion_score

CategoryAggregate
  taxonomy_node_id, frequency, severity, source_mix, avg_confidence
  workaround_ids[]

EmbeddingChunk
  id, feedback_item_id, text, vector_id, metadata

MethodologySnapshot
  run_id, prompts, model_ids, coverage_stats, bias_notes, limitations[]
```

---

## 6. End-to-end data flow

```
1. Configure analysis run (sources, date window, taxomomy version, models)
2. Adapters fetch → Raw store + SourceRun receipts
3. Normalize → FeedbackItem
4. Relevance filter → analysis corpus (target ≥ 500 relevant items)
5. Classify + extract snippets + segment tags
6. Cluster themes; score categories; overlay hypotheses
7. Chunk + embed → vector index
8. Write CategoryAggregate + MethodologySnapshot
9. Freeze snapshot (versioned export)
10. Serve dashboard, RAG, and methodology from the frozen snapshot
```

After freeze, the serving stack is **read-only**. Re-running the engine is a **new snapshot**, not an in-place mutation—consistent with “one-time analysis” and “findings may evolve only with future research.”

---

## 7. Technical stack (free only)

Default to **no-cost software and locally run models**. Paid APIs (OpenAI, Anthropic, SerpApi, Apify, App Store Connect, Play Developer API) are out of the default stack. A vendor free tier is allowed only as a documented overflow (e.g. Custom Search JSON API’s 100 queries/day for community URL discovery).

| Layer | Choice | Cost / license |
|-------|--------|----------------|
| UI | Next.js research app (dashboard, search, methodology) | Open source |
| Insights / search API | **Python read-only HTTP server** (`python -m pipeline serve`, port 8765) + Next.js rewrites/`/rag-search` proxy | Open source |
| Batch pipeline | Python collectors, classification, clustering | Open source |
| Canonical DB | **SQLite** for the portable snapshot (default); Postgres+pgvector only if already available locally | Open source |
| Vector index | Co-located JSON (`data/rag/<run-id>.json`) beside SQLite | Portable snapshot artifact |
| Embeddings | **sentence-transformers** (`BAAI/bge-small-en-v1.5` or `bge-large-en-v1.5`) on CPU; optional **Ollama** `nomic-embed-text` | Free local weights |
| Search rerank | **Cross-encoder** (`BAAI/bge-reranker-base`) at query time | Free local weights |
| Search LLM (optional) | Groq, Gemini, or Hugging Face Inference for one completion per question | Free tier keys only |
| Classification / clustering | **Ollama** local LLM (Llama, Qwen, or Mistral class) with structured JSON; fallback **Hugging Face** zero-shot (`facebook/bart-large-mnli`) if CPU budget is tight | Free local weights |
| Play adapter | In-repo `batchexecute` client, or MIT `google-play-scraper` / fetch-only port | Free; undocumented RPC |
| App Store adapter | stdlib HTTP client vs RSS/JSON | Free public feed |
| Reddit adapter | HTTP client vs Arctic Shift (optional `arcshiftwrap`) | Free community API |
| Community adapter | Custom Search JSON API (free quota) + HTML parse; Playwright + Firefox if JS-rendered | Free; CSE daily quota |
| Object / file store | Local `data/` on disk (raw JSON, prompts, evals, exports) | No cloud bill |
| Auth | Optional HTTP basic auth or local-only bind | No paid IdP required |

Same embedding model **must** be used at index time and query time.

At this corpus size, a **monorepo with a Python batch job + a static or lightly dynamic dashboard** is sufficient. Do not introduce streaming, microservices-per-adapter, or paid model routers.

---

## 8. Application architecture (serving)

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Dashboard  │────▶│  GET /insights   │────▶│  aggregates     │
│  UI         │     │  GET /categories │     │  taxonomy       │
└─────────────┘     └──────────────────┘     └─────────────────┘

┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  RAG UI     │────▶│  POST /search    │────▶│  vector index   │
│             │     │  GET /items/:id  │     │  feedback items │
└─────────────┘     └──────────────────┘     └─────────────────┘

┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  How it     │────▶│  GET /methodology│────▶│  snapshot meta  │
│  works UI   │     │  GET /quality    │     │  coverage/bias  │
└─────────────┘     └──────────────────┘     └─────────────────┘
```

Search request contract (logical):

- Input: `query`, optional `filters` (source, category, date, `min_confidence`)
- Output (in scope): `answer` object — `headline`, `summary`, optional `stats[]` / `bullets[]`, `evidence[]` (≤2, with `context`), plus chrome metadata; `hits[]` omitted from JSON for reviewer UI (still computed server-side). Optional `cited_summary` when LLM synthesis succeeds.
- Output (out of scope): `in_scope: false`, `hits: []`, no `answer`, explicit `message`

**Hosting note:** The UI alone can deploy to **Vercel**, but search and dashboard require the **Python read API** plus frozen `snapshot.db` and `data/rag/` on a persistent host (VM, Railway, Fly.io, Render). See `docs/HOSTING.md`.

---

## 9. Taxonomy and scoring

Taxonomy is versioned configuration, not hardcoded UI copy. Seed from the problem statement’s incomplete-memory scenarios, then expand only when clusters have supporting evidence.

**Illustrative root nodes** (to be confirmed by the engine, not assumed as final):

- Incomplete memory (place + event, no date; person + occasion; object + rough time)
- Query formulation / keyword mismatch
- Metadata gaps (date, location, people)
- Library scale / recency (old photos, 3,000+ items)
- Search abandonment and manual browse
- Workaround strategies that succeeded

**Severity (relative, within this snapshot)**:

```
severity ≈ f(frequency, negative sentiment / frustration language,
             source diversity, emotional-value markers)
```

Scores are **ordinal for ranking inside this analysis**, not population incidence. The methodology tab must state that public-feedback volume ≠ true user prevalence.

---

## 10. Quality, validation, and bias

Required for success criteria (problem statement §6) and the methodology tab.

| Control | Mechanism |
|---------|-----------|
| Classification confidence | Model-reported + optional second-pass or human sample |
| Reproducibility across sources | Category must appear in >1 channel when claimed as “consistent” |
| Accuracy check | Gold set of labeled reviews; confusion matrix published in methodology |
| Coverage | Counts by geo, locale, device, segment; explicit `unknown` rates |
| Bias | Over-weight of English, public complainers, store-review extremes; App Store recency cap; Reddit subreddit-scoped search; community CSE ranking. Mitigation: source mix on aggregates, not treating volume as prevalence |
| Hallucination | RAG answers grounded only in retrieved chunks; quotes must match stored text |
| Out-of-scope RAG | Scope gate rejects non–photo-retrieval queries with empty hits; no parametric answer |
| Blind spots | Social media (explicitly excluded); private chats; users who never post; App Store history beyond ~500/storefront; Arctic Shift keyword limits; Help Community incomplete census; Photos-internal telemetry (unavailable) |

Human review is required when confidence is low, items are ambiguous, or a category would drive a roadmap bet.

---

## 11. Security, privacy, and compliance

- Collect **only public** posts/reviews from the four adapters above; respect each platform’s terms and rate limits.
- Store original URLs and text for attribution; do not scrape behind login walls or use Community Console endpoints.
- Minimize retained profile fields; no attempt to join public handles to Google accounts.
- Restrict the research app to internal users (or localhost).
- Do not send corpus text to paid third-party model APIs in the default pipeline; inference stays local.
- Snapshot exports used for sharing should support redaction of usernames if needed.

This system **never** accesses Google Photos libraries, EXIF from user files, or production Photos search indexes.

---

## 12. What is explicitly out of scope

| Out of scope | Why |
|--------------|-----|
| Social media (X, etc.) and any fifth channel | Locked to four sources |
| Paid collection or model APIs | Free-stack constraint |
| App Store Connect / Play Developer Console dumps | Would require developer-account access; RSS and `batchexecute` are the chosen public paths |
| Internal Google Community Console APIs | Not a public collection contract |
| In-product photo retrieval / ML for finding photos in a library | This engine studies the *problem*; it is not the solution product |
| Continuous collection and live dashboards after freeze | One-time snapshot (problem statement §3, §8) |
| Causal claims about all Google Photos users | Public feedback is biased; engine reports evidence, not census |
| Building the Phase 3 product roadmap features | Downstream of this artifact |
| Replacing qualitative interviews | Complements them; methodology must say when human research is still required |

---

## 13. Mapping to problem-statement success criteria

| Success criterion | Architectural support |
|-------------------|------------------------|
| Sufficient relevant data points | Multi-adapter ingest + relevance filter + coverage metrics |
| High-confidence classification | Structured local-LLM labels, confidence fields, gold-set eval |
| Distinct categories with evidence | Taxonomy + snippets + clusters |
| Consistent across segments/sources | Segment tags + source-mix on aggregates |
| Actionable insights for roadmap | Severity ranking + opportunity overlay on dashboard |
| Functional RAG | Embedding index + cited search API |
| Transparent methodology | Methodology snapshot + dedicated tab |
| Durable dashboard artifact | Frozen snapshot + versioned export |

---

## 14. Delivery phases (implementation)

Aligns with problem statement §8 (discovery → review → later product work).

| Phase | Architecture work |
|-------|-------------------|
| **0. Foundation** | Canonical schema, taxonomy v0, run config, raw + canonical stores |
| **1. Collection** | Four adapters (RSS, `batchexecute`, Arctic Shift, CSE+HTML), receipts, relevance filter, corpus ≥ 500 |
| **2. Analysis** | Classify, cluster, score, hypothesis overlay, evals |
| **3. RAG** | Chunk, embed, search API, citation UX |
| **4. Artifact UI** | Dashboard, search, How the Engine Works, freeze snapshot |
| **5. Handoff** | Read-only hosting, export, known limitations for Phase 2 product review |

---

## 15. Non-functional targets (for this snapshot)

| Concern | Target |
|---------|--------|
| Corpus | 500+ relevant items (success bar); pipeline should tolerate low thousands |
| Dashboard load | Aggregates precomputed; interactive filters without full-corpus scans |
| RAG latency | Interactive (sub-few-seconds) on this corpus size |
| Reproducibility | Same run config + stored raw data can rebuild aggregates |
| Durability | Snapshot remains the “definitive reference” without live jobs |

---

## 16. Open decisions

These do not block the architecture; they should be recorded in the first `MethodologySnapshot`:

1. App Store storefront list and Play `hl`/`gl` locales for the snapshot
2. Reddit subreddit list and keyword set (beyond `r/googlephotos`)
3. Whether community discovery uses CSE only, browse-HTML only, or both
4. Local embedding + chat model IDs actually used (Ollama vs sentence-transformers)
5. Human-annotation sample size for gold labels
6. Whether RAG returns extractive snippets only or also a cited summary
7. Hosting of the frozen artifact (internal URL vs. static export)

---

**Document version**: 1.2  
**Date**: 21 September 2026  
**Status**: Target architecture for implementation  
**Depends on**: Problem Statement v2.2 — one-time AI-powered discovery engine, four public sources, free stack, RAG retrieval-scope gate
