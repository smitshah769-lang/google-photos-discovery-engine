# AI Discovery Engine — Google Photos retrieval feedback

One-time research platform: collect public feedback from **four sources only** (Google Play Store, Apple App Store, Reddit, Google Photos Help Community), classify retrieval problems, and serve a frozen dashboard + RAG artifact.

**Phase 0** provides schema, run config, taxonomy v0, and a staged CLI. **Phase 1** adds four source adapters, normalization, and rule-based relevance filtering. **Phase 2** classifies retrieval-related items, extracts verbatim snippets, clusters themes, tags segments, scores categories, overlays the incomplete-memory hypothesis, and writes gold-set quality metrics. **Phase 5** is the read-only handoff: localhost serving, snapshot export, rebuild-from-raw, and a limitations pack for product review.

## Constraints

- **Public data only** — no private Google Photos libraries or authenticated Photos APIs.
- **No Google Community Console** or login-walled scraping.
- **No paid APIs** for collection or models in the default stack (local Ollama / sentence-transformers).
- **Serving defaults to localhost** (`127.0.0.1` in `config/run.yaml`). Optional HTTP basic auth via `DISCOVERY_BASIC_USER` / `DISCOVERY_BASIC_PASSWORD`. Binding `0.0.0.0` without auth prints a warning.
- **Not a census, not causal, not a Photos search product.** Findings evolve only with a new research run. Problem-statement Phase 2–3 product work is out of this repo.

## Setup

```bash
cd "AI Discovery Engine - Google Photos"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # optional: Google CSE for Help Community
```

**How to pull data:** see **[docs/DATA_COLLECTION.md](./docs/DATA_COLLECTION.md)** (live Python collect is the default).

```bash
./scripts/smoke-fixtures.sh    # offline check
./scripts/collect-live.sh      # live four-source pull
```

## Phase 0 commands

```bash
# Create schema + load taxonomy into SQLite
python -m pipeline init-db

# New draft analysis run (prints run UUID)
python -m pipeline new-run

# Collect (live) or --fixtures for offline
python -m pipeline collect <run-id>
python -m pipeline collect <run-id> --fixtures
python -m pipeline normalize <run-id>
python -m pipeline status <run-id>
python -m pipeline smoke
python -m pipeline analyze <run-id>
python -m pipeline index <run-id>
python -m pipeline aggregate <run-id>
python -m pipeline freeze <run-id> --dry-run

# Or all non-freeze stages
python -m pipeline run-all <run-id>
```

Database and raw payloads live under `data/` (gitignored). Re-running after **freeze** requires a **new** `run_id`; frozen rows are not mutated in place.

## Optional: Node raw fetch (no relevancy)

```bash
npm install
export GOOGLE_CSE_API_KEY=... GOOGLE_CSE_CX=...   # optional, for Help Community
npm run fetch-raw
```

Writes `photo_retrieval_feedback.json` using the same sources and `config/run.yaml` as the Python pipeline.

Import into SQLite (then normalize as usual):

```bash
python -m pipeline import-raw                    # default: photo_retrieval_feedback.json, new run
python -m pipeline import-raw path/to.json --run-id <uuid>
python -m pipeline normalize <run-id>
```

Or use `python -m pipeline collect <run-id>` without the Node script.

## Phase 1 collection

| Source | Method |
|--------|--------|
| App Store | Public customer-reviews RSS/JSON |
| Play Store | `batchexecute` RPC (`UsvDTd`) |
| Reddit | Arctic Shift API (subreddit-scoped); records `gap` if down |
| Help Community | Google CSE (`GOOGLE_CSE_API_KEY`, `GOOGLE_CSE_CX`) + public browse HTML |

Optional env for community discovery:

```bash
export GOOGLE_CSE_API_KEY=...
export GOOGLE_CSE_CX=...
```

After `normalize`, `methodology_snapshot.coverage_stats_json` includes `relevant_count`, `meets_target`, and `target_miss_visible` when below 500.

## Phase 2 analysis

```bash
python -m pipeline analyze <run-id>
```

Requires a completed `normalize` so `feedback_item` rows exist. Default `config/run.yaml` uses the **heuristic** classifier and hashing embeddings (offline). For a local LLM:

```yaml
models:
  classification:
    provider: ollama
    model_id: qwen2.5:7b   # must be pulled in Ollama
    fallback_provider: huggingface  # optional, still local; never a paid API
  embedding:
    provider: sentence-transformers
    model_id: BAAI/bge-small-en-v1.5
```

If Ollama/CPU inference fails and no local fallback is configured, **analyze fails** — there is no paid API fallback.

Outputs (per run):

- `classification` rows (multi-label taxonomy ids, confidence, rationale, verbatim `snippets`)
- `feedback_item.segments_json` (`library_size`, `photo_age`, `geo`, `device`, `hypothesis_overlay`) — `unknown` unless the **user** stated it
- `cluster` rows (n=1–2 flagged for human review; giant `other` is not a ranked opportunity)
- `category_aggregate` with `consistent_across_sources` (**computed** when ≥2 sources) and segment unknown rates
- methodology `gold_eval` (per-label precision/recall + exact-set accuracy) from `config/gold_set.json`

Multi-label counting: one item may increment more than one category. Ranking is **within this snapshot**, not user-base prevalence. Hypothesis overlay values are `support`, `contradict`, and `insufficient` (not support-only).

## Phase 3 RAG (index + search)

Build the vector index (after `analyze`). Uses `models.embedding` from `config/run.yaml` — **same provider/model at index and query time**.

```bash
python -m pipeline index <run-id>
python -m pipeline search <run-id> -q "users struggling to find old photos"
python -m pipeline serve <run-id>          # POST http://127.0.0.1:8765/search {"query":"..."}
```

Index file: `data/rag/<run-id>.json` next to SQLite. Out-of-scope queries return zero hits without vector search. Optional cited synthesis: `rag.synthesis.enabled` in `run.yaml` (off by default). For a **free, high-quality** embed + rerank + LLM stack, see **[docs/FREE_RAG.md](./docs/FREE_RAG.md)**.

## Phase 4 artifact UI

Precompute dashboard JSON, freeze an immutable export, and serve the research app from that snapshot.

```bash
python -m pipeline aggregate <run-id>
python -m pipeline freeze <run-id>            # writes data/exports/<run-id>/
python -m pipeline freeze <run-id> --redact   # usernames redacted in the export copy only
python -m pipeline serve <run-id>             # GET /insights /categories /methodology /quality /items/:id  POST /search
```

Chrome always shows `run_id` and freeze date. Ranking copy is **within this snapshot**, not user-base incidence.

```bash
./scripts/serve-artifact.sh <run-id>
```

- Read API: `http://127.0.0.1:8765` (localhost default; do not bind `0.0.0.0` without auth)
- UI: `http://127.0.0.1:3000` — Dashboard, RAG search, How the Engine Works, evidence drawer

A second collect after freeze requires a **new** `run_id`. `serve-search` remains an alias of `serve`.

## Phase 5 handoff

Read-only hosting so stakeholders can use dashboard + RAG **without pipeline jobs**. See **[docs/HANDOFF.md](./docs/HANDOFF.md)** and **[docs/REBUILD.md](./docs/REBUILD.md)**.

```bash
python -m pipeline serve <run-id>                 # GET /handoff plus existing read APIs
python -m pipeline serve --export-dir data/exports/<run-id>
python -m pipeline export <run-id> --redact       # shareable copy; names stripped
python -m pipeline rebuild <run-id>               # from stored raw; refused if frozen
python -m pipeline rebuild-from-export data/exports/<run-id>
python -m pipeline handoff <run-id>
./scripts/serve-artifact.sh <run-id>
```

UI tab **Handoff** lists non-claims, known gaps from receipts (failed adapter, &lt;500 relevant, CSE quota, Arctic Shift outage), rebuild steps, and out-of-repo Phase 2/3 product work.

## Configuration

| File | Purpose |
|------|---------|
| `config/run.yaml` | Date window, storefronts, Play package, Reddit keywords, `collection.mode`, corpus target (500 relevant), classify/embed providers |
| `config/taxonomy_v0.yaml` | Versioned problem taxonomy — reference nodes by `id` |
| `config/gold_set.json` | Human labels for methodology accuracy / confusion notes |
| `config/prompts/classify_v0.txt` | Classification prompt (no Goa/café examples) |
| `config/methodology_template.yaml` | Open decisions (architecture §16) and limitation seeds |

## Layout

```
config/          Run spec and taxonomy
pipeline/        Python batch CLI and SQLite schema
data/            Snapshot DB and raw JSON (local only)
app/             Next.js research UI (Dashboard, RAG, How it works, Handoff)
docs/            Collection, rebuild, and handoff notes
```

## Specs

- [Problem Statement .md](./Problem%20Statement%20.md)
- [System Architecture.md](./System%20Architecture.md)
- [Edge Cases.md](./Edge%20Cases.md)
- [Implementation Plan.md](./Implementation%20Plan.md)
- [docs/HANDOFF.md](./docs/HANDOFF.md)
- [docs/REBUILD.md](./docs/REBUILD.md)

## Tests

```bash
pytest
```
