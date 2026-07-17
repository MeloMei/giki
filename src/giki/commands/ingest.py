"""`giki ingest` — analyze source files and synthesize wiki pages.

Thin CLI wrapper around :class:`giki.orchestrator.Ingester`. Accepts one or
more source paths; per-path exceptions are caught and reported so a single
failing source does not abort the batch.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import ConfigError, load_config
from ..llm import build_client
from ..llm.usage import UsageTracker
from ..orchestrator import Ingester
from ..console import console, success, error, info, warn, print_panel


def ingest_command(
    paths: list[Path] = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Source file(s) to ingest.",
    ),
    branch: str | None = typer.Option(
        None,
        "--branch",
        help="Ingest on this branch (create if missing).",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Non-interactive; accept all candidate pages.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print candidates without writing files.",
    ),
    retry_failed: bool = typer.Option(
        False,
        "--retry-failed",
        help="Retry only pages that failed last time.",
    ),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (default: cwd).",
    ),
) -> None:
    """Ingest one or more source files into the wiki."""
    try:
        config = load_config(root.resolve())
    except ConfigError as e:
        error(str(e))
        raise typer.Exit(code=1)

    ingester = Ingester(config)

    # Track LLM usage across the whole batch; the wrapped client is built
    # lazily, so runs that make no LLM calls never require an API key.
    usage = UsageTracker(command="ingest")
    llm_client = usage.wrap(lambda: build_client(config.llm.compile))

    n_sources = 0
    total_created = 0
    total_updated = 0
    total_failed = 0
    any_exception = False

    for path in paths:
        n_sources += 1
        info(f"ingesting [bold]{path.name}[/bold] ...")
        try:
            result = ingester.ingest(
                path,
                branch=branch,
                yes=yes,
                dry_run=dry_run,
                retry_failed=retry_failed,
                llm_client=llm_client,
            )
        except Exception as exc:  # per-path failure — keep going
            any_exception = True
            error(f"{path}: {exc}")
            continue

        total_created += len(result.created)
        total_updated += len(result.updated)
        total_failed += len(result.failed)

        if result.created:
            for slug in result.created:
                success(f"  created [bold]{slug}[/bold]")
        if result.updated:
            for slug in result.updated:
                info(f"  updated [bold]{slug}[/bold]")
        if result.failed:
            for item in result.failed:
                error(f"  failed [bold]{item.slug}[/bold]: {item.error}")

    # Summary
    summary_lines = [
        f"{n_sources} source(s) processed",
        f"{total_created} page(s) created",
        f"{total_updated} page(s) updated",
        f"{total_failed} page(s) failed",
    ]
    console.print()
    print_panel("\n".join(summary_lines), title="Ingest Summary")

    # LLM usage panel + ledger (only when LLM calls were actually made).
    # The ledger is an audit aid — a write failure must not fail the run.
    if usage.records:
        ledger = None
        try:
            ledger = usage.append_ledger(config.state_dir)
        except OSError as e:
            warn(f"could not write usage ledger: {e}")
        lines = usage.summary_lines()
        if ledger is not None:
            lines.append(f"ledger: {ledger.relative_to(config.root)}")
        print_panel("\n".join(lines), title="LLM Usage")

    if any_exception or total_failed > 0:
        raise typer.Exit(code=1)
