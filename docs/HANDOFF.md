# Handoff pack — product review (problem statement Phase 1 complete)

This repository delivers a **frozen, read-only** discovery snapshot. Product-team review (problem statement §8 Phase 2) uses the dashboard, RAG, and this pack. It does not re-run collectors.

## Non-claims

- This snapshot is **not a census** of Google Photos users.
- Findings are **not causal** for all Photos users; public complainers and store extremes are biased samples.
- This engine is **not a search product** and does not retrieve photos from anyone’s library.
- Findings evolve **only with future research** — a new collect is a new `run_id`, not a live update of this freeze.

## Known gaps

Gaps are first-class: failed adapters, `gap` receipts (e.g. Arctic Shift outage), CSE quota exhaustion, relevant count below 500, and a missing vector index. They appear on:

- Dashboard incomplete-source-mix banner
- How the Engine Works receipts
- `GET /handoff` and `python -m pipeline handoff <run-id>`
- `data/exports/<run-id>/HANDOFF.md` after freeze

A silent skip of a source is not allowed (Edge Cases §14.1).

## Serving

```bash
./scripts/serve-artifact.sh <run-id>
```

- API: `http://127.0.0.1:8765` (optional basic auth)
- UI: `http://127.0.0.1:3000` — Dashboard, RAG, How the Engine Works, Handoff

Pipeline jobs are not required. Prefer localhost; warn if binding `0.0.0.0` without auth.

## Rebuild

See [REBUILD.md](./REBUILD.md). Same `config/run.yaml` + stored raw rebuilds aggregates.

## Out of this repository

- **Phase 2**: product team reviews findings and prioritizes opportunity areas (not implemented here).
- **Phase 3**: in-product Photos retrieval / roadmap features (not implemented here).
- Joining public handles to Google accounts; Community Console; paid APIs; a fifth channel; live post-freeze trends.
