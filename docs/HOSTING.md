# Hosting (reviewers + GitHub)

## Can I use Vercel?

**Partially.**

| Component | Vercel? | Notes |
|-----------|---------|--------|
| **Next.js UI** (`app/`) | Yes | Set `DISCOVERY_API_URL` to your backend URL; optional `NEXT_PUBLIC_DISCOVERY_BASIC_AUTH` |
| **Python read API** | No | Needs long-lived process + local files (`snapshot.db`, `data/rag/*.json`, embedding models) |
| **Frozen data** | No on serverless alone | DB + vector index are hundreds of MB; not suited to pure serverless functions |

**Recommended patterns**

1. **Local / review session:** `./scripts/serve-artifact.sh <run-id>` (API `8765` + UI `3000`).
2. **Share with 3–5 reviewers:** Small VM or PaaS with **both** processes + basic auth — see `scripts/serve-for-reviewers.sh`.
3. **Vercel + backend:** Deploy UI to Vercel; host API on Railway / Fly.io / Render / a VM with repo + export bundle mounted; point env vars at that URL.

Embeddings and reranking run **on the API host** (CPU, `pip install -e '.[analysis]'`). Optional LLM keys (`GROQ_API_KEY`, `GEMINI_API_KEY`, `HF_TOKEN`) live only on the server.

## GitHub

Code pushes without `data/` (gitignored). Share snapshots via export bundle or separate artifact storage; reviewers need the DB + RAG index on the host running `python -m pipeline serve`.

## Step-by-step free VM

See **[DEPLOY_ORACLE.md](./DEPLOY_ORACLE.md)** and scripts `pack-review-bundle.sh`, `upload-review-bundle.sh`, `vm-bootstrap.sh`.
