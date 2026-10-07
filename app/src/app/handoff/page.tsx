"use client";

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { fetchJson, type HandoffPack } from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/chartTheme";

export default function HandoffPage() {
  const [pack, setPack] = useState<HandoffPack | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJson<HandoffPack>("/handoff")
      .then(setPack)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return (
      <main className="page">
        <div className="card card-error">{error}</div>
      </main>
    );
  }
  if (!pack) {
    return (
      <main className="page">
        <div className="skeleton skeleton-card tall" />
      </main>
    );
  }

  return (
    <main className="page">
      <PageHeader
        title="Handoff for product review"
        description="Read-only snapshot pack. Dashboard and RAG do not need pipeline jobs running."
      />

      <div className="alert">{pack.serving_note}</div>
      <div className="alert">{pack.ranking_copy}</div>

      <article className="card">
        <h2 className="card-title">Non-claims</h2>
        <ul>
          {pack.non_claims.map((line) => (
            <li key={line} style={{ marginBottom: "0.5rem" }}>
              {line}
            </li>
          ))}
        </ul>
      </article>

      <article className="card">
        <h2 className="card-title">Known gaps from receipts</h2>
        {pack.known_gaps.length === 0 ? (
          <p className="muted">No adapter gaps recorded. This is still not a census of all Photos users.</p>
        ) : (
          <ul className="receipt-list">
            {pack.known_gaps.map((gap) => (
              <li key={`${gap.kind}-${gap.source}-${gap.detail}`} className="receipt receipt-gap">
                <span className="receipt-source">{SOURCE_LABELS[gap.source] || gap.source}</span>
                <span className="receipt-status">{gap.kind}</span>
                <span className="receipt-notes">{gap.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </article>

      <article className="card">
        <h2 className="card-title">Rebuild from stored raw + run spec</h2>
        <ul>
          {pack.rebuild_instructions.map((line) => (
            <li key={line} style={{ marginBottom: "0.5rem" }}>
              {line}
            </li>
          ))}
        </ul>
      </article>

      <article className="card">
        <h2 className="card-title">Out of this repository</h2>
        <ul>
          {pack.out_of_repo_scope.map((line) => (
            <li key={line} style={{ marginBottom: "0.5rem" }}>
              {line}
            </li>
          ))}
        </ul>
      </article>
    </main>
  );
}
