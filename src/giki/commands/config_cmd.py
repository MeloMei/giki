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
from ..console import console, success, error, key_value_table, print_panel

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
        error(str(e))
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
    console.print_json(json.dumps(display, indent=2, default=str))


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
        error(f"{cfg_path} not found")
        raise typer.Exit(code=1)

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        error(f"failed to parse {cfg_path}: {e}")
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
    success(f"Set [bold]{key}[/bold] = {coerced!r}")


@config_app.command("tips")
def tips() -> None:
    """Show tips about common config keys."""
    print_panel(
        "Common keys (all are optional if you're happy with defaults):\n\n"
        "  [bold]llm.compile.provider[/bold]     claude | openai\n"
        "  [bold]llm.compile.model[/bold]        model name\n"
        "  [bold]llm.compile.base_url[/bold]     API base URL\n"
        "  [bold]llm.compile.api_key_env[/bold]  env var name that holds the API key\n\n"
        "  [bold]llm.review.*[/bold]             same fields as llm.compile\n\n"
        "  [bold]ingest.chunk_size[/bold]        chars per Analyze chunk (default 12000)\n"
        "  [bold]ingest.chunk_overlap[/bold]     overlap between chunks (default 500)\n"
        "  [bold]ingest.interactive[/bold]       auto | always | never\n\n"
        "  [bold]review.severity_blocking[/bold] list of severities that fail the PR\n"
        "  [bold]review.unrelated_edit_threshold[/bold]  0.0-1.0\n\n"
        "  [bold]wiki.max_slug_length[/bold]     default 80\n"
        "  [bold]wiki.related_min_neighbors[/bold]  default 1\n\n"
        "Full reference:\n"
        "  docs/superpowers/specs/2026-06-30-giki-v0.1-design.md  §10.2\n\n"
        "Examples:\n"
        "  [dim]giki config show[/dim]\n"
        "  [dim]giki config set llm.compile.model claude-4-opus[/dim]\n"
        "  [dim]giki config set ingest.chunk_size 8000[/dim]",
        title="giki config tips",
        style="blue",
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
