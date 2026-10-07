"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchJson, type FeedbackItem } from "@/lib/api";
import { SOURCE_LABELS } from "@/lib/chartTheme";

export function EvidenceDrawer({
  itemId,
  evidenceKind,
  onClose,
}: {
  itemId: string | null;
  evidenceKind?: {
    title: string;
    count: number;
    items: { id: string; snippet: string; source: string; source_url: string | null }[];
  };
  onClose: () => void;
}) {
  const [item, setItem] = useState<FeedbackItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(itemId);

  useEffect(() => {
    setSelectedId(itemId);
  }, [itemId]);

  const load = useCallback(async (id: string) => {
    setError(null);
    try {
      const data = await fetchJson<FeedbackItem>(`/items/${id}`);
      setItem(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load item");
      setItem(null);
    }
  }, []);

  useEffect(() => {
    if (selectedId) void load(selectedId);
    else setItem(null);
  }, [selectedId, load]);

  if (!itemId && !evidenceKind) return null;

  return (
    <>
      <button type="button" className="drawer-backdrop" aria-label="Close evidence" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Evidence drawer">
        <div className="drawer-head">
          <strong>Evidence</strong>
          <button type="button" className="ghost" onClick={onClose}>Close</button>
        </div>
        {evidenceKind ? (
          <p className="muted">
            <strong>{evidenceKind.title}</strong> — {evidenceKind.count} stored items (list matches
            the metric).
          </p>
        ) : null}
        {evidenceKind && evidenceKind.items.length > 0 ? (
          <ul className="evidence-list">
            {evidenceKind.items.map((row) => (
              <li key={row.id}>
                <button type="button" className="linkish" onClick={() => setSelectedId(row.id)}>
                  {SOURCE_LABELS[row.source] || row.source} · {row.id.slice(0, 10)}…
                </button>
                <div className="snippet">{row.snippet}</div>
              </li>
            ))}
          </ul>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        {item ? (
          <article className="item-card">
            <p className="muted">
              {SOURCE_LABELS[item.source] || item.source} · {item.authored_at || "no date"}
            </p>
            {item.source_url ? (
              <p>
                <a href={item.source_url} target="_blank" rel="noreferrer">Open source</a>
              </p>
            ) : (
              <p className="muted">No citable URL.</p>
            )}
            <blockquote>{item.text}</blockquote>
            {item.classifications.map((c) => (
              <div key={c.taxonomy_node_id} className="class-block">
                <div>{c.name} · confidence {c.confidence ?? "—"}</div>
                <div className="muted">{c.rationale}</div>
                {(c.expanded_snippets.length ? c.expanded_snippets : c.snippets).map((s) => (
                  <p key={s} className="snippet">“{s}”</p>
                ))}
              </div>
            ))}
            <button
              type="button"
              onClick={() => {
                const quote = (item.classifications[0]?.expanded_snippets[0] || item.text).slice(0, 400);
                void navigator.clipboard.writeText(
                  `${quote}\n\nSource: ${item.source_url || item.id}\nitem_id: ${item.id}`,
                );
              }}
            >
              Copy as evidence
            </button>
          </article>
        ) : null}
      </aside>
    </>
  );
}
