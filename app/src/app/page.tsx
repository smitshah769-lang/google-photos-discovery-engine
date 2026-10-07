"use client";

import { useCallback, useEffect, useState } from "react";
import {
  FrequencyBarChart,
  NamedPieChart,
  SearchAiSearchWidget,
  SearchTypeSentimentChart,
  SegmentBars,
  YearCoverageChart,
} from "@/components/DashboardCharts";
import { DashboardSkeleton } from "@/components/DashboardSkeleton";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { PageHeader } from "@/components/PageHeader";
import { fetchJson, type EvidenceItem, type Insights } from "@/lib/api";
import { SENTIMENT_COLORS, SIGNAL_COLORS, SOURCE_LABELS } from "@/lib/chartTheme";

export default function DashboardPage() {
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawerItem, setDrawerItem] = useState<string | null>(null);
  const [bundle, setBundle] = useState<{
    title: string;
    count: number;
    items: EvidenceItem[];
  } | null>(null);

  useEffect(() => {
    fetchJson<Insights>("/insights")
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

  const openEvidence = useCallback(async (title: string, params: string) => {
    const ev = await fetchJson<{ count: number; items: EvidenceItem[] }>(`/evidence?${params}`);
    setBundle({ title, count: ev.count, items: ev.items });
    setDrawerItem(ev.items[0]?.id || null);
  }, []);

  if (error) {
    return (
      <main className="page">
        <div className="card card-error">Could not load dashboard: {error}</div>
      </main>
    );
  }
  if (!data) return <DashboardSkeleton />;

  if (!data.research) {
    return (
      <main className="page">
        <PageHeader title="Discovery dashboard" />
        <div className="alert alert-warn">
          Dashboard research metrics are missing. Restart the Python serve process and re-run{" "}
          <code>python -m pipeline aggregate {data.run_id}</code>.
        </div>
      </main>
    );
  }

  const research = data.research;
  const kpi = research?.kpi;

  return (
    <main className={`page ${bundle || drawerItem ? "page-with-drawer" : ""}`}>
      <PageHeader title="Discovery dashboard" />

      <section className="kpi-row gp-tiles" aria-label="Key metrics">
        <button
          type="button"
          className="kpi-card kpi-card-interactive gp-tile"
          onClick={() => void openEvidence("Relevant items", "kind=relevant")}
        >
          <span className="kpi-label">Relevant data points</span>
          <span className="kpi-value">{data.relevant_count.toLocaleString()}</span>
          <span className="kpi-hint">Search-related after Training Data filters</span>
        </button>
        <button
          type="button"
          className="kpi-card kpi-card-interactive gp-tile"
          onClick={() => void openEvidence("Actionable signals", "kind=signal&signal=actionable")}
        >
          <span className="kpi-label">Actionable signals</span>
          <span className="kpi-value">{kpi?.actionable_count?.toLocaleString() ?? "—"}</span>
          <span className="kpi-hint">Specific pain points used for theme tags</span>
        </button>
        <div className="kpi-card gp-tile">
          <span className="kpi-label">Pain-point themes</span>
          <span className="kpi-value">{kpi?.overarching_theme_count ?? "—"}</span>
          <span className="kpi-hint">Design, system, query, awareness</span>
        </div>
        <button
          type="button"
          className="kpi-card kpi-card-interactive gp-tile"
          onClick={() => void openEvidence("User suggestions", "kind=suggestion")}
        >
          <span className="kpi-label">User suggestions</span>
          <span className="kpi-value">{kpi?.suggestion_items ?? "—"}</span>
          <span className="kpi-hint">Ranked by helpful votes / replies</span>
        </button>
      </section>

      <div className="chart-grid">
        <article className="card">
          <h2 className="card-title">Overall search sentiment</h2>
          <p className="card-sub">Positive, negative, or neutral about finding photos</p>
          <NamedPieChart
            data={research?.overall_sentiment || []}
            colors={SENTIMENT_COLORS}
            onSliceClick={(id) => void openEvidence(`Sentiment: ${id}`, `kind=sentiment&sentiment=${id}`)}
          />
        </article>

        <article className="card">
          <h2 className="card-title">Exploration signal mix</h2>
          <p className="card-sub">Actionable pain points vs overall opinions or forum replies</p>
          <NamedPieChart
            data={research?.signal_mix || []}
            colors={SIGNAL_COLORS}
            onSliceClick={(id) => void openEvidence(`Signal: ${id}`, `kind=signal&signal=${id}`)}
          />
        </article>

        <article className="card span-2">
          <h2 className="card-title">User pain points</h2>
          <p className="card-sub">Overarching themes — items may count in more than one</p>
          <FrequencyBarChart
            data={(research?.pain_points || []).map((p) => ({
              id: p.taxonomy_node_id,
              label: p.name,
              value: p.frequency,
            }))}
            onBarClick={(id) => {
              const row = research?.pain_points.find((p) => p.taxonomy_node_id === id);
              if (row) {
                void openEvidence(row.name, `kind=category_frequency&taxonomy_node_id=${id}`);
              }
            }}
          />
        </article>

        <article className="card span-2">
          <h2 className="card-title">Common sub-themes</h2>
          <p className="card-sub">Specific failure modes under the four pain-point themes</p>
          <FrequencyBarChart
            data={(research?.sub_themes || []).slice(0, 14).map((p) => ({
              id: p.taxonomy_node_id,
              label: p.name,
              value: p.frequency,
            }))}
            onBarClick={(id) =>
              void openEvidence(
                research?.sub_themes.find((s) => s.taxonomy_node_id === id)?.name || id,
                `kind=category_frequency&taxonomy_node_id=${id}`,
              )
            }
          />
        </article>

        <article className="card">
          <h2 className="card-title">Search / AI Search</h2>
          <p className="card-sub">Search bar, AI search, Ask Photos, and Gemini — shown separately from other search types</p>
          <SearchAiSearchWidget
            data={
              research?.search_ai_search ?? {
                id: "search_ai_search",
                name: "Search/AI Search",
                frequency: 0,
                positive: 0,
                negative: 0,
                neutral: 0,
              }
            }
            onOpenEvidence={() =>
              void openEvidence("Search / AI Search", "kind=search_type&search_type=search_ai_search")
            }
            onSentimentClick={(sentiment) =>
              void openEvidence(
                `Search / AI Search (${sentiment})`,
                `kind=search_type&search_type=search_ai_search&sentiment=${sentiment}`,
              )
            }
          />
        </article>

        <article className="card">
          <h2 className="card-title">Search types mentioned</h2>
          <p className="card-sub">
            People, places, dates, and other modes · excludes Search/AI Search · forum replies excluded
          </p>
          <FrequencyBarChart
            data={(research?.search_types || []).map((p) => ({
              id: p.id,
              label: p.name,
              value: p.frequency,
            }))}
            barColor="#9334e6"
            onBarClick={(id) =>
              void openEvidence(
                research?.search_types.find((s) => s.id === id)?.name || id,
                `kind=search_type&search_type=${id}`,
              )
            }
          />
        </article>

        <article className="card">
          <h2 className="card-title">Search type sentiment</h2>
          <p className="card-sub">Positive, negative, and neutral per search type · excludes Search/AI Search</p>
          <SearchTypeSentimentChart
            rows={research?.search_type_sentiment || []}
            onBarClick={(id) =>
              void openEvidence(
                research?.search_type_sentiment.find((s) => s.id === id)?.name ||
                  research?.search_types.find((s) => s.id === id)?.name ||
                  id,
                `kind=search_type&search_type=${id}`,
              )
            }
          />
        </article>

        <article className="card span-2">
          <h2 className="card-title">Highest-engagement suggestions</h2>
          <p className="card-sub">{research?.suggestion_summary}</p>
          <ul className="snippet-list">
            {(research?.top_suggestions || []).map((item) => (
              <li key={item.id} className="snippet-row">
                <div className="snippet-meta">
                  <span className="hit-pill">{SOURCE_LABELS[item.source] || item.source}</span>
                  {item.rank > 0 ? <span className="muted">{item.rank} helpful</span> : null}
                  {item.authored_at ? <span className="muted">{String(item.authored_at).slice(0, 10)}</span> : null}
                </div>
                <blockquote>{item.snippet}</blockquote>
                <div className="hit-actions">
                  <button type="button" onClick={() => setDrawerItem(item.id)}>
                    View item
                  </button>
                  {item.source_url ? (
                    <a href={item.source_url} target="_blank" rel="noreferrer">
                      Open source
                    </a>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          {(research?.top_suggestions || []).length === 0 ? (
            <p className="chart-empty">No suggestion snippets in the filtered corpus.</p>
          ) : null}
        </article>

        <article className="card span-2">
          <h2 className="card-title">Year coverage</h2>
          <p className="card-sub">Authored feedback by year in this snapshot</p>
          <YearCoverageChart rows={research?.year_coverage || []} />
        </article>

        <article className="card span-2">
          <h2 className="card-title">User segments</h2>
          <p className="card-sub">Library size, photo age, geography, and device when the user states them</p>
          <SegmentBars
            segments={data.segments}
            onBarClick={(key, val) =>
              void openEvidence(
                `${key}=${val}`,
                `kind=segment&segment_key=${key}&segment_value=${encodeURIComponent(val)}`,
              )
            }
          />
        </article>
      </div>

      <EvidenceDrawer
        itemId={drawerItem}
        evidenceKind={bundle || undefined}
        onClose={() => {
          setDrawerItem(null);
          setBundle(null);
        }}
      />
    </main>
  );
}
