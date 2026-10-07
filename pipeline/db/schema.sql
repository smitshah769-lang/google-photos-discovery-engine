-- AI Discovery Engine snapshot schema (Phase 0). Immutable after freeze.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS analysis_run (
  id TEXT PRIMARY KEY,
  run_spec_json TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  created_at TEXT NOT NULL,
  frozen_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('draft', 'frozen')),
  corpus_target_relevant INTEGER NOT NULL DEFAULT 500
);

CREATE TABLE IF NOT EXISTS source_run (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_run(id),
  source TEXT NOT NULL CHECK (
    source IN ('app_store', 'play_store', 'reddit', 'help_community')
  ),
  query_spec_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  item_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (
    status IN ('pending', 'running', 'success', 'partial', 'failed', 'gap', 'skipped')
  ),
  notes TEXT,
  UNIQUE (analysis_run_id, source)
);

CREATE TABLE IF NOT EXISTS stage_receipt (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_run(id),
  stage TEXT NOT NULL CHECK (
    stage IN ('normalize', 'analyze', 'index', 'aggregate', 'freeze')
  ),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK (
    status IN ('pending', 'running', 'success', 'partial', 'failed', 'skipped')
  ),
  item_count INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  UNIQUE (analysis_run_id, stage)
);

CREATE TABLE IF NOT EXISTS model_run (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_run(id),
  purpose TEXT NOT NULL,
  prompt_version TEXT,
  model_id TEXT NOT NULL,
  temperature REAL,
  input_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  output_summary TEXT
);

CREATE TABLE IF NOT EXISTS raw_record (
  id TEXT PRIMARY KEY,
  source_run_id TEXT NOT NULL REFERENCES source_run(id),
  source_native_id TEXT NOT NULL,
  payload_json TEXT,
  payload_path TEXT,
  captured_at TEXT NOT NULL,
  CHECK (payload_json IS NOT NULL OR payload_path IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS feedback_item (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_run(id),
  raw_record_id TEXT REFERENCES raw_record(id),
  source TEXT NOT NULL,
  source_url TEXT,
  authored_at TEXT,
  captured_at TEXT NOT NULL,
  locale TEXT,
  text TEXT NOT NULL,
  thread_context TEXT,
  relevance_label TEXT CHECK (
    relevance_label IN ('retrieval_related', 'unrelated', 'ambiguous')
  ),
  relevance_confidence REAL,
  segments_json TEXT,
  redaction_flag INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS taxonomy_node (
  id TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  name TEXT NOT NULL,
  definition TEXT NOT NULL,
  parent_id TEXT,
  examples_json TEXT,
  PRIMARY KEY (taxonomy_version, id)
);

CREATE TABLE IF NOT EXISTS classification (
  id TEXT PRIMARY KEY,
  feedback_item_id TEXT NOT NULL REFERENCES feedback_item(id),
  taxonomy_node_id TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  confidence REAL,
  rationale TEXT,
  model_run_id TEXT REFERENCES model_run(id),
  snippets_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS cluster (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_run(id),
  label TEXT NOT NULL,
  member_ids_json TEXT NOT NULL,
  cohesion_score REAL
);

CREATE TABLE IF NOT EXISTS category_aggregate (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_run(id),
  taxonomy_node_id TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  frequency INTEGER NOT NULL DEFAULT 0,
  severity REAL,
  source_mix_json TEXT,
  avg_confidence REAL,
  workaround_ids_json TEXT
);

CREATE TABLE IF NOT EXISTS embedding_chunk (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_run(id),
  feedback_item_id TEXT NOT NULL REFERENCES feedback_item(id),
  text TEXT NOT NULL,
  vector_id TEXT,
  metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS methodology_snapshot (
  id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL UNIQUE REFERENCES analysis_run(id),
  run_id TEXT NOT NULL,
  prompts_json TEXT,
  model_ids_json TEXT,
  coverage_stats_json TEXT,
  bias_notes TEXT,
  limitations_json TEXT NOT NULL,
  open_decisions_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_item_run ON feedback_item(analysis_run_id);
CREATE INDEX IF NOT EXISTS idx_feedback_item_authored ON feedback_item(authored_at);
CREATE INDEX IF NOT EXISTS idx_raw_record_source_run ON raw_record(source_run_id);
CREATE INDEX IF NOT EXISTS idx_classification_item ON classification(feedback_item_id);
