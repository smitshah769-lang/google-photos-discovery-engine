# Rebuild from stored raw + run spec

Reproducibility target (System Architecture §15): **the same run config plus stored raw payloads can rebuild aggregates**. Serving the frozen dashboard and RAG does **not** require collectors or Ollama to be running.

## Serve the frozen artifact (product review)

No `collect` / `analyze` jobs:

```bash
python -m pipeline serve <run-id>                 # read-only API on 127.0.0.1:8765
./scripts/serve-artifact.sh <run-id>              # API + Next.js UI on 127.0.0.1:3000
```

Or serve the export bundle (copy under `data/exports/<run-id>/`):

```bash
python -m pipeline serve --export-dir data/exports/<run-id>
```

Default bind is localhost. If you bind `0.0.0.0` without HTTP basic auth, the CLI and API print a warning. Set `DISCOVERY_BASIC_USER` and `DISCOVERY_BASIC_PASSWORD` (and `NEXT_PUBLIC_DISCOVERY_BASIC_AUTH=user:password` for the UI).

## Rebuild aggregates (no web collect)

On a **draft** (not frozen) run that already has `raw_record` rows:

```bash
python -m pipeline rebuild <run-id>
```

This re-runs `normalize` → `analyze` → `index` → `aggregate` only. It is refused if the run is frozen (edge §6: never overwrite a freeze in place).

## Rebuild from a freeze export (new run_id)

```bash
python -m pipeline rebuild-from-export data/exports/<run-id>
```

Copies source receipts + raw payloads into a **new** analysis run, then rebuilds aggregates. Use this when sharing a redacted export or when the original freeze must stay immutable.

Required inputs inside the export directory:

- `snapshot.db` (includes `raw_record` + `source_run`)
- `run.yaml` (copied from `config/run.yaml` at freeze)
- optional `rag/<run-id>.json` (rebuilt by `index` anyway)

## Share outside the research team

```bash
python -m pipeline freeze <run-id> --redact    # first freeze
python -m pipeline export <run-id> --redact    # refresh export after freeze
```

Redaction strips public display names / handles in the **export copy only**. Public URLs stay. Do not join handles to Google accounts.

## What this does not rebuild

- Live store/forum fetches (`collect`) — that is a new snapshot.
- Problem-statement Phase 2 product review or Phase 3 in-Photos search features — those are out of this repository.
