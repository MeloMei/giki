"""`giki ingest` — analyze source files and synthesize wiki pages.

Thin CLI wrapper around :class:`giki.orchestrator.Ingester`. Accepts one or
more source paths; per-path exceptions are caught and reported so a single
failing source does not abort the batch.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import ConfigError, load_config
from ..orchestrator import Ingester


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
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    ingester = Ingester(config)

    n_sources = 0
    total_created = 0
    total_updated = 0
    total_failed = 0
    any_exception = False

    for path in paths:
        n_sources += 1
        try:
            result = ingester.ingest(
                path,
                branch=branch,
                yes=yes,
                dry_run=dry_run,
                retry_failed=retry_failed,
            )
        except Exception as exc:  # per-path failure — keep going
            any_exception = True
            typer.echo(f"\u00d7 {path}: {exc}", err=True)
            continue

        total_created += len(result.created)
        total_updated += len(result.updated)
        total_failed += len(result.failed)

    typer.echo(
        f"{n_sources} sources processed, "
        f"{total_created} pages created, "
        f"{total_updated} pages updated, "
        f"{total_failed} pages failed"
    )

    if any_exception or total_failed > 0:
        raise typer.Exit(code=1)
