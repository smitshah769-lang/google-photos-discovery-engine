"use client";

import { useEffect, useState } from "react";
import { ArchitectureDiagram } from "@/components/ArchitectureDiagram";
import { PageHeader } from "@/components/PageHeader";
import { SourceExtractionSummary } from "@/components/SourceExtractionSummary";
import { resolveDataExtraction } from "@/lib/buildExtractionStats";
import { fetchJson, type Insights, type Methodology, type Quality } from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/chartTheme";

export default function HowItWorksPage() {
  const [method, setMethod] = useState<Methodology | null>(null);
  const [quality, setQuality] = useState<Quality | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetchJson<Methodology>("/methodology"),
      fetchJson<Quality>("/quality"),
      fetchJson<Insights>("/insights"),
    ])
      .then(([m, q, i]) => {
        setMethod(m);
        setQuality(q);
        setInsights(i);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return (
      <main className="page">
        <div className="card card-error">{error}</div>
      </main>
    );
  }
  if (!method || !quality || !insights) {
    return <main className="page"><div className="skeleton skeleton-card tall" /></main>;
  }

  const { stats: extractionStats, partial: extractionPartial } = resolveDataExtraction(
    method,
    insights,
  );

  const limitationLines = [...method.required_limitations];
  for (const line of method.limitations || []) {
    if (!limitationLines.includes(line)) {
      limitationLines.push(line);
    }
  }

  return (
    <main className="page">
      <PageHeader
        title="How the Engine Works"
        description="Methodology, limitations, and quality metrics for this one-time snapshot."
      />

      <div className="alert">{method.ranking_copy}</div>

      <article className="card arch-card">
        <h2 className="card-title">System architecture</h2>
        <p className="card-sub">
          From System Architecture.md §3 — one-time batch pipeline, four public sources, read-only
          research UI after freeze.
        </p>
        <ArchitectureDiagram />
      </article>

      <article className="card">
        <h2 className="card-title">Data extracted by source</h2>
        <p className="card-sub">
          Total data points collected from each public adapter in this snapshot, plus how many
          normalized items are retrieval-related for analysis.
        </p>
        <SourceExtractionSummary stats={extractionStats} partial={extractionPartial} />
      </article>

      <div className="method-grid">
        <article className="card">
          <h2 className="card-title">Four public sources</h2>
          <ul className="method-list">
            {Object.entries(method.collection_methods).map(([src, how]) => (
              <li key={src}>
                <strong>{SOURCE_LABELS[src] || src}</strong>
                <span className="muted">{how}</span>
              </li>
            ))}
          </ul>
          <p className="scope-line">
            Window: {String(method.date_window.after || "—")} →{" "}
            {String(method.date_window.before || "collection time")}
          </p>
        </article>

        <article className="card span-2">
          <h2 className="card-title">Limitations</h2>
          <ul>
            {limitationLines.map((line) => (
              <li key={line} style={{ marginBottom: "0.5rem" }}>{line}</li>
            ))}
          </ul>
          <p style={{ marginTop: "1rem" }}>{method.human_review}</p>
          <p className="muted">{method.bias_notes}</p>
        </article>

        <article className="card">
          <h2 className="card-title">Quality snapshot</h2>
          <p>
            Classified <strong>{quality.classified_count ?? "—"}</strong> · unclassified{" "}
            <strong>{quality.unclassified_count ?? "—"}</strong>
          </p>
          <ul>
            {quality.hypothesis_overlay.values_supported.map((k) => (
              <li key={k}>
                {k}: <strong>{quality.hypothesis_overlay.counts[k]}</strong>
              </li>
            ))}
          </ul>
          {quality.index.exists ? null : (
            <p className="alert alert-warn" style={{ marginTop: "0.75rem" }}>
              {quality.index.rebuild_instruction}
            </p>
          )}
        </article>
      </div>
    </main>
  );
}
