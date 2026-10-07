/** Empty = same-origin (Next.js rewrites / rag-search proxy → Python API). Set full URL only for split UI/API hosts. */
export const API_BASE = process.env.NEXT_PUBLIC_DISCOVERY_API_URL || "";

function extraHeaders(): HeadersInit {
  const basic = process.env.NEXT_PUBLIC_DISCOVERY_BASIC_AUTH;
  if (!basic) return {};
  const encoded =
    typeof Buffer !== "undefined"
      ? Buffer.from(basic).toString("base64")
      : btoa(basic);
  return { Authorization: `Basic ${encoded}` };
}

/** Same-origin proxy for POST /search (avoids clashing with the /search page route). */
export const SEARCH_API_PATH = "/rag-search";

function resolveApiUrl(path: string, init?: RequestInit): string {
  if (path === "/search" && (init?.method || "GET").toUpperCase() === "POST") {
    return SEARCH_API_PATH;
  }
  const base = API_BASE.trim();
  if (base && base !== "same-origin") {
    return `${base.replace(/\/$/, "")}${path}`;
  }
  return path;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = resolveApiUrl(path, init);
  const res = await fetch(url, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...extraHeaders(),
      ...(init?.headers || {}),
    },
  });
  const data = (await res.json()) as T;
  if (!res.ok) {
    throw new Error((data as { error?: string }).error || `Request failed (${res.status})`);
  }
  return data;
}

export type ChromeMeta = {
  run_id: string;
  status: string;
  frozen_at: string | null;
  created_at: string;
  taxonomy_version: string;
  corpus_target_relevant: number;
  ranking_copy: string;
};

export type SourceReceipt = {
  source: string;
  status: string;
  item_count: number;
  notes: string;
  collection_method?: string;
};

export type CategoryRow = {
  taxonomy_node_id: string;
  name: string;
  definition: string;
  frequency: number;
  severity: number | null;
  avg_confidence: number | null;
  source_mix: Record<string, number>;
  consistent_across_sources: boolean;
  segment_unknown_rates: Record<string, number>;
  low_support: boolean;
  low_support_reason: string | null;
  ranked_opportunity: boolean;
  workaround_ids: string[];
};

export type Insights = ChromeMeta & {
  relevant_count: number;
  meets_target: boolean;
  target_miss_visible: boolean;
  incomplete_source_mix: boolean;
  source_receipts: SourceReceipt[];
  source_breakdown: Record<string, number>;
  analysis_scope: {
    date_range_authored_at: { start: string | null; end: string | null };
    sources: string[];
    run_id: string;
    taxonomy_version: string;
  };
  hypothesis_overlay: {
    counts: Record<string, number>;
    overall: string;
    values_supported: string[];
  };
  segments: Record<string, Record<string, number>>;
  trend: {
    buckets: { period: string; count: number }[];
    subtitle: string;
    window_start: string | null;
    window_end: string | null;
  };
  categories: CategoryRow[];
  high_impact: CategoryRow[];
  workarounds: { count: number; item_ids: string[] };
  index: { exists: boolean; rebuild_instruction: string | null };
  filters_empty_message: string;
  research?: ResearchDashboard;
};

export type ResearchDashboard = {
  key_findings: string;
  pain_points: { taxonomy_node_id: string; name: string; frequency: number }[];
  sub_themes: {
    taxonomy_node_id: string;
    name: string;
    parent_id: string;
    parent_name: string;
    frequency: number;
  }[];
  overall_sentiment: { id: string; label: string; value: number }[];
  signal_mix: { id: string; label: string; value: number }[];
  search_types: { id: string; name: string; frequency: number }[];
  search_type_sentiment: {
    id: string;
    name: string;
    positive: number;
    negative: number;
    neutral: number;
    total: number;
  }[];
  search_ai_search: {
    id: string;
    name: string;
    frequency: number;
    positive: number;
    negative: number;
    neutral: number;
  };
  top_suggestions: {
    id: string;
    source: string;
    source_url: string | null;
    authored_at: string | null;
    snippet: string;
    rank: number;
  }[];
  suggestion_summary: string;
  year_coverage: { year: string; count: number }[];
  featured_snippets: {
    id: string;
    source: string;
    source_url: string | null;
    authored_at: string | null;
    snippet: string;
    severity: number | null;
  }[];
  kpi: {
    sub_theme_count: number;
    suggestion_items: number;
    overarching_theme_count: number;
    actionable_count: number;
    search_typed_count: number;
  };
};

export type EvidenceItem = {
  id: string;
  source: string;
  source_url: string | null;
  authored_at: string | null;
  snippet: string;
};

export type FeedbackItem = {
  id: string;
  source: string;
  source_url: string | null;
  authored_at: string | null;
  captured_at: string;
  text: string;
  thread_context: string | null;
  relevance_label: string;
  segments: Record<string, string>;
  classifications: {
    taxonomy_node_id: string;
    name: string;
    confidence: number | null;
    rationale: string | null;
    snippets: string[];
    expanded_snippets: string[];
  }[];
  citable: boolean;
};

export type SearchHit = {
  item_id: string;
  snippet: string;
  source: string;
  source_url: string | null;
  authored_at: string | null;
  categories: string[];
  confidence: number | null;
  relevance_score: number;
  impact_score: number;
  rerank_score: number;
};

export type SearchEvidence = {
  item_id: string;
  snippet: string;
  source: string | null;
  source_url: string | null;
  context?: string;
};

export type SearchStat = {
  label: string;
  value: string;
  detail?: string;
};

export type SearchAnswer = {
  summary: string;
  evidence: SearchEvidence[];
  format?: "sentiment" | "pain_points" | "narrative";
  headline?: string;
  stats?: SearchStat[];
  bullets?: string[];
};

export type SearchResult = ChromeMeta & {
  in_scope: boolean;
  message: string | null;
  hits: SearchHit[];
  answer?: SearchAnswer;
  cited_summary?: { summary?: string; citations?: unknown };
  related_themes?: { label: string; overlap_count: number }[];
  index?: { exists: boolean; rebuild_instruction: string | null };
};

export type SourceExtractionRow = {
  source: string;
  extracted_raw: number;
  receipt_reported: number;
  normalized_total: number;
  retrieval_related: number;
  unrelated: number;
  ambiguous: number;
};

export type DataExtractionStats = {
  by_source: SourceExtractionRow[];
  totals: {
    extracted_raw: number;
    normalized_total: number;
    retrieval_related: number;
    unrelated: number;
    ambiguous: number;
  };
  note: string;
};

export type Methodology = ChromeMeta & {
  collection_methods: Record<string, string>;
  source_receipts: SourceReceipt[];
  /** Present when the read API includes pipeline/serve/read.py extraction_stats (restart serve after upgrades). */
  data_extraction?: DataExtractionStats;
  date_window: Record<string, string | null>;
  run_spec_summary: Record<string, unknown>;
  prompts: Record<string, unknown>;
  model_ids: Record<string, unknown>;
  coverage: Record<string, unknown>;
  taxonomy: { id: string; name: string; definition: string }[];
  multi_label_counting_rule: string | null;
  bias_notes: string;
  required_limitations: string[];
  limitations: string[];
  open_decisions: Record<string, unknown>;
  human_review: string;
  non_claims?: string[];
  out_of_repo_scope?: string[];
  pipeline_required_for_serving?: boolean;
};

export type Quality = ChromeMeta & {
  gold_eval: Record<string, unknown>;
  segment_unknown_rates: Record<string, number | null>;
  hypothesis_overlay: Insights["hypothesis_overlay"];
  classified_count: number | null;
  unclassified_count: number | null;
  clusters: Record<string, unknown> | null;
  bias_notes: string;
  index: { exists: boolean; rebuild_instruction: string | null };
};

export type KnownGap = {
  kind: string;
  source: string;
  status: string;
  detail: string;
};

export type HandoffPack = ChromeMeta & {
  non_claims: string[];
  known_gaps: KnownGap[];
  out_of_repo_scope: string[];
  rebuild_instructions: string[];
  ranking_copy: string;
  required_limitations: string[];
  source_receipts: SourceReceipt[];
  pipeline_required_for_serving: boolean;
  serving_note: string;
};
