export const SOURCE_COLORS: Record<string, string> = {
  app_store: "#7eb6ff",
  play_store: "#6dd4a8",
  reddit: "#ff8f6b",
  help_community: "#c9a0ff",
};

export const HYPOTHESIS_COLORS: Record<string, string> = {
  support: "#6dd4a8",
  contradict: "#f28b82",
  insufficient: "#9aabba",
};

export const CHART = {
  grid: "#e8eaed",
  axis: "#5f6368",
  tooltipBg: "#ffffff",
  tooltipBorder: "#dadce0",
  accent: "#1a73e8",
  valueLabel: "#3c4043",
};

/** Recharts LabelList / pie label styling */
export const VALUE_LABEL_STYLE = {
  fontSize: 11,
  fontWeight: 600,
  fill: CHART.valueLabel,
} as const;

export const SENTIMENT_COLORS: Record<string, string> = {
  positive: "#34a853",
  negative: "#ea4335",
  neutral: "#9aa0a6",
};

export const SIGNAL_COLORS: Record<string, string> = {
  actionable: "#1a73e8",
  no_signal: "#9aa0a6",
};

export const SOURCE_LABELS: Record<string, string> = {
  app_store: "App Store",
  play_store: "Play Store",
  reddit: "Reddit",
  help_community: "Help Community",
};
