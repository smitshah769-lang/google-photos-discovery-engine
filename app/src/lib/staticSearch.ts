import { readSnapshot } from "@/lib/snapshot";

type Chunk = {
  feedback_item_id?: string;
  text?: string;
  stored_text?: string;
  metadata?: {
    item_id?: string;
    source?: string;
    source_url?: string | null;
    authored_at?: string | null;
    categories?: string[];
    confidence?: number | null;
    impact?: number;
  };
  vector?: number[];
};

type IndexFile = { chunks?: Chunk[] };

type Hit = {
  item_id: string;
  snippet: string;
  source: string | null;
  source_url: string | null;
  authored_at: string | null;
  categories: string[];
  confidence: number | null;
  relevance_score: number;
  impact_score: number;
  rerank_score: number;
  text: string;
};

const OUT_OF_SCOPE =
  /\b(train(?:ing)?\s+(?:the\s+)?model|fine[- ]?tune|write\s+(?:a\s+)?python|python\s+scraper|scrape\s+(?:the\s+)?play\s+store|what\s+is\s+rag\b|how\s+does\s+(?:this|the)\s+(?:discovery|research)\s+engine\s+work|discovery\s+engine\s+work|capital\s+of\s+france|who\s+won\s+the\s+world\s+cup|openai|chatgpt|gemini\s+api)\b/i;
const GOOGLE_PHOTOS = /\b(google\s+photos|gphotos|photos\s+app)\b/i;
const RETRIEVAL =
  /\b(find|search|locate|look(?:ing)?\s+for|can't\s+find|cannot\s+find|couldn't\s+find|old\s+pictures?|old\s+photos?|screenshot|metadata|people|face|album|remember\s+when|incomplete\s+memory|workaround|date|location|place|years?\s+ago|abandon|gave\s+up|scroll)\b/i;
const REVIEWER =
  /\b(pain\s+points?|sentiment|themes?|frustrations?|complaints?|key\s+findings?|what\s+are|how\s+(?:is|are|do)\s+users?|overall|search\s+experience|user\s+feedback|evidence)\b/i;
const SNAPSHOT = /\b(search|photos?|retrieval|feedback|google\s+photos|users?|ask\s+photos|ai\s+search)\b/i;
const BACKUP = /\b(backup|sync|storage|quota|billing|subscription|payment|upload)\b/i;
const FINDING = /\b(find|search|locate|missing\s+photo|can't\s+find|cannot\s+find)\b/i;

const OOS_MESSAGE =
  "This search only covers Google Photos photo search and retrieval in the collected feedback snapshot (finding photos, incomplete memory, metadata, abandonment, workarounds). Your query is outside that scope.";

function inScope(query: string): { ok: boolean; message?: string } {
  const text = query.trim();
  if (!text) return { ok: false, message: "Enter a question about Google Photos photo search or retrieval." };
  if (OUT_OF_SCOPE.test(text)) return { ok: false, message: OOS_MESSAGE };
  const reviewer = REVIEWER.test(text) && SNAPSHOT.test(text);
  if (!RETRIEVAL.test(text) && !GOOGLE_PHOTOS.test(text) && !reviewer) {
    return { ok: false, message: OOS_MESSAGE };
  }
  if (BACKUP.test(text) && !FINDING.test(text)) return { ok: false, message: OOS_MESSAGE };
  return { ok: true };
}

const STOP = new Set([
  "the", "and", "for", "are", "what", "how", "with", "this", "that", "from", "about",
  "around", "users", "user", "google", "photos", "photo", "search", "into", "does", "have",
]);

function lexicalOverlap(query: string, document: string): number {
  const q = new Set(
    (query.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length > 2 && !STOP.has(w)),
  );
  if (q.size === 0) return 0;
  const d = new Set(document.toLowerCase().match(/[a-z0-9]+/g) || []);
  let hit = 0;
  for (const word of q) if (d.has(word)) hit += 1;
  return hit / q.size;
}

function retrieve(query: string, source: string | null): Hit[] {
  const index = readSnapshot<IndexFile>("index.json");
  const scored: Hit[] = [];
  for (const chunk of index.chunks || []) {
    const meta = chunk.metadata || {};
    if (source && meta.source !== source) continue;
    const lexical = lexicalOverlap(query, chunk.text || "");
    if (lexical <= 0) continue;
    const rel = lexical;
    const text = chunk.stored_text || chunk.text || "";
    const snippet = text.length > 280 ? `${text.slice(0, 277).trim()}...` : text.trim();
    const impact = Number(meta.impact || 0);
    const boosted = rel;
    scored.push({
      item_id: String(meta.item_id || chunk.feedback_item_id || ""),
      snippet,
      source: meta.source || null,
      source_url: meta.source_url || null,
      authored_at: meta.authored_at || null,
      categories: meta.categories || [],
      confidence: meta.confidence ?? null,
      relevance_score: Math.round(rel * 10000) / 10000,
      impact_score: Math.round(impact * 10000) / 10000,
      rerank_score: Math.round(boosted * (1 + 0.15 * impact) * 10000) / 10000,
      text,
    });
  }
  scored.sort((a, b) => b.rerank_score - a.rerank_score);
  const seen = new Set<string>();
  const unique: Hit[] = [];
  for (const hit of scored) {
    if (!hit.item_id || seen.has(hit.item_id)) continue;
    seen.add(hit.item_id);
    unique.push(hit);
    if (unique.length >= 8) break;
  }
  return unique;
}

function pct(part: number, whole: number): number {
  if (whole <= 0) return 0;
  return Math.round((100 * part) / whole);
}

function metricAnswer(query: string): { headline: string; summary: string; stats: { label: string; value: string; detail?: string }[]; bullets: string[] } | null {
  const q = query.toLowerCase();
  const insights = readSnapshot<{
    relevant_count?: number;
    research?: {
      overall_sentiment?: { id: string; value: number }[];
      pain_points?: { name: string; frequency: number }[];
      search_ai_search?: { frequency?: number; positive?: number; negative?: number; neutral?: number };
      key_findings?: string;
    };
  }>("insights.json");
  const research = insights.research || {};
  const relevant = insights.relevant_count || 0;
  if (/\bpain\s+points?\b|\bfrustrations?\b|\bcomplaints?\b/.test(q)) {
    const pain = research.pain_points || [];
    if (!pain.length) return null;
    return {
      headline: "Top pain themes (taxonomy)",
      summary: `Lead theme: ${pain[0].name} (${pain[0].frequency.toLocaleString()} items).`,
      stats: pain.slice(0, 4).map((p) => ({
        label: p.name,
        value: p.frequency.toLocaleString(),
        detail: "items tagged",
      })),
      bullets: [
        `Across ${relevant.toLocaleString()} retrieval-related items, “${pain[0].name}” is the most frequent overarching theme.`,
        "Counts reflect taxonomy labels in this freeze, not production telemetry.",
      ],
    };
  }
  if (/\bsentiment\b|\bnegative\b|\bpositive\b|\bfeel\b/.test(q)) {
    const rows = Object.fromEntries((research.overall_sentiment || []).map((r) => [r.id, r.value]));
    const neg = rows.negative || 0;
    const neu = rows.neutral || 0;
    const pos = rows.positive || 0;
    const total = neg + neu + pos || relevant || 1;
    const ai = research.search_ai_search || {};
    const aiTotal = Number(ai.frequency || 0) || Number(ai.positive || 0) + Number(ai.negative || 0) + Number(ai.neutral || 0);
    const bullets = [
      `Labels come from the frozen research pass on ${total.toLocaleString()} retrieval-related items—not live ratings.`,
    ];
    if (aiTotal) {
      bullets.push(
        `Among ${aiTotal.toLocaleString()} items that mention Search / AI Search / Ask Photos, ${pct(Number(ai.negative || 0), aiTotal)}% are negative.`,
      );
    }
    return {
      headline: "Overall search sentiment in this snapshot",
      summary: `Search-related sentiment is ${pct(neg, total)}% negative, ${pct(neu, total)}% neutral, and ${pct(pos, total)}% positive.`,
      stats: [
        { label: "Negative", value: `${pct(neg, total)}%`, detail: `${neg.toLocaleString()} items` },
        { label: "Neutral", value: `${pct(neu, total)}%`, detail: `${neu.toLocaleString()} items` },
        { label: "Positive", value: `${pct(pos, total)}%`, detail: `${pos.toLocaleString()} items` },
      ],
      bullets,
    };
  }
  if (/\bkey\s+findings?\b|\boverall\b|\bthemes?\b/.test(q) && research.key_findings) {
    return {
      headline: "Key findings",
      summary: String(research.key_findings),
      stats: [],
      bullets: [],
    };
  }
  return null;
}

async function summarize(query: string, hits: Hit[]): Promise<{ summary: string; quotes: { item_id: string; quote: string }[] } | null> {
  const evidence = hits
    .slice(0, 6)
    .map((h) => `- item_id=${h.item_id}: ${h.text.slice(0, 700)}`)
    .join("\n");
  const prompt = [
    "You summarize user feedback about Google Photos photo search and retrieval.",
    "Use ONLY the evidence below. Do not invent quotes.",
    "Write 2–4 sentences of plain text. No JSON, no title, no bullet list.",
    `Question: ${query}`,
    "",
    "Evidence:",
    evidence,
  ].join("\n");

  const groq = process.env.GROQ_API_KEY;
  const gemini = process.env.GEMINI_API_KEY;
  let raw = "";
  if (groq) {
    for (const model of ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]) {
      const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${groq}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model,
          temperature: 0.2,
          max_tokens: 500,
          messages: [{ role: "user", content: prompt }],
        }),
      });
      if (!res.ok) {
        const errText = await res.text();
        console.error("Groq summary failed", model, res.status, errText.slice(0, 240));
        continue;
      }
      const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
      raw = data.choices?.[0]?.message?.content || "";
      break;
    }
    if (!raw) return null;
    return { summary: raw.trim(), quotes: [] };
  } else if (gemini) {
    const res = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${gemini}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.2, maxOutputTokens: 500 },
        }),
      },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { candidates?: { content?: { parts?: { text?: string }[] } }[] };
    raw = data.candidates?.[0]?.content?.parts?.[0]?.text || "";
    if (!raw.trim()) return null;
    return { summary: raw.trim(), quotes: [] };
  }
  return null;
}

export async function runStaticSearch(body: { query?: string; sources?: string[] }): Promise<Record<string, unknown>> {
  const chrome = readSnapshot<Record<string, unknown>>("chrome.json");
  const query = String(body.query || "");
  const scope = inScope(query);
  if (!scope.ok) {
    return { ...chrome, in_scope: false, message: scope.message, hits: [] };
  }
  const source = body.sources?.[0] || null;
  const hits = retrieve(query, source);
  if (!hits.length) {
    return {
      ...chrome,
      in_scope: true,
      message: "No matching feedback in this snapshot for that query. Try different wording or relax filters.",
      hits: [],
    };
  }

  const metrics = metricAnswer(query);
  let summary = metrics?.summary || "";
  let quotes: { item_id: string; quote: string }[] = [];
  const synthesized = await summarize(query, hits).catch(() => null);
  if (synthesized?.summary && !metrics) {
    summary = synthesized.summary;
    quotes = synthesized.quotes;
  } else if (synthesized?.quotes.length) {
    quotes = synthesized.quotes;
  }
  if (!summary) {
    const themes = [...new Set(hits.flatMap((h) => h.categories))].slice(0, 3);
    const themeBit = themes.length ? ` Themes that show up in the top matches include ${themes.join(", ")}.` : "";
    summary = `Based on the closest-matching feedback in this snapshot, users often describe issues related to “${query.trim()}”.${themeBit} The quotes below are supporting examples from retrieved items.`;
  }
  const evidence = (quotes.length ? quotes : hits.slice(0, 2).map((h) => ({ item_id: h.item_id, quote: h.snippet }))).map(
    (q) => {
      const hit = hits.find((h) => h.item_id === q.item_id);
      return {
        item_id: q.item_id,
        snippet: q.quote,
        source: hit?.source || null,
        source_url: hit?.source_url || null,
        context: "From the closest matching feedback in this snapshot.",
      };
    },
  );

  return {
    ...chrome,
    in_scope: true,
    message: null,
    hits: [],
    answer: {
      format: metrics?.stats.length
        ? /\bpain\b/i.test(metrics.headline)
          ? "pain_points"
          : "sentiment"
        : "narrative",
      headline: metrics?.headline || "Summary",
      summary,
      stats: metrics?.stats || [],
      bullets: metrics?.bullets || [],
      evidence: evidence.slice(0, 2),
    },
    embedding_model: { provider: "lexical", model_id: "keyword-overlap" },
  };
}
