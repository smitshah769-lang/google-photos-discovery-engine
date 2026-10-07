import type { DataExtractionStats, Insights, Methodology } from "@/lib/api";

const SOURCES = ["app_store", "play_store", "reddit", "help_community"] as const;

export function resolveDataExtraction(
  method: Methodology,
  insights: Insights | null,
): { stats: DataExtractionStats; partial: boolean } {
  if (method.data_extraction?.by_source?.length) {
    return { stats: method.data_extraction, partial: false };
  }

  const receipts = method.source_receipts ?? [];
  const relevant = insights?.source_breakdown ?? {};
  const by_source = SOURCES.map((source) => {
    const r = receipts.find((x) => x.source === source);
    const extracted = r?.item_count ?? 0;
    const rel = relevant[source] ?? 0;
    return {
      source,
      extracted_raw: extracted,
      receipt_reported: extracted,
      normalized_total: 0,
      retrieval_related: rel,
      unrelated: 0,
      ambiguous: 0,
    };
  });

  const totals = {
    extracted_raw: by_source.reduce((n, r) => n + r.extracted_raw, 0),
    normalized_total: 0,
    retrieval_related:
      insights?.relevant_count ?? by_source.reduce((n, r) => n + r.retrieval_related, 0),
    unrelated: 0,
    ambiguous: 0,
  };

  return {
    partial: true,
    stats: {
      by_source,
      totals,
      note:
        "Extracted counts come from collection receipts; retrieval-related from dashboard insights. " +
        "Restart python -m pipeline serve <run-id> for full per-source normalize / unrelated / ambiguous breakdown.",
    },
  };
}
