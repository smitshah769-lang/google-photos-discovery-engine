"use client";

import { FormEvent, useState } from "react";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { PageHeader } from "@/components/PageHeader";
import {
  fetchJson,
  type SearchAnswer,
  type SearchEvidence,
  type SearchResult,
} from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/chartTheme";

const EXAMPLE_PROMPTS: { label: string; query: string }[] = [
  {
    label: "Pain points",
    query: "What are the main user pain points around Google Photos search?",
  },
  {
    label: "Search sentiment",
    query: "What is sentiment like for search in this feedback?",
  },
  {
    label: "AI / Ask Photos",
    query: "What do users say about AI search and Ask Photos?",
  },
  {
    label: "Old photos",
    query: "Why do users struggle to find old family photos?",
  },
  {
    label: "Face search",
    query: "What issues do people report with face search?",
  },
];

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [itemId, setItemId] = useState<string | null>(null);

  async function runSearch(q: string) {
    setQuery(q);
    setError(null);
    setLoading(true);
    try {
      const body: Record<string, unknown> = { query: q };
      if (source) body.sources = [source];
      const data = await fetchJson<SearchResult>("/search", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(data);
      setItemId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await runSearch(query);
  }

  return (
    <main className={`page search-page ${itemId ? "page-with-drawer" : ""}`}>
      <PageHeader
        title="Ask the snapshot"
        description="Summaries use this frozen corpus. Up to two quotes illustrate the answer—they are chosen to match the question, not a full search dump."
      />

      <div className="gp-search-shell">
        <form onSubmit={onSubmit} className="gp-search-bar">
          <span className="gp-search-icon" aria-hidden>
            ⌕
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about search pain points, sentiment, themes…"
            aria-label="Search query"
          />
          <button type="submit" disabled={loading} className="gp-search-submit">
            {loading ? "…" : "Ask"}
          </button>
        </form>

        <div className="gp-search-filters">
          <label>
            Source
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All sources</option>
              {Object.entries(SOURCE_LABELS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <p className="muted search-prompt-label">Try a starter question</p>
        <div className="chip-row gp-chip-row">
          {EXAMPLE_PROMPTS.map(({ label, query: q }) => (
            <button
              key={q}
              type="button"
              className="chip search-starter-chip"
              onClick={() => void runSearch(q)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error ? <div className="alert alert-warn">{error}</div> : null}
      {result?.index && !result.index.exists ? (
        <div className="alert alert-warn">{result.index.rebuild_instruction}</div>
      ) : null}
      {result ? <SearchBody result={result} onOpen={setItemId} /> : null}
      <EvidenceDrawer itemId={itemId} onClose={() => setItemId(null)} />
    </main>
  );
}

function SearchBody({
  result,
  onOpen,
}: {
  result: SearchResult;
  onOpen: (id: string) => void;
}) {
  if (!result.in_scope) {
    return <div className="alert alert-warn">{result.message}</div>;
  }
  if (result.message && !result.answer?.summary) {
    return <div className="alert">{result.message}</div>;
  }

  let answer: SearchAnswer | undefined = result.answer;
  if (!answer?.summary && result.hits.length > 0) {
    answer = {
      summary:
        "Retrieved matching feedback below. Restart the Python API (port 8765) if you expected a narrative summary.",
      evidence: result.hits.slice(0, 2).map((h) => ({
        item_id: h.item_id,
        snippet: h.snippet,
        source: h.source,
        source_url: h.source_url,
      })),
    };
  }
  if (!answer?.summary) {
    return (
      <div className="alert">
        {result.message ||
          "No answer could be generated. Restart the Python API on port 8765 and try again."}
      </div>
    );
  }

  return (
    <div className="search-results">
      <section className="search-answer-card">
        <h2 className="search-answer-title">{answer.headline || "Summary"}</h2>
        {answer.stats && answer.stats.length > 0 ? (
          <div className="search-stat-grid">
            {answer.stats.map((stat) => (
              <div key={stat.label} className="search-stat-tile">
                <span className="search-stat-value">{stat.value}</span>
                <span className="search-stat-label">{stat.label}</span>
                {stat.detail ? <span className="search-stat-detail">{stat.detail}</span> : null}
              </div>
            ))}
          </div>
        ) : (
          <p className="search-answer-lead">{answer.summary}</p>
        )}
        {answer.bullets && answer.bullets.length > 0 ? (
          <ul className="search-answer-bullets">
            {answer.bullets.map((b) => (
              <li key={b.slice(0, 48)}>{b}</li>
            ))}
          </ul>
        ) : null}
        {answer.stats && answer.stats.length > 0 ? (
          <p className="search-answer-footnote muted">{answer.summary}</p>
        ) : null}
      </section>

      {answer.evidence.length > 0 ? (
        <section className="search-evidence-block">
          <h2 className="search-answer-title">Illustrative quotes</h2>
          <p className="muted search-evidence-note">
            These examples support the summary above—not a ranked list of all matches.
          </p>
          <div className="search-evidence-list">
            {answer.evidence.map((ev: SearchEvidence, idx) => (
              <article key={ev.item_id + String(idx)} className="search-evidence-card">
                <div className="hit-meta">
                  <span className="hit-pill">{SOURCE_LABELS[ev.source || ""] || ev.source}</span>
                  <span className="search-evidence-index">Quote {idx + 1}</span>
                </div>
                {ev.context ? <p className="search-evidence-why">{ev.context}</p> : null}
                <blockquote className="search-evidence-quote">{ev.snippet}</blockquote>
                <div className="hit-actions">
                  <button type="button" onClick={() => onOpen(ev.item_id)}>
                    View full item
                  </button>
                  {ev.source_url ? (
                    <a href={ev.source_url} target="_blank" rel="noreferrer">
                      Open source
                    </a>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
