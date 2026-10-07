"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DataExtractionStats } from "@/lib/api";
import { CHART, SOURCE_COLORS, SOURCE_LABELS, VALUE_LABEL_STYLE } from "@/lib/chartTheme";

function formatBarCount(value: unknown) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n === 0) return "";
  return n.toLocaleString();
}

const tooltipProps = {
  contentStyle: {
    background: CHART.tooltipBg,
    border: `1px solid ${CHART.tooltipBorder}`,
    borderRadius: 10,
    fontSize: 13,
  },
  labelStyle: { color: "#e8eef4" },
  itemStyle: { color: "#e8eef4" },
};

export function SourceExtractionSummary({
  stats,
  partial,
}: {
  stats: DataExtractionStats | undefined;
  partial?: boolean;
}) {
  if (!stats?.by_source?.length) {
    return (
      <p className="chart-empty">
        Extraction stats are not available. Start the read API with{" "}
        <code>python -m pipeline serve &lt;run-id&gt;</code> and refresh.
      </p>
    );
  }

  const chartData = stats.by_source.map((row) => ({
    source: SOURCE_LABELS[row.source] || row.source,
    sourceKey: row.source,
    extracted: row.extracted_raw,
    relevant: row.retrieval_related,
    other: row.unrelated + row.ambiguous,
  }));

  return (
    <div className="extraction-summary">
      {partial ? <div className="alert alert-warn">{stats.note}</div> : null}
      <div className="extraction-totals">
        <div className="extraction-total-pill">
          <span className="kpi-label">Total extracted (raw)</span>
          <strong>{stats.totals.extracted_raw.toLocaleString()}</strong>
        </div>
        <div className="extraction-total-pill">
          <span className="kpi-label">Normalized items</span>
          <strong>{stats.totals.normalized_total.toLocaleString()}</strong>
        </div>
        <div className="extraction-total-pill">
          <span className="kpi-label">Retrieval-related (analysis corpus)</span>
          <strong>{stats.totals.retrieval_related.toLocaleString()}</strong>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
          <XAxis dataKey="source" stroke={CHART.axis} fontSize={11} />
          <YAxis stroke={CHART.axis} fontSize={11} allowDecimals={false} />
          <Tooltip {...tooltipProps} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="extracted" name="Extracted (raw)" radius={[4, 4, 0, 0]}>
            {chartData.map((row) => (
              <Cell key={row.sourceKey} fill={SOURCE_COLORS[row.sourceKey] || CHART.accent} />
            ))}
            <LabelList dataKey="extracted" position="top" style={VALUE_LABEL_STYLE} formatter={formatBarCount} />
          </Bar>
          <Bar dataKey="relevant" name="Retrieval-related" fill="#6dd4a8" radius={[4, 4, 0, 0]}>
            <LabelList dataKey="relevant" position="top" style={VALUE_LABEL_STYLE} formatter={formatBarCount} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Source</th>
              <th>Extracted (raw)</th>
              <th>Receipt count</th>
              <th>Normalized</th>
              <th>Retrieval-related</th>
              <th>Unrelated</th>
              <th>Ambiguous</th>
            </tr>
          </thead>
          <tbody>
            {stats.by_source.map((row) => (
              <tr key={row.source}>
                <td>{SOURCE_LABELS[row.source] || row.source}</td>
                <td>{row.extracted_raw.toLocaleString()}</td>
                <td className="muted">{row.receipt_reported.toLocaleString()}</td>
                <td>{row.normalized_total ? row.normalized_total.toLocaleString() : "—"}</td>
                <td>{row.retrieval_related.toLocaleString()}</td>
                <td>{row.unrelated ? row.unrelated.toLocaleString() : "—"}</td>
                <td>{row.ambiguous ? row.ambiguous.toLocaleString() : "—"}</td>
              </tr>
            ))}
            <tr className="totals-row">
              <td><strong>Total</strong></td>
              <td><strong>{stats.totals.extracted_raw.toLocaleString()}</strong></td>
              <td />
              <td>
                <strong>
                  {stats.totals.normalized_total
                    ? stats.totals.normalized_total.toLocaleString()
                    : "—"}
                </strong>
              </td>
              <td><strong>{stats.totals.retrieval_related.toLocaleString()}</strong></td>
              <td><strong>{stats.totals.unrelated.toLocaleString()}</strong></td>
              <td><strong>{stats.totals.ambiguous.toLocaleString()}</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="scope-line">{stats.note}</p>
    </div>
  );
}
