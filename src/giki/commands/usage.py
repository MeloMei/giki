"""`giki usage` — cumulative LLM usage and cost report from the local ledger.

Reads ``.giki-state/usage.jsonl`` (written by ``giki ingest`` and
``giki review``) and renders totals plus per-command, per-model, and
recent-run breakdowns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich import box
from rich.table import Table

from ..console import console, heading, info, print_panel, warn
from ..llm.usage import LEDGER_NAME, read_ledger


def _fmt_cost(cost: float | None, partial: bool) -> str:
    if cost is None:
        return "n/a"
    return f"{'>= ' if partial else ''}${cost:.4f}"


def _parse_ts(value) -> datetime:
    """Parse a ledger timestamp; unparseable values sort oldest."""
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_ts(value) -> str:
    """Compact timestamp for display: ``YYYY-MM-DD HH:MM``."""
    return str(value)[:16].replace("T", " ")


def _aggregate(records: list[dict], key_fn) -> dict[str, dict]:
    """Group records by ``key_fn`` into calls/tokens/cost buckets."""
    groups: dict[str, dict] = {}
    for r in records:
        g = groups.setdefault(
            key_fn(r),
            {"calls": 0, "tin": 0, "tout": 0, "cost": 0.0, "known": 0, "partial": False},
        )
        g["calls"] += 1
        g["tin"] += r["input_tokens"]
        g["tout"] += r["output_tokens"]
        c = r["cost_usd"]
        if c is None:
            g["partial"] = True
        else:
            g["known"] += 1
            g["cost"] += c
    return groups


def _group_cost(g: dict) -> str:
    """Cost cell for one group: n/a when every call has unknown pricing."""
    if g["known"] == 0:
        return "n/a"
    return _fmt_cost(g["cost"], g["partial"])


def _cost_desc(groups: dict[str, dict]) -> list[str]:
    """Group keys ordered by known cost descending; n/a groups sink last."""
    return sorted(
        groups,
        key=lambda k: (groups[k]["known"] == 0, -groups[k]["cost"], k),
    )


def _render_breakdown(title: str, first_col: str, groups: dict[str, dict]) -> None:
    heading(title)
    table = Table(box=box.SIMPLE)
    table.add_column(first_col, style="bold")
    table.add_column("calls", justify="right")
    table.add_column("tokens in", justify="right")
    table.add_column("tokens out", justify="right")
    table.add_column("cost", justify="right")
    for key in _cost_desc(groups):
        g = groups[key]
        table.add_row(
            key,
            str(g["calls"]),
            f"{g['tin']:,}",
            f"{g['tout']:,}",
            _group_cost(g),
        )
    console.print(table)


def _render_recent_runs(records: list[dict], *, limit: int = 5) -> None:
    heading(f"Recent runs (last {limit})")
    by_run = _aggregate(records, lambda r: str(r.get("run_id") or "(no run id)"))
    last_ts: dict[str, datetime] = {}
    last_ts_raw: dict[str, str] = {}
    commands: dict[str, set] = {}
    for r in records:
        rid = str(r.get("run_id") or "(no run id)")
        ts = _parse_ts(r.get("ts", ""))
        if rid not in last_ts or ts > last_ts[rid]:
            last_ts[rid] = ts
            last_ts_raw[rid] = str(r.get("ts", ""))
        commands.setdefault(rid, set()).add(str(r.get("command") or "?"))

    table = Table(box=box.SIMPLE)
    table.add_column("run", style="bold")
    table.add_column("last activity")
    table.add_column("command")
    table.add_column("calls", justify="right")
    table.add_column("cost", justify="right")
    recent = sorted(by_run, key=lambda rid: last_ts[rid], reverse=True)[:limit]
    for rid in recent:
        g = by_run[rid]
        table.add_row(
            rid,
            _fmt_ts(last_ts_raw[rid]),
            ", ".join(sorted(commands[rid])),
            str(g["calls"]),
            _group_cost(g),
        )
    console.print(table)


def usage_command(
    root: Path = typer.Option(
        Path("."), "--root", help="Knowledge base root directory"
    ),
) -> None:
    """Show cumulative LLM usage and estimated cost from the local ledger."""
    root = root.resolve()
    state_dir = root / ".giki-state"
    records, skipped = read_ledger(state_dir)

    if skipped:
        warn(f"skipped {skipped} malformed ledger line(s)")

    if not records:
        info(f"No LLM usage recorded yet (ledger: {state_dir / LEDGER_NAME})")
        return

    total_calls = len(records)
    total_in = sum(r["input_tokens"] for r in records)
    total_out = sum(r["output_tokens"] for r in records)
    known = [r for r in records if r["cost_usd"] is not None]
    total_cost = sum(r["cost_usd"] for r in known)
    partial = len(known) < total_calls

    first = _fmt_ts(min(records, key=lambda r: _parse_ts(r.get("ts", ""))).get("ts", ""))
    last = _fmt_ts(max(records, key=lambda r: _parse_ts(r.get("ts", ""))).get("ts", ""))

    print_panel(
        f"{total_calls} LLM call(s) · {total_in:,} tokens in · "
        f"{total_out:,} tokens out\n"
        f"estimated total cost: "
        f"{_fmt_cost(total_cost if known else None, partial)}\n"
        f"ledger span: {first} → {last}",
        title="LLM Usage (cumulative)",
    )

    _render_breakdown(
        "By command",
        "command",
        _aggregate(records, lambda r: str(r.get("command") or "?")),
    )
    _render_breakdown(
        "By model",
        "model",
        _aggregate(
            records,
            lambda r: f"{r.get('provider') or '?'}:{r.get('model') or '?'}",
        ),
    )
    _render_recent_runs(records)
