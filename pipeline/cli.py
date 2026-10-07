from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from pipeline.config_loader import load_run_spec
from pipeline.db.connection import get_connection
from pipeline.env_loader import load_project_env
from pipeline.import_json import DEFAULT_JSON, import_raw_json, load_export
from pipeline.paths import db_path
from pipeline.run_context import create_analysis_run, ensure_database
from pipeline.run_status import get_run_status
from pipeline.rag.search import SearchRequest, search
from pipeline.export_bundle import overlay_export_run_spec
from pipeline.serve.auth import bind_without_auth_warning, serving_credentials
from pipeline.serve.http import serve_api
from pipeline.stages import (
    rebuild_from_export,
    run_aggregate,
    run_analyze,
    run_collect,
    run_export,
    run_freeze,
    run_index,
    run_normalize,
    run_rebuild,
)
from pipeline.stages.llm_second_pass import run_llm_second_pass
from pipeline.stages.rebuild import load_serve_spec_from_export
from pipeline.taxonomy import load_taxonomy


@click.group()
@click.option(
    "--run-spec",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="Path to run.yaml (default: config/run.yaml)",
)
@click.pass_context
def cli(ctx: click.Context, run_spec: Path | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["run_spec_path"] = run_spec
    ctx.obj["run_spec"] = load_run_spec(run_spec)


@cli.command("init-db")
@click.pass_context
def init_db(ctx: click.Context) -> None:
    """Create SQLite schema and load taxonomy v0."""
    db_file = ensure_database(ctx.obj["run_spec_path"])
    taxonomy = load_taxonomy()
    click.echo(f"Initialized database at {db_file}")
    click.echo(f"Taxonomy {taxonomy.version}: {len(taxonomy.nodes)} nodes")


@cli.command("new-run")
@click.option("--run-id", default=None, help="Optional fixed UUID for reproducibility in tests")
@click.pass_context
def new_run(ctx: click.Context, run_id: str | None) -> None:
    """Create a draft analysis_run with source and stage placeholders."""
    run_spec = ctx.obj["run_spec"]
    ensure_database(ctx.obj["run_spec_path"])
    with get_connection(db_path(run_spec)) as conn:
        created = create_analysis_run(conn, run_spec, run_id=run_id)
    click.echo(created)


def _run_stage(ctx: click.Context, stage_fn, analysis_run_id: str) -> None:
    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        result = stage_fn(conn, analysis_run_id)
    click.echo(json.dumps(result, indent=2))


@cli.command()
@click.argument("analysis_run_id")
@click.option(
    "--fixtures",
    is_flag=True,
    help="Use tests/fixtures for this collect only (does not edit run.yaml)",
)
@click.option(
    "--only",
    type=click.Choice(["app_store", "play_store", "reddit", "help_community"]),
    default=None,
    help="Collect a single source (Play writes each page to the DB with configured delay)",
)
@click.pass_context
def collect(ctx: click.Context, analysis_run_id: str, fixtures: bool, only: str | None) -> None:
    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        result = run_collect(
            conn,
            analysis_run_id,
            use_fixtures=fixtures,
            only=only,
            live_run_spec=run_spec,
        )
    click.echo(json.dumps(result, indent=2))


@cli.command()
@click.argument("analysis_run_id")
@click.pass_context
def normalize(ctx: click.Context, analysis_run_id: str) -> None:
    _run_stage(ctx, run_normalize, analysis_run_id)


@cli.command()
@click.argument("analysis_run_id")
@click.pass_context
def analyze(ctx: click.Context, analysis_run_id: str) -> None:
    _run_stage(ctx, run_analyze, analysis_run_id)


@cli.command("llm-second-pass")
@click.argument("analysis_run_id")
@click.option("--limit", type=int, default=None, help="Process at most N items (for smoke tests)")
@click.option("--no-resume", is_flag=True, help="Re-process items even if already in output JSONL")
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help="Audit JSONL path (default: data/llm_second_pass_<run-id>.jsonl)",
)
@click.option("--reaggregate", is_flag=True, help="Run aggregate stage after labeling")
@click.pass_context
def llm_second_pass_cmd(
    ctx: click.Context,
    analysis_run_id: str,
    limit: int | None,
    no_resume: bool,
    output_path: Path | None,
    reaggregate: bool,
) -> None:
    """Ollama second pass: refine regex retrieval_related items per Training Data.md."""
    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        result = run_llm_second_pass(
            conn,
            analysis_run_id,
            output_path=output_path,
            limit=limit,
            resume=not no_resume,
            reaggregate=reaggregate,
        )
    click.echo(json.dumps(result, indent=2))
    if result.get("status") == "failed":
        raise click.ClickException(str(result.get("error") or "llm-second-pass failed"))


@cli.command("index")
@click.argument("analysis_run_id")
@click.pass_context
def index_cmd(ctx: click.Context, analysis_run_id: str) -> None:
    _run_stage(ctx, run_index, analysis_run_id)


@cli.command("search")
@click.argument("analysis_run_id")
@click.option("--query", "-q", required=True, help="Natural-language search query")
@click.option("--source", "sources", multiple=True, help="Filter by source (repeatable)")
@click.option("--category", default=None, help="Taxonomy node id filter")
@click.option("--min-confidence", type=float, default=None)
@click.option("--include-synthesis", is_flag=True, help="Request cited summary when configured")
@click.pass_context
def search_cmd(
    ctx: click.Context,
    analysis_run_id: str,
    query: str,
    sources: tuple[str, ...],
    category: str | None,
    min_confidence: float | None,
    include_synthesis: bool,
) -> None:
    """Phase 3 semantic search with scope gate and citations."""
    run_spec = ctx.obj["run_spec"]
    req = SearchRequest(
        query=query,
        sources=list(sources) if sources else None,
        category=category,
        min_confidence=min_confidence,
        include_synthesis=include_synthesis if include_synthesis else None,
    )
    with get_connection(db_path(run_spec)) as conn:
        result = search(conn, analysis_run_id, req, run_spec=run_spec)
    click.echo(json.dumps(result.to_dict(), indent=2))


def _serve(
    ctx: click.Context,
    analysis_run_id: str | None,
    host: str | None,
    port: int | None,
    export_dir: Path | None,
) -> None:
    run_spec = ctx.obj["run_spec"]
    run_id = analysis_run_id
    if export_dir is not None:
        loaded_id, run_spec = load_serve_spec_from_export(export_dir, run_spec)
        run_id = run_id or loaded_id
        run_spec = overlay_export_run_spec(run_spec, export_dir)
    if not run_id:
        raise click.ClickException("Pass an analysis run id or --export-dir")
    serving = run_spec.get("serving") or {}
    bind_host = host or str(serving.get("bind_host") or "127.0.0.1")
    bind_port = port or int(serving.get("bind_port") or 8765)
    warning = bind_without_auth_warning(bind_host, serving_credentials(run_spec))
    if warning:
        click.echo(warning, err=True)
    serve_api(run_spec, run_id, host=bind_host, port=bind_port)


@cli.command("serve")
@click.argument("analysis_run_id", required=False)
@click.option("--host", default=None, help="Bind host (default from run.yaml serving.bind_host)")
@click.option("--port", type=int, default=None, help="Bind port (default from run.yaml serving.bind_port)")
@click.option(
    "--export-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
    help="Serve the frozen export bundle (snapshot.db + rag/) instead of data/",
)
@click.pass_context
def serve_cmd(
    ctx: click.Context,
    analysis_run_id: str | None,
    host: str | None,
    port: int | None,
    export_dir: Path | None,
) -> None:
    """Serve read-only APIs from a frozen snapshot (no pipeline jobs)."""
    _serve(ctx, analysis_run_id, host, port, export_dir)


@cli.command("serve-search")
@click.argument("analysis_run_id", required=False)
@click.option("--host", default=None, help="Bind host (default from run.yaml serving.bind_host)")
@click.option("--port", type=int, default=None, help="Bind port (default from run.yaml serving.bind_port)")
@click.option(
    "--export-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
)
@click.pass_context
def serve_search_cmd(
    ctx: click.Context,
    analysis_run_id: str | None,
    host: str | None,
    port: int | None,
    export_dir: Path | None,
) -> None:
    """Alias for `serve` (Phase 3 name)."""
    _serve(ctx, analysis_run_id, host, port, export_dir)


@cli.command()
@click.argument("analysis_run_id")
@click.pass_context
def aggregate(ctx: click.Context, analysis_run_id: str) -> None:
    _run_stage(ctx, run_aggregate, analysis_run_id)


@cli.command()
@click.argument("analysis_run_id")
@click.option("--dry-run", is_flag=True, help="Report freeze intent without writing frozen_at")
@click.option("--redact", is_flag=True, help="Redact usernames in the export copy only")
@click.pass_context
def freeze(ctx: click.Context, analysis_run_id: str, dry_run: bool, redact: bool) -> None:
    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        result = run_freeze(conn, analysis_run_id, dry_run=dry_run, redact=redact)
    click.echo(json.dumps(result, indent=2))


@cli.command("export")
@click.argument("analysis_run_id")
@click.option("--redact", is_flag=True, help="Strip display names/handles in the export copy only")
@click.pass_context
def export_cmd(ctx: click.Context, analysis_run_id: str, redact: bool) -> None:
    """Refresh data/exports/<run-id>/ (works on frozen runs; does not unfreeze)."""
    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        result = run_export(conn, analysis_run_id, redact=redact)
    click.echo(json.dumps(result, indent=2, default=str))


@cli.command("rebuild")
@click.argument("analysis_run_id")
@click.pass_context
def rebuild_cmd(ctx: click.Context, analysis_run_id: str) -> None:
    """Rebuild normalize/analyze/index/aggregate from stored raw. Refused if frozen."""
    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        result = run_rebuild(conn, analysis_run_id)
    click.echo(json.dumps(result, indent=2))


@cli.command("rebuild-from-export")
@click.argument("export_dir", type=click.Path(path_type=Path, exists=True, file_okay=False))
@click.pass_context
def rebuild_from_export_cmd(ctx: click.Context, export_dir: Path) -> None:
    """New run_id from an export's raw + run.yaml, then rebuild aggregates (no collect)."""
    result = rebuild_from_export(
        export_dir,
        dest_run_spec=ctx.obj["run_spec"],
        dest_run_spec_path=ctx.obj.get("run_spec_path"),
    )
    click.echo(json.dumps(result, indent=2))


@cli.command("handoff")
@click.argument("analysis_run_id")
@click.pass_context
def handoff_cmd(ctx: click.Context, analysis_run_id: str) -> None:
    """Print the Phase 5 limitations pack (non-claims, gaps, rebuild, out of scope)."""
    from pipeline.handoff import handoff_payload

    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        payload = handoff_payload(conn, analysis_run_id)
    click.echo(json.dumps(payload, indent=2, default=str))


@cli.command("run-all")
@click.argument("analysis_run_id")
@click.pass_context
def run_all(ctx: click.Context, analysis_run_id: str) -> None:
    """Invoke every stage in order (Phase 0 no-ops)."""
    for stage in (collect, normalize, analyze, index_cmd, aggregate):
        ctx.invoke(stage, analysis_run_id=analysis_run_id)


@cli.command()
@click.argument("analysis_run_id")
@click.pass_context
def status(ctx: click.Context, analysis_run_id: str) -> None:
    """Show source receipts, raw counts, and feedback summary for a run."""
    run_spec = ctx.obj["run_spec"]
    with get_connection(db_path(run_spec)) as conn:
        payload = get_run_status(conn, analysis_run_id)
    click.echo(json.dumps(payload, indent=2))


@cli.command()
@click.pass_context
def smoke(ctx: click.Context) -> None:
    """Offline smoke: init-db, new run, fixture collect, normalize, status."""
    run_spec = ctx.obj["run_spec"]
    ensure_database(ctx.obj["run_spec_path"])
    with get_connection(db_path(run_spec)) as conn:
        run_id = create_analysis_run(conn, run_spec)
        collect_result = run_collect(conn, run_id, use_fixtures=True)
        norm_result = run_normalize(conn, run_id)
        summary = get_run_status(conn, run_id)
    click.echo(
        json.dumps(
            {
                "analysis_run_id": run_id,
                "collect": collect_result,
                "normalize": norm_result,
                "status": summary,
            },
            indent=2,
        )
    )


@cli.command("import-raw")
@click.argument(
    "json_path",
    type=click.Path(path_type=Path, exists=True),
    required=False,
)
@click.option("--run-id", default=None, help="Target analysis run (default: create new run)")
@click.option("--no-replace", is_flag=True, help="Append without clearing prior raw rows")
@click.option(
    "--only",
    "only_sources",
    multiple=True,
    type=click.Choice(["app_store", "play_store", "reddit", "help_community"]),
    help="Import selected sources only (repeatable)",
)
@click.pass_context
def import_raw(
    ctx: click.Context,
    json_path: Path | None,
    run_id: str | None,
    no_replace: bool,
    only_sources: tuple[str, ...],
) -> None:
    """Import photo_retrieval_feedback.json into raw_record + source_run receipts."""
    path = json_path or DEFAULT_JSON
    if not path.is_file():
        raise click.ClickException(
            f"File not found: {path}. Run npm run fetch-raw or pass a JSON path."
        )
    export = load_export(path)
    run_spec = ctx.obj["run_spec"]
    ensure_database(ctx.obj["run_spec_path"])
    do_replace = not no_replace

    with get_connection(db_path(run_spec)) as conn:
        if run_id:
            analysis_run_id = run_id
        else:
            analysis_run_id = create_analysis_run(conn, run_spec)
        sources = tuple(only_sources) if only_sources else None
        summary = import_raw_json(
            conn, analysis_run_id, export, replace=do_replace, sources=sources
        )
        conn.commit()

    click.echo(json.dumps({"analysis_run_id": analysis_run_id, **summary}, indent=2))


@cli.command("taxonomy-ids")
@click.pass_context
def taxonomy_ids(_ctx: click.Context) -> None:
    taxonomy = load_taxonomy()
    for node in taxonomy.nodes:
        click.echo(node.id)


def main() -> None:
    load_project_env()
    try:
        cli(obj={})
    except (click.ClickException, ValueError, RuntimeError) as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
