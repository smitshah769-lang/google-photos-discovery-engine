from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.analysis.embeddings import embed_texts
from pipeline.analysis.inference import InferenceUnavailable
from pipeline.analysis.score import item_impact_features
from pipeline.db.repository import load_run_spec
from pipeline.paths import resolve_data_dir
from pipeline.rag.quotes import expand_to_sentence_boundary
from pipeline.rag.scope import (
    FILTER_EMPTY_MESSAGE,
    NO_MATCH_MESSAGE,
    classify_query_scope,
)
from pipeline.rag.rerank import cross_encoder_rerank, lexical_overlap_boost
from pipeline.rag.store import VectorIndex, index_path_for_run
from pipeline.analysis.cloud_llm import resolve_synthesis_settings
from pipeline.rag.answer import compose_search_answer, query_wants_snapshot_metrics
from pipeline.rag.synthesis import synthesize_cited_summary


@dataclass
class SearchRequest:
    query: str
    sources: list[str] | None = None
    category: str | None = None
    date_after: str | None = None
    date_before: str | None = None
    min_confidence: float | None = None
    include_synthesis: bool | None = None


@dataclass
class SearchResponse:
    in_scope: bool
    message: str | None = None
    hits: list[dict[str, Any]] = field(default_factory=list)
    cited_summary: dict[str, Any] | None = None
    answer: dict[str, Any] | None = None
    related_themes: list[dict[str, Any]] = field(default_factory=list)
    embedding_model: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "in_scope": self.in_scope,
            "message": self.message,
            "hits": self.hits,
        }
        if self.answer is not None:
            out["answer"] = self.answer
            out["hits"] = []
        if self.cited_summary is not None:
            out["cited_summary"] = self.cited_summary
        if self.related_themes:
            out["related_themes"] = self.related_themes
        if self.embedding_model:
            out["embedding_model"] = self.embedding_model
        return out


def _pick_snippet(chunk: dict[str, Any], stored_text: str) -> str:
    meta = chunk.get("metadata") or {}
    for cand in meta.get("snippet_candidates") or []:
        if cand and cand in stored_text:
            return expand_to_sentence_boundary(stored_text, cand)
    text = stored_text or chunk.get("text") or ""
    trimmed = text[:280].strip()
    if len(text) > 280:
        trimmed = expand_to_sentence_boundary(text, trimmed[:80])
    return trimmed


def _apply_filters(
    chunk: dict[str, Any],
    req: SearchRequest,
) -> bool:
    meta = chunk.get("metadata") or {}
    if req.sources and meta.get("source") not in req.sources:
        return False
    if req.category and req.category not in (meta.get("categories") or []):
        return False
    if req.min_confidence is not None:
        if float(meta.get("confidence") or 0.0) < req.min_confidence:
            return False
    authored = meta.get("authored_at")
    if authored and req.date_after and authored < req.date_after:
        return False
    if authored and req.date_before and authored > req.date_before:
        return False
    return True


def _related_themes(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    hit_item_ids: set[str],
) -> list[dict[str, Any]]:
    if not hit_item_ids:
        return []
    rows = conn.execute(
        "SELECT label, member_ids_json, cohesion_score FROM cluster WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchall()
    themes: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["member_ids_json"] or "{}")
            ids = set(payload.get("ids") or [])
        except json.JSONDecodeError:
            ids = set()
        overlap = hit_item_ids & ids
        if not overlap:
            continue
        if payload.get("needs_human_review"):
            continue
        themes.append(
            {
                "label": row["label"],
                "cohesion_score": row["cohesion_score"],
                "overlap_count": len(overlap),
            }
        )
    themes.sort(key=lambda t: (t["overlap_count"], t.get("cohesion_score") or 0.0), reverse=True)
    return themes[:5]


def _relevant_count(conn: sqlite3.Connection, analysis_run_id: str) -> int:
    row = conn.execute(
        "SELECT coverage_stats_json FROM methodology_snapshot WHERE analysis_run_id = ?",
        (analysis_run_id,),
    ).fetchone()
    if row and row["coverage_stats_json"]:
        try:
            coverage = json.loads(row["coverage_stats_json"])
            if coverage.get("relevant_count") is not None:
                return int(coverage["relevant_count"])
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    row2 = conn.execute(
        """
        SELECT COUNT(*) AS n FROM feedback_item
        WHERE analysis_run_id = ? AND relevance_label = 'retrieval_related'
        """,
        (analysis_run_id,),
    ).fetchone()
    return int(row2["n"] if row2 else 0)


def load_index_for_run(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    run_spec: dict[str, Any] | None = None,
) -> tuple[VectorIndex, Path]:
    spec = run_spec or load_run_spec(conn, analysis_run_id)
    path = index_path_for_run(resolve_data_dir(spec), analysis_run_id)
    index = VectorIndex.load(path)
    if index.analysis_run_id != analysis_run_id:
        raise ValueError("Vector index run id does not match analysis_run_id.")
    return index, path


def search(
    conn: sqlite3.Connection,
    analysis_run_id: str,
    req: SearchRequest,
    *,
    run_spec: dict[str, Any] | None = None,
) -> SearchResponse:
    spec = run_spec or load_run_spec(conn, analysis_run_id)
    rag_cfg = spec.get("rag") or {}
    models = spec.get("models") or {}
    embed_cfg = models.get("embedding") or {}

    in_scope, oos_message = classify_query_scope(req.query)
    if not in_scope:
        return SearchResponse(in_scope=False, message=oos_message, hits=[])

    try:
        index, _path = load_index_for_run(conn, analysis_run_id, spec)
    except FileNotFoundError:
        return SearchResponse(
            in_scope=True,
            message=(
                "Vector index is missing. Rebuild with: "
                f"python -m pipeline index {analysis_run_id}"
            ),
            hits=[],
        )

    embed_provider = str(index.embedding_provider or embed_cfg.get("provider") or "hashing")
    embed_model = str(index.embedding_model_id or embed_cfg.get("model_id") or "")

    top_k = int(rag_cfg.get("top_k") or 20)
    min_relevance = float(rag_cfg.get("min_relevance") or 0.12)
    fetch_k = int(rag_cfg.get("fetch_k") or max(top_k * 3, 30))
    lexical_weight = float(rag_cfg.get("hybrid_lexical_weight") or 0.0)
    rerank_cfg = rag_cfg.get("rerank") or {}
    rerank_enabled = bool(rerank_cfg.get("enabled"))
    rerank_model = str(rerank_cfg.get("model_id") or "BAAI/bge-reranker-base")
    rerank_pool = int(rerank_cfg.get("candidates") or min(fetch_k, 40))

    try:
        query_vec = embed_texts([req.query], provider=embed_provider, model_id=embed_model)[0]
    except InferenceUnavailable as exc:
        return SearchResponse(
            in_scope=True,
            message=str(exc),
            hits=[],
            embedding_model={"provider": embed_provider, "model_id": embed_model},
        )

    candidates = index.search(query_vec, top_k=fetch_k, min_relevance=min_relevance)

    filtered: list[tuple[dict[str, Any], float]] = []
    for chunk, rel in candidates:
        if _apply_filters(chunk, req):
            filtered.append((chunk, rel))

    if candidates and not filtered:
        return SearchResponse(
            in_scope=True,
            message=FILTER_EMPTY_MESSAGE,
            hits=[],
            embedding_model={"provider": embed_provider, "model_id": embed_model},
        )

    if lexical_weight > 0:
        boosted: list[tuple[dict[str, Any], float]] = []
        for chunk, rel in filtered:
            doc = chunk.get("text") or ""
            rel_adj = rel + lexical_weight * lexical_overlap_boost(req.query, doc)
            boosted.append((chunk, rel_adj))
        boosted.sort(key=lambda x: x[1], reverse=True)
        filtered = boosted

    ranked = filtered[:rerank_pool]
    if rerank_enabled and ranked:
        try:
            ranked = cross_encoder_rerank(
                req.query,
                ranked,
                model_id=rerank_model,
                top_k=top_k,
            )
        except InferenceUnavailable:
            ranked = filtered[:top_k]
    else:
        ranked = filtered[:top_k]

    hits_out: list[dict[str, Any]] = []
    for chunk, rel in ranked:
        meta = chunk.get("metadata") or {}
        item_id = meta.get("item_id") or chunk.get("feedback_item_id")
        stored = chunk.get("stored_text") or ""
        impact_meta = float(meta.get("impact") or 0.0)
        impact_item = item_impact_features(stored)
        impact = max(impact_meta, impact_item["frustration"] + impact_item["emotional_value"])
        rerank = rel * (1.0 + 0.15 * impact)
        snippet = _pick_snippet(chunk, stored)
        if snippet and stored and snippet not in stored and len(snippet) > 20:
            snippet = expand_to_sentence_boundary(stored, snippet[:40])
        hits_out.append(
            {
                "item_id": item_id,
                "snippet": snippet,
                "source": meta.get("source"),
                "source_url": meta.get("source_url"),
                "authored_at": meta.get("authored_at"),
                "categories": meta.get("categories") or [],
                "confidence": meta.get("confidence"),
                "relevance_score": round(rel, 4),
                "impact_score": round(impact, 4),
                "rerank_score": round(rerank, 4),
            }
        )

    hits_out.sort(key=lambda h: h["rerank_score"], reverse=True)

    if not hits_out:
        embed_meta = {"provider": embed_provider, "model_id": embed_model}
        if query_wants_snapshot_metrics(req.query):
            answer = compose_search_answer(
                req.query,
                [],
                conn=conn,
                analysis_run_id=analysis_run_id,
                relevant_count=_relevant_count(conn, analysis_run_id),
            )
            if answer.get("summary"):
                return SearchResponse(
                    in_scope=True,
                    hits=[],
                    answer=answer,
                    embedding_model=embed_meta,
                )
        return SearchResponse(
            in_scope=True,
            message=NO_MATCH_MESSAGE,
            hits=[],
            embedding_model=embed_meta,
        )

    synthesis_cfg = rag_cfg.get("synthesis") or {}
    synth_enabled, synth_provider, synth_model = resolve_synthesis_settings(synthesis_cfg, models)
    want_synthesis = req.include_synthesis
    if want_synthesis is None:
        want_synthesis = synth_enabled
    cited_summary = None
    if want_synthesis and synth_model:
        synth_hits = [
            {
                "item_id": h["item_id"],
                "text": next(
                    (c.get("text") for c in index.chunks if (c.get("metadata") or {}).get("item_id") == h["item_id"]),
                    h["snippet"],
                ),
                "stored_text": next(
                    (c.get("stored_text") for c in index.chunks if (c.get("metadata") or {}).get("item_id") == h["item_id"]),
                    "",
                ),
            }
            for h in hits_out[:8]
        ]
        temp = float(synthesis_cfg.get("temperature") or 0.1)
        cited_summary = synthesize_cited_summary(
            req.query,
            synth_hits,
            provider=synth_provider,
            model_id=synth_model,
            temperature=temp,
        )

    related = _related_themes(conn, analysis_run_id, {h["item_id"] for h in hits_out})

    answer = compose_search_answer(
        req.query,
        hits_out,
        conn=conn,
        analysis_run_id=analysis_run_id,
        relevant_count=_relevant_count(conn, analysis_run_id),
        cited_summary=cited_summary,
    )

    return SearchResponse(
        in_scope=True,
        hits=hits_out,
        answer=answer,
        cited_summary=cited_summary,
        related_themes=related,
        embedding_model={"provider": embed_provider, "model_id": embed_model},
    )
