"""`giki config show / set / tips` command implementations.

NOTE: `set` rewrites .giki/config.yaml without preserving YAML comments.
This is a v0.1 limitation and is intentional — the config schema is small
enough that regenerating from scratch is acceptable.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer
import yaml

from ..config import ConfigError, load_config

config_app = typer.Typer(
    help="Manage .giki/config.yaml. Note: `set` does not preserve YAML comments.",
    no_args_is_help=True,
)


@config_app.command("show")
def show(
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """Print the loaded config."""
    try:
        cfg = load_config(root)
    except ConfigError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1)

    # Serialize the dataclass hierarchy to a dict for display
    def _to_display(obj):
        if hasattr(obj, "__dataclass_fields__"):
            d = asdict(obj)
            # Drop derived Path fields that would clutter output
            for k in ("root", "giki_dir", "state_dir"):
                d.pop(k, None)
            return d
        return obj

    display = _to_display(cfg)
    # JSON is easier to read than yaml.dump for showing computed defaults
    typer.echo(json.dumps(display, indent=2, default=str))


@config_app.command("set")
def set_command(
    key: str = typer.Argument(..., help="Dot-path key, e.g. llm.compile.model"),
    value: str = typer.Argument(..., help="New value (string). Booleans/numbers auto-detected."),
    root: Path = typer.Option(
        Path("."), "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """Update a config value. Overwrites .giki/config.yaml (comments not preserved)."""
    cfg_path = Path(root) / ".giki" / "config.yaml"
    if not cfg_path.exists():
        typer.echo(f"error: {cfg_path} not found", err=True)
        raise typer.Exit(code=1)

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        typer.echo(f"error: failed to parse {cfg_path}: {e}", err=True)
        raise typer.Exit(code=1)

    parts = key.split(".")
    coerced = _coerce_value(value)

    # Traverse / create nested dicts
    node = raw
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = coerced

    cfg_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    typer.echo(f"Set {key} = {coerced!r}")


@config_app.command("tips")
def tips() -> None:
    """Show tips about common config keys."""
    typer.echo(
        """giki config tips
================

Common keys (all are optional if you're happy with defaults):

  llm.compile.provider     claude | openai
  llm.compile.model        model name
  llm.compile.base_url     API base URL
  llm.compile.api_key_env  env var name that holds the API key

  llm.review.*             same fields as llm.compile

  ingest.chunk_size        chars per Analyze chunk (default 12000)
  ingest.chunk_overlap     overlap between chunks (default 500)
  ingest.interactive       auto | always | never

  review.severity_blocking list of severities that fail the PR
  review.unrelated_edit_threshold  0.0-1.0

  wiki.max_slug_length     default 80
  wiki.related_min_neighbors  default 1

Full reference:
  docs/superpowers/specs/2026-06-30-giki-v0.1-design.md  §10.2

Examples:
  giki config show
  giki config set llm.compile.model claude-4-opus
  giki config set ingest.chunk_size 8000
"""
    )


def _coerce_value(text: str):
    """Coerce a CLI string to bool / int / float / str."""
    lowered = text.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text
