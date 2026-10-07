# Effective free RAG (this project)

Goal: strong retrieval + cited summaries for **3–5 reviewers**, **$0** ongoing cost.

## Recommended stack

| Layer | What to use | Cost | Why |
|--------|-------------|------|-----|
| **Embeddings** | Local `BAAI/bge-small-en-v1.5` (already on disk) or `bge-large` after re-index | Free | Small = what your index uses today; large = ~+quality, ~1GB download |
| **Hybrid retrieval** | Vectors + light keyword overlap (`hybrid_lexical_weight`) | Free | Catches exact terms (“face search”, “Ask Photos”) vectors miss |
| **Rerank** | Local `BAAI/bge-reranker-base` cross-encoder | Free | Biggest quality jump after embeddings |
| **Answer text** | One LLM call per question: **Groq**, **HF**, or **Gemini** | Free tier | Summarizes top evidence; not used for retrieval |

Avoid using a **live embedding API** for the full index (~900 items): you pay in rate limits and latency at index time. Keep embeddings **local**; use APIs only for the **single summary call** per search.

## One-time setup

```bash
cd "AI Discovery Engine - Google Photos"
pip install -e ".[analysis]"
```

Add **one** LLM key in `.env` (pick one):

```bash
GROQ_API_KEY=...          # https://console.groq.com/keys — fast, good for summaries
# HF_TOKEN=...            # https://huggingface.co/settings/tokens — set rag.synthesis.provider: huggingface
# GEMINI_API_KEY=...      # https://aistudio.google.com/apikey
```

Defaults live in `config/run.yaml` under `models.embedding` and `rag`.

## Your machine (checked)

| Asset | Role | Use for RAG embed? |
|--------|------|---------------------|
| **`BAAI/bge-small-en-v1.5`** (HF cache + current index) | Text embeddings | **Yes — active today** |
| **Ollama `qwen2.5:3b`** | Chat / classify | **No** (not an embedder) |
| **Ollama `moondream`** | Vision | **No** |
| **`facebook/bart-large-mnli`** | Zero-shot labels | **No** |

There is **no** `nomic-embed-text` (or similar) in Ollama yet. Chat/vision models do not replace an embedding model.

**Effectiveness:** For this corpus, **bge-small + cross-encoder rerank** (already enabled) beats bge-small alone. **bge-large** is usually better than bge-small but requires re-index + download. Ollama `nomic-embed-text` is optional and typically **not** better than bge-large for English retrieval.

## Rebuild the index (only when changing embed model or chunking)

```bash
python -m pipeline index 4ad39133-1e6c-4146-99a0-7d68dfe72020
```

First rerank pass downloads `bge-reranker-base` if missing. Switching to `bge-large` in `run.yaml` then re-running `index` pulls ~1GB extra.

## Serve

```bash
python -m pipeline serve 4ad39133-1e6c-4146-99a0-7d68dfe72020
# UI: ./scripts/serve-artifact.sh <run-id>
```

## Tuning (still free)

In `config/run.yaml`:

- **`min_relevance`** ↓ (e.g. `0.06`) → more recall, noisier hits  
- **`fetch_k`** ↑ → more candidates for reranker  
- **`rag.rerank.candidates`** ↑ → better rerank, slower queries  
- **`rag.rerank.enabled: false`** → faster, weaker ranking on CPU-only machines  

## What “live API” is for here

- **Yes:** one chat completion per user question (Groq / HF / Gemini).  
- **No (by default):** embedding every chunk via HF/OpenAI — use local BGE instead.

If Groq is shared with another app, use a **second API key** for this handoff or prefer **HF_TOKEN** with `provider: huggingface` in `run.yaml`.

## Sharing with reviewers

See [HANDOFF.md](./HANDOFF.md). The host machine needs `.env` keys and the analysis extras; reviewers only need the HTTPS URL (basic auth recommended).
