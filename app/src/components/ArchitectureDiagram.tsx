import type { ReactNode } from "react";

/**
 * High-level architecture (System Architecture.md §3).
 * One-time batch snapshot; read-only UI after freeze.
 */
export function ArchitectureDiagram() {
  return (
    <figure className="arch-diagram" aria-labelledby="arch-diagram-title">
      <figcaption id="arch-diagram-title" className="sr-only">
        Discovery engine architecture: presentation, application APIs, batch pipeline, data stores,
        and four source adapters.
      </figcaption>
      <svg
        viewBox="0 0 720 520"
        role="img"
        aria-label="Architecture diagram"
        className="arch-diagram-svg"
      >
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" fill="#6eb5ff" />
          </marker>
          <linearGradient id="layerGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1e2834" />
            <stop offset="100%" stopColor="#171f28" />
          </linearGradient>
        </defs>

        <LayerBox y={8} h={56} title="Presentation layer">
          <text x={360} y={48} textAnchor="middle" className="arch-body">
            Dashboard · RAG Search · How the Engine Works · Evidence drawer
          </text>
        </LayerBox>

        <Connector x1={360} y1={64} y2={88} />

        <LayerBox y={88} h={52} title="Application layer">
          <text x={360} y={126} textAnchor="middle" className="arch-body">
            Insights API · Semantic search API · Methodology / metrics API
          </text>
        </LayerBox>

        <Connector x1={360} y1={140} y2={164} />

        <LayerBox y={164} h={72} title="Intelligence & processing (batch)">
          <text x={360} y={198} textAnchor="middle" className="arch-body">
            Ingest → Normalize → Filter → Classify → Cluster → Score
          </text>
          <text x={360} y={218} textAnchor="middle" className="arch-body-muted">
            Embed → Index (vector + metadata)
          </text>
        </LayerBox>

        <Connector x1={360} y1={236} y2={260} />

        <LayerBox y={260} h={68} title="Data layer">
          <text x={360} y={294} textAnchor="middle" className="arch-body">
            Raw store · Canonical feedback DB · Taxonomy · Vector index
          </text>
          <text x={360} y={314} textAnchor="middle" className="arch-body-muted">
            Artifacts (run config, prompts, evals, export snapshots)
          </text>
        </LayerBox>

        <Connector x1={360} y1={368} y2={328} />

        <LayerBox y={368} h={88} title="Source adapters (batch, four only)" accent>
          <text x={360} y={408} textAnchor="middle" className="arch-body">
            Play Store (batchexecute) · App Store (RSS)
          </text>
          <text x={360} y={428} textAnchor="middle" className="arch-body">
            Reddit (Arctic Shift) · Photos Help Community (search + HTML)
          </text>
        </LayerBox>

        <text x={360} y={498} textAnchor="middle" className="arch-footnote">
          After freeze, the UI reads the snapshot only — no live collectors or in-place mutation.
        </text>
      </svg>
    </figure>
  );
}

function LayerBox({
  y,
  h,
  title,
  accent,
  children,
}: {
  y: number;
  h: number;
  title: string;
  accent?: boolean;
  children: ReactNode;
}) {
  const stroke = accent ? "#3d6a99" : "#263240";
  return (
    <g>
      <rect
        x={24}
        y={y}
        width={672}
        height={h}
        rx={10}
        fill="url(#layerGrad)"
        stroke={stroke}
        strokeWidth={1.5}
      />
      <text x={48} y={y + 22} className="arch-title">{title}</text>
      {children}
    </g>
  );
}

function Connector({ x1, y1, y2 }: { x1: number; y1: number; y2: number }) {
  return (
    <path
      d={`M ${x1} ${y1} L ${x1} ${y2}`}
      stroke="#6eb5ff"
      strokeWidth={2}
      markerEnd="url(#arrow)"
      fill="none"
    />
  );
}
