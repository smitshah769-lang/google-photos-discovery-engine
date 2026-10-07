"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { PieLabelRenderProps } from "recharts";
import type { CategoryRow, Insights } from "@/lib/api";
import {
  CHART,
  HYPOTHESIS_COLORS,
  SENTIMENT_COLORS,
  SOURCE_COLORS,
  SOURCE_LABELS,
  VALUE_LABEL_STYLE,
} from "@/lib/chartTheme";

const tooltipProps = {
  contentStyle: {
    background: CHART.tooltipBg,
    border: `1px solid ${CHART.tooltipBorder}`,
    borderRadius: 10,
    fontSize: 13,
  },
  labelStyle: { color: "#202124" },
  itemStyle: { color: "#5f6368" },
};

function shortLabel(name: string, max = 28) {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

function formatCount(value: unknown) {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n === 0) return "";
  return n.toLocaleString();
}

function renderPieSliceLabel(props: PieLabelRenderProps) {
  const value = typeof props.value === "number" ? props.value : Number(props.value);
  if (!Number.isFinite(value) || value <= 0) return null;
  const cx = Number(props.cx ?? 0);
  const cy = Number(props.cy ?? 0);
  const midAngle = Number(props.midAngle ?? 0);
  const innerRadius = Number(props.innerRadius ?? 0);
  const outerRadius = Number(props.outerRadius ?? 0);
  const RADIAN = Math.PI / 180;
  const radius = innerRadius + (outerRadius - innerRadius) * 0.55;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text
      x={x}
      y={y}
      fill="#ffffff"
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={11}
      fontWeight={700}
    >
      {value.toLocaleString()}
    </text>
  );
}

const HORIZONTAL_BAR_MARGIN = { left: 8, right: 48, top: 8, bottom: 8 } as const;

export function SourcePieChart({
  breakdown,
  onSliceClick,
}: {
  breakdown: Record<string, number>;
  onSliceClick?: (source: string) => void;
}) {
  const data = Object.entries(breakdown)
    .map(([source, value]) => ({
      source,
      name: SOURCE_LABELS[source] || source,
      value,
    }))
    .filter((d) => d.value > 0);

  if (data.length === 0) {
    return <p className="chart-empty">No relevant items by source yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={56}
          outerRadius={92}
          paddingAngle={2}
          label={renderPieSliceLabel}
          labelLine={false}
          onClick={(_, index) => onSliceClick?.(data[index]?.source ?? "")}
          style={{ cursor: onSliceClick ? "pointer" : "default" }}
        >
          {data.map((entry) => (
            <Cell key={entry.source} fill={SOURCE_COLORS[entry.source] || CHART.accent} />
          ))}
        </Pie>
        <Tooltip {...tooltipProps} />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          formatter={(value, entry) => {
            const v = (entry.payload as { value?: number } | undefined)?.value;
            return v != null ? `${value}: ${v.toLocaleString()}` : value;
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function HypothesisPieChart({
  counts,
  onSliceClick,
}: {
  counts: Record<string, number>;
  onSliceClick?: (key: string) => void;
}) {
  const data = ["support", "contradict", "insufficient"].map((key) => ({
    key,
    name: key,
    value: counts[key] ?? 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          outerRadius={88}
          label={renderPieSliceLabel}
          labelLine={false}
          onClick={(_, i) => onSliceClick?.(data[i]?.key ?? "")}
          style={{ cursor: onSliceClick ? "pointer" : "default" }}
        >
          {data.map((entry) => (
            <Cell key={entry.key} fill={HYPOTHESIS_COLORS[entry.key]} />
          ))}
        </Pie>
        <Tooltip {...tooltipProps} />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          formatter={(value, entry) => {
            const v = (entry.payload as { value?: number } | undefined)?.value;
            return v != null ? `${value}: ${v.toLocaleString()}` : value;
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function CategoryBarChart({
  categories,
  onBarClick,
}: {
  categories: CategoryRow[];
  onBarClick?: (nodeId: string) => void;
}) {
  const data = [...categories]
    .sort((a, b) => b.frequency - a.frequency)
    .slice(0, 12)
    .map((c) => ({
      id: c.taxonomy_node_id,
      name: shortLabel(c.name),
      frequency: c.frequency,
      severity: c.severity ?? 0,
    }));

  if (data.length === 0) {
    return <p className="chart-empty">No categories to chart.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(280, data.length * 36)}>
      <BarChart data={data} layout="vertical" margin={HORIZONTAL_BAR_MARGIN}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
        <XAxis type="number" stroke={CHART.axis} fontSize={11} />
        <YAxis type="category" dataKey="name" width={140} stroke={CHART.axis} fontSize={11} />
        <Tooltip {...tooltipProps} />
        <Bar
          dataKey="frequency"
          name="Frequency"
          fill={CHART.accent}
          radius={[0, 4, 4, 0]}
          onClick={(bar) => {
            const id = (bar as { payload?: { id?: string } }).payload?.id;
            if (id) onBarClick?.(id);
          }}
          style={{ cursor: onBarClick ? "pointer" : "default" }}
        >
          <LabelList dataKey="frequency" position="right" style={VALUE_LABEL_STYLE} formatter={formatCount} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SeverityBarChart({ categories }: { categories: CategoryRow[] }) {
  const data = [...categories]
    .sort((a, b) => (b.severity ?? 0) - (a.severity ?? 0))
    .slice(0, 10)
    .map((c) => ({
      name: shortLabel(c.name, 22),
      severity: c.severity ?? 0,
    }));

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
        <XAxis dataKey="name" stroke={CHART.axis} fontSize={10} angle={-28} textAnchor="end" height={72} />
        <YAxis stroke={CHART.axis} fontSize={11} domain={[0, 1]} tickFormatter={(v) => String(v)} />
        <Tooltip {...tooltipProps} />
        <Bar dataKey="severity" name="Relative severity" fill="#6dd4a8" radius={[4, 4, 0, 0]}>
          <LabelList
            dataKey="severity"
            position="top"
            style={VALUE_LABEL_STYLE}
            formatter={(v) => (typeof v === "number" ? v.toFixed(2) : String(v))}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TrendAreaChart({ trend }: { trend: Insights["trend"] }) {
  const data = trend.buckets.map((b) => ({ period: b.period, count: b.count }));
  if (data.length === 0) {
    return <p className="chart-empty">No authored_at dates in this snapshot.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={CHART.accent} stopOpacity={0.45} />
            <stop offset="100%" stopColor={CHART.accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
        <XAxis dataKey="period" stroke={CHART.axis} fontSize={11} />
        <YAxis stroke={CHART.axis} fontSize={11} allowDecimals={false} />
        <Tooltip {...tooltipProps} />
        <Area
          type="monotone"
          dataKey="count"
          name="Relevant items"
          stroke={CHART.accent}
          fill="url(#trendFill)"
          strokeWidth={2}
        >
          <LabelList dataKey="count" position="top" style={VALUE_LABEL_STYLE} formatter={formatCount} />
        </Area>
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SegmentBars({
  segments,
  onBarClick,
}: {
  segments: Record<string, Record<string, number>>;
  onBarClick?: (key: string, value: string) => void;
}) {
  const keys = Object.keys(segments);
  if (keys.length === 0) return null;

  return (
    <div className="segment-chart-grid">
      {keys.map((segKey) => {
        const entries = Object.entries(segments[segKey]).sort((a, b) => b[1] - a[1]);
        const data = entries.map(([label, count]) => ({ label, count }));
        return (
          <div key={segKey} className="segment-mini">
            <h4>{segKey.replace(/_/g, " ")}</h4>
            <ResponsiveContainer width="100%" height={entries.length * 28 + 40}>
              <BarChart data={data} layout="vertical" margin={{ left: 4, right: 40, top: 4, bottom: 4 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="label" width={72} stroke={CHART.axis} fontSize={10} />
                <Tooltip {...tooltipProps} />
                <Bar
                  dataKey="count"
                  fill={labelColor(segKey)}
                  radius={[0, 3, 3, 0]}
                  onClick={(bar) => {
                    const label = (bar as { payload?: { label?: string } }).payload?.label;
                    if (label) onBarClick?.(segKey, label);
                  }}
                  style={{ cursor: onBarClick ? "pointer" : "default" }}
                >
                  <LabelList dataKey="count" position="right" style={VALUE_LABEL_STYLE} formatter={formatCount} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      })}
    </div>
  );
}

function labelColor(segKey: string) {
  const map: Record<string, string> = {
    library_size: "#1a73e8",
    photo_age: "#9334e6",
    geo: "#34a853",
    device: "#ea8600",
  };
  return map[segKey] || CHART.accent;
}

export function FrequencyBarChart({
  data,
  onBarClick,
  barColor = CHART.accent,
}: {
  data: { id: string; label: string; value: number }[];
  onBarClick?: (id: string) => void;
  barColor?: string;
}) {
  const rows = [...data].sort((a, b) => b.value - a.value);
  if (rows.length === 0) {
    return <p className="chart-empty">No data for this chart yet.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={Math.max(240, rows.length * 34)}>
      <BarChart data={rows} layout="vertical" margin={HORIZONTAL_BAR_MARGIN}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
        <XAxis type="number" stroke={CHART.axis} fontSize={11} allowDecimals={false} />
        <YAxis type="category" dataKey="label" width={150} stroke={CHART.axis} fontSize={11} />
        <Tooltip {...tooltipProps} />
        <Bar
          dataKey="value"
          name="Count"
          fill={barColor}
          radius={[0, 8, 8, 0]}
          onClick={(bar) => {
            const id = (bar as { payload?: { id?: string } }).payload?.id;
            if (id) onBarClick?.(id);
          }}
          style={{ cursor: onBarClick ? "pointer" : "default" }}
        >
          <LabelList dataKey="value" position="right" style={VALUE_LABEL_STYLE} formatter={formatCount} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function NamedPieChart({
  data,
  colors,
  onSliceClick,
}: {
  data: { id: string; label: string; value: number }[];
  colors: Record<string, string>;
  onSliceClick?: (id: string) => void;
}) {
  const rows = data.filter((d) => d.value > 0);
  if (rows.length === 0) {
    return <p className="chart-empty">No data for this chart yet.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={rows}
          dataKey="value"
          nameKey="label"
          cx="50%"
          cy="50%"
          innerRadius={56}
          outerRadius={92}
          paddingAngle={2}
          label={renderPieSliceLabel}
          labelLine={false}
          onClick={(_, index) => onSliceClick?.(rows[index]?.id ?? "")}
          style={{ cursor: onSliceClick ? "pointer" : "default" }}
        >
          {rows.map((entry) => (
            <Cell key={entry.id} fill={colors[entry.id] || CHART.accent} />
          ))}
        </Pie>
        <Tooltip {...tooltipProps} />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          formatter={(value, entry) => {
            const v = (entry.payload as { value?: number } | undefined)?.value;
            return v != null ? `${value}: ${v.toLocaleString()}` : value;
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function SearchTypeSentimentChart({
  rows,
  onBarClick,
}: {
  rows: { id: string; name: string; positive: number; negative: number; neutral: number }[];
  onBarClick?: (id: string) => void;
}) {
  if (rows.length === 0) {
    return <p className="chart-empty">No search-type sentiment yet.</p>;
  }
  const data = rows.map((r) => ({
    id: r.id,
    name: r.name.length > 18 ? `${r.name.slice(0, 17)}…` : r.name,
    positive: r.positive,
    negative: r.negative,
    neutral: r.neutral,
  }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(280, data.length * 38)}>
      <BarChart data={data} layout="vertical" margin={HORIZONTAL_BAR_MARGIN}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} horizontal={false} />
        <XAxis type="number" stroke={CHART.axis} fontSize={11} allowDecimals={false} />
        <YAxis type="category" dataKey="name" width={120} stroke={CHART.axis} fontSize={11} />
        <Tooltip {...tooltipProps} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="negative" stackId="sent" fill="#ea4335" name="Negative" radius={[0, 0, 0, 0]}
          onClick={(bar) => {
            const id = (bar as { payload?: { id?: string } }).payload?.id;
            if (id) onBarClick?.(id);
          }}
          style={{ cursor: onBarClick ? "pointer" : "default" }}
        >
          <LabelList
            dataKey="negative"
            position="center"
            fill="#ffffff"
            fontSize={10}
            fontWeight={600}
            formatter={formatCount}
          />
        </Bar>
        <Bar dataKey="neutral" stackId="sent" fill="#9aa0a6" name="Neutral"
          onClick={(bar) => {
            const id = (bar as { payload?: { id?: string } }).payload?.id;
            if (id) onBarClick?.(id);
          }}
          style={{ cursor: onBarClick ? "pointer" : "default" }}
        >
          <LabelList
            dataKey="neutral"
            position="center"
            fill="#202124"
            fontSize={10}
            fontWeight={600}
            formatter={formatCount}
          />
        </Bar>
        <Bar dataKey="positive" stackId="sent" fill="#34a853" name="Positive" radius={[0, 8, 8, 0]}
          onClick={(bar) => {
            const id = (bar as { payload?: { id?: string } }).payload?.id;
            if (id) onBarClick?.(id);
          }}
          style={{ cursor: onBarClick ? "pointer" : "default" }}
        >
          <LabelList
            dataKey="positive"
            position="center"
            fill="#ffffff"
            fontSize={10}
            fontWeight={600}
            formatter={formatCount}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SearchAiSearchWidget({
  data,
  onOpenEvidence,
  onSentimentClick,
}: {
  data: {
    name: string;
    frequency: number;
    positive: number;
    negative: number;
    neutral: number;
  };
  onOpenEvidence?: () => void;
  onSentimentClick?: (sentiment: string) => void;
}) {
  const sentimentData = [
    { id: "positive", label: "Positive", value: data.positive },
    { id: "negative", label: "Negative", value: data.negative },
    { id: "neutral", label: "Neutral", value: data.neutral },
  ].filter((d) => d.value > 0);

  if (data.frequency === 0) {
    return <p className="chart-empty">No Search/AI Search mentions in this snapshot.</p>;
  }

  return (
    <div className="search-ai-widget">
      <button type="button" className="search-ai-mentions" onClick={onOpenEvidence}>
        <span className="kpi-value">{data.frequency.toLocaleString()}</span>
        <span className="kpi-label">mentions</span>
      </button>
      <p className="search-ai-caption muted">
        Search bar, search results, AI search, Ask Photos, or Gemini
      </p>
      {sentimentData.length > 0 ? (
        <NamedPieChart
          data={sentimentData}
          colors={SENTIMENT_COLORS}
          onSliceClick={(id) => onSentimentClick?.(id)}
        />
      ) : (
        <p className="chart-empty">No sentiment breakdown for this type.</p>
      )}
    </div>
  );
}

export function YearCoverageChart({ rows }: { rows: { year: string; count: number }[] }) {
  if (rows.length === 0) {
    return <p className="chart-empty">No authored dates in this snapshot.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} margin={{ left: 0, right: 8, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
        <XAxis dataKey="year" stroke={CHART.axis} fontSize={11} />
        <YAxis stroke={CHART.axis} fontSize={11} allowDecimals={false} />
        <Tooltip {...tooltipProps} />
        <Bar dataKey="count" name="Items" fill="#1a73e8" radius={[8, 8, 0, 0]}>
          <LabelList dataKey="count" position="top" style={VALUE_LABEL_STYLE} formatter={formatCount} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
