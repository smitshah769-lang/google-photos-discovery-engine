import { readSnapshot } from "@/lib/snapshot";

type CorpusItem = {
  id: string;
  source: string;
  source_url: string | null;
  authored_at: string | null;
  snippet: string;
  segments: Record<string, unknown>;
  taxonomy_node_ids: string[];
};

const SEGMENT_KEYS = new Set(["library_size", "photo_age", "geo", "device"]);

function nodeIdsForQuery(nodeId: string): string[] {
  if (nodeId === "knowledge_unknown_capability" || nodeId === "knowledge_hidden_features") {
    return ["knowledge_unknown_capability", "knowledge_hidden_features"];
  }
  return [nodeId];
}

function seg(item: CorpusItem): Record<string, unknown> {
  return item.segments || {};
}

export function queryEvidence(params: URLSearchParams): { kind: string; count: number; items: unknown[]; error?: string } {
  const kind = params.get("kind") || "";
  const corpus = readSnapshot<CorpusItem[]>("corpus.json");
  let matched: CorpusItem[] = [];

  if (kind === "relevant") {
    matched = corpus;
  } else if (kind === "source") {
    const source = params.get("source") || "";
    matched = corpus.filter((item) => item.source === source);
  } else if (kind === "sentiment") {
    const wanted = (params.get("sentiment") || "").toLowerCase();
    matched = corpus.filter((item) => String(seg(item).sentiment || "neutral").toLowerCase() === wanted);
  } else if (kind === "signal") {
    const wanted = (params.get("signal") || "").toLowerCase();
    matched = corpus.filter((item) => String(seg(item).signal || "no_signal").toLowerCase() === wanted);
  } else if (kind === "search_type") {
    const wanted = params.get("search_type") || "";
    const sent = (params.get("sentiment") || "").toLowerCase();
    matched = corpus.filter((item) => {
      const types = seg(item).search_types;
      if (!wanted || !Array.isArray(types) || !types.includes(wanted)) return false;
      if (!sent) return true;
      return String(seg(item).sentiment || "neutral").toLowerCase() === sent;
    });
  } else if (kind === "suggestion") {
    matched = corpus.filter((item) => Boolean(seg(item).is_suggestion));
  } else if (kind === "category_frequency") {
    const node = params.get("taxonomy_node_id") || "";
    if (!node) return { kind, count: 0, items: [], error: "taxonomy_node_id required" };
    const wanted = new Set(nodeIdsForQuery(node));
    matched = corpus.filter((item) => item.taxonomy_node_ids.some((id) => wanted.has(id)));
  } else if (kind === "hypothesis") {
    const key = params.get("overlay") || "";
    matched = corpus.filter((item) => String(seg(item).hypothesis_overlay || "insufficient") === key);
  } else if (kind === "segment") {
    const sk = params.get("segment_key") || "";
    const sv = params.get("segment_value") || "unknown";
    if (!SEGMENT_KEYS.has(sk)) return { kind, count: 0, items: [] };
    matched = corpus.filter((item) => String(seg(item)[sk] || "unknown") === sv);
  } else if (kind === "workaround") {
    matched = corpus.filter((item) => item.taxonomy_node_ids.includes("workarounds_succeeded"));
  } else {
    return { kind, count: 0, items: [], error: "unknown evidence kind" };
  }

  const items = matched.map((item) => ({
    id: item.id,
    source: item.source,
    source_url: item.source_url,
    authored_at: item.authored_at,
    snippet: item.snippet,
  }));
  return { kind, count: items.length, items };
}
