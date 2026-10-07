# Data collection — operational guide

**Default:** Python `python -m pipeline collect` → optional `normalize`.  
**Alternate:** `npm run fetch-raw` → `python -m pipeline import-raw`.

Success bar: **≥500 `retrieval_related` items after `normalize`**, across all four sources combined (not per source).

---

## 1. One-time setup

```bash
cd "AI Discovery Engine - Google Photos"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy env template for Help Community discovery (recommended for live runs):

```bash
cp .env.example .env
```

**CSE setup (embed code ≠ API):** The HTML snippet from [Programmable Search](https://programmablesearchengine.google.com/) (`cse.js?cx=…`) only provides **`GOOGLE_CSE_CX`**. The pipeline calls the **Custom Search JSON API**, so you also need **`GOOGLE_CSE_API_KEY`** from Google Cloud (enable **Custom Search API**, create an API key). Configure the search engine to search the **entire web** (the pipeline restricts with `siteSearch` in `config/run.yaml`).

Example `.env`:

```bash
GOOGLE_CSE_CX=d086cd3ddd3ef49de
GOOGLE_CSE_API_KEY=your_cloud_api_key_here
```

The pipeline loads `.env` automatically when `python-dotenv` is installed.

---

## 2. Smoke test (offline, ~1 minute)

Verifies adapters, SQLite, and normalize without network:

```bash
./scripts/smoke-fixtures.sh
# or
python -m pipeline smoke
```

---

## 3. Live collection (primary)

```bash
./scripts/collect-live.sh
```

Or manually:

```bash
python -m pipeline init-db
RUN=$(python -m pipeline new-run)
python -m pipeline collect "$RUN"
python -m pipeline status "$RUN"
python -m pipeline normalize "$RUN"
python -m pipeline status "$RUN"
```

**Duration:** Often 20–60+ minutes (App Store pages × storefronts, Reddit keyword loops).

| Source | Live requirement |
|--------|------------------|
| App Store | Network; JSON RSS in `config/run.yaml` |
| Play | Network; `batchexecute` (may fail if Google changes RPC) |
| Reddit | [Arctic Shift API](https://github.com/ArthurHeitmann/arctic_shift/tree/master/api) — posts use `query`, comments use `body` (not `q`); else receipt `gap` |
| Help Community | CSE keys in `.env` strongly recommended; browse fallback is thin |

Check receipts:

```bash
python -m pipeline status "$RUN"
```

---

## 4. Alternate: Node JSON → SQLite

```bash
npm install
npm run fetch-raw
python -m pipeline import-raw --run-id "$RUN"   # or omit --run-id for new run
python -m pipeline normalize "$RUN"
```

Use when Play is easier via `google-play-scraper` or you want `photo_retrieval_feedback.json` to inspect before import.

---

## 5. If relevant count &lt; 500

1. Note `target_miss_visible` on `python -m pipeline status` after normalize.
2. Widen `config/run.yaml` (more storefronts, Play `max_pages`, Reddit `keywords`).
3. **`python -m pipeline new-run`** and collect again — never mutate a **frozen** run.

---

## 6. What not to do

- Do not treat raw row count as the 500 bar — only **relevant** after normalize.
- Do not use paid Reddit / SerpApi / Community Console APIs.
- Do not freeze a run until Edge Cases §14 acceptance checks pass (later phases).

---

## Reference

| Command | Purpose |
|---------|---------|
| `python -m pipeline smoke` | Fixtures collect + normalize + status |
| `python -m pipeline collect <id> --fixtures` | Collect fixtures for one run |
| `python -m pipeline status <id>` | Receipts, raw counts, feedback summary |
| `python -m pipeline import-raw` | JSON → `raw_record` |

Specs: [System Architecture.md](../System%20Architecture.md), [Edge Cases.md](../Edge%20Cases.md), [Implementation Plan.md](../Implementation%20Plan.md).
