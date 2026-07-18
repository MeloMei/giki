"""`giki usage` — cumulative LLM usage and cost report from the local ledger.

Reads ``.giki-state/usage.jsonl`` (written by ``giki ingest`` and
``giki review``) and renders totals plus per-command, per-model, and
recent-run breakdowns.
"""

from __future__ import annotations

import json as json_module
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich import box
from rich.table import Table

from ..config import load_config
from ..console import console, error, heading, info, print_panel, warn
from ..llm.usage import LEDGER_NAME, estimate_cost, is_local_endpoint, read_ledger


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


def _parse_since(text: str) -> datetime:
    """Parse a ``--since`` value: ISO date/datetime or ``Nd`` (last N days).

    Dates without a time component mean local midnight of that day.
    Raises ``typer.BadParameter`` on unparseable input.
    """
    text = text.strip()
    try:
        if text.endswith("d") and text[:-1].isascii() and text[:-1].isdigit():
            days = int(text[:-1])
            now = datetime.now().astimezone()
            return (now - timedelta(days=days)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        dt = datetime.fromisoformat(text)
    except (ValueError, OverflowError):
        raise typer.BadParameter(
            f"invalid --since value {text!r} (expected YYYY-MM-DD, ISO datetime, or Nd)"
        ) from None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpret naive values as local time
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


def _report(records: list[dict]) -> dict:
    """Build the machine-readable report shared by human and JSON output."""
    total_in = sum(r["input_tokens"] for r in records)
    total_out = sum(r["output_tokens"] for r in records)
    known = [r for r in records if r["cost_usd"] is not None]
    total_cost = sum(r["cost_usd"] for r in known)
    by_command = _aggregate(records, lambda r: str(r.get("command") or "?"))
    by_model = _aggregate(
        records, lambda r: f"{r.get('provider') or '?'}:{r.get('model') or '?'}"
    )
    span = None
    if records:
        first = min(records, key=lambda r: _parse_ts(r.get("ts", ""))).get("ts", "")
        last = max(records, key=lambda r: _parse_ts(r.get("ts", ""))).get("ts", "")
        span = [str(first), str(last)]
    return {
        "total": {
            "calls": len(records),
            "input_tokens": total_in,
            "output_tokens": total_out,
            "cost_usd": total_cost if known else None,
            "partial": len(known) < len(records),
        },
        "by_command": by_command,
        "by_model": by_model,
        "ledger_span": span,
    }


def _jsonable(groups: dict[str, dict]) -> dict[str, dict]:
    """Convert aggregate buckets to a clean JSON shape (cost None when unknown)."""
    return {
        k: {
            "calls": g["calls"],
            "input_tokens": g["tin"],
            "output_tokens": g["tout"],
            "cost_usd": g["cost"] if g["known"] else None,
            "partial": g["partial"],
        }
        for k, g in groups.items()
    }


def _reprice(records: list[dict], pricing: dict | None) -> int:
    """Re-estimate records whose cost was unknown at write time.

    The ledger is the audit snapshot for priced records, but ``null`` costs
    just mean "we didn't know the price back then" — re-pricing them with
    the *current* config (custom ``pricing:`` section, loopback base_url)
    closes the gap without rewriting history. Returns the re-priced count.
    """
    n = 0
    for r in records:
        if r["cost_usd"] is not None:
            continue
        base_url = r.get("base_url")
        if base_url and is_local_endpoint(str(base_url)):
            r["cost_usd"] = 0.0
        else:
            r["cost_usd"] = estimate_cost(
                str(r.get("model") or ""),
                r["input_tokens"],
                r["output_tokens"],
                pricing,
            )
        if r["cost_usd"] is not None:
            n += 1
    return n


def _budget_status(cost: float | None, partial: bool, budget: float) -> dict:
    """Compare the (known) cost against the budget.

    ``exceeded`` compares only known costs — when ``partial`` is True the
    true cost may be higher, which callers must surface as a caveat.
    Comparison happens in the same rounded domain as ``remaining`` so
    float noise (0.1 + 0.2) never flips an exactly-at-budget result.
    """
    known_cost = 0.0 if cost is None else cost
    return {
        "limit": budget,
        "cost": cost,
        "remaining": round(budget - known_cost, 6),
        "exceeded": round(known_cost - budget, 6) > 0,
        "partial": partial,
    }


def usage_command(
    root: Path = typer.Option(
        Path("."), "--root", help="Knowledge base root directory"
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="Only include calls on/after this date (YYYY-MM-DD, ISO datetime, or Nd for last N days). Records with unparseable timestamps are excluded.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output JSON (CI-friendly)"
    ),
    budget: float | None = typer.Option(
        None,
        "--budget",
        help="Budget limit in USD for the selected period; exit code 1 when the estimated cost exceeds it. Only models with known pricing count toward the comparison.",
    ),
) -> None:
    """Show cumulative LLM usage and estimated cost from the local ledger."""
    if budget is not None and budget < 0:
        raise typer.BadParameter("--budget must be >= 0")

    root = root.resolve()
    state_dir = root / ".giki-state"
    records, skipped = read_ledger(state_dir)

    since_dt = _parse_since(since) if since else None
    if since_dt is not None:
        records = [r for r in records if _parse_ts(r.get("ts", "")) >= since_dt]

    # Re-price historical records whose cost was unknown at write time,
    # using the current config's custom pricing (if any). A missing config
    # is fine (CI may persist only .giki-state/); a BROKEN config must be
    # surfaced — silently falling back would hide the user's typo.
    pricing = None
    if (root / ".giki" / "config.yaml").exists():
        try:
            pricing = load_config(root).pricing
        except Exception as e:
            # stderr: keeps --json stdout pure.
            error(f"could not load config for re-pricing: {e}")
    repriced = _reprice(records, pricing)

    if json_output:
        report = _report(records)
        payload = {
            "version": 1,
            "total": report["total"],
            "by_command": _jsonable(report["by_command"]),
            "by_model": _jsonable(report["by_model"]),
            "ledger_span": report["ledger_span"],
            "since": since,
            "since_resolved": since_dt.isoformat() if since_dt else None,
            "skipped_lines": skipped,
            "repriced": repriced,
        }
        if budget is not None:
            payload["budget"] = _budget_status(
                report["total"]["cost_usd"], report["total"]["partial"], budget
            )
        console.print_json(
            json_module.dumps(payload, indent=2, ensure_ascii=False)
        )
        if budget is not None and payload["budget"]["exceeded"]:
            # stderr note for humans reading CI logs; stdout stays pure JSON.
            error(
                f"Budget exceeded: est. cost ${payload['budget']['cost']:.4f} "
                f"> budget ${budget:.2f}"
            )
            raise typer.Exit(code=1)
        return

    if skipped:
        warn(f"skipped {skipped} malformed ledger line(s)")

    if repriced:
        info(f"{repriced} historical record(s) re-priced using current config")

    if not records:
        if since_dt is not None:
            info(f"No LLM usage recorded since {since} (ledger: {state_dir / LEDGER_NAME})")
        else:
            info(f"No LLM usage recorded yet (ledger: {state_dir / LEDGER_NAME})")
        if budget is not None:
            info(f"Budget: $0.0000 of ${budget:.2f} used (0%)")
        return

    report = _report(records)
    total = report["total"]
    first, last = (_fmt_ts(x) for x in report["ledger_span"])

    title = "LLM Usage (cumulative)" if since_dt is None else f"LLM Usage (since {since})"
    print_panel(
        f"{total['calls']} LLM call(s) · {total['input_tokens']:,} tokens in · "
        f"{total['output_tokens']:,} tokens out\n"
        f"estimated total cost: "
        f"{_fmt_cost(total['cost_usd'], total['partial'])}\n"
        f"ledger span: {first} → {last}",
        title=title,
    )

    _render_breakdown("By command", "command", report["by_command"])
    _render_breakdown("By model", "model", report["by_model"])
    _render_recent_runs(records)

    if budget is not None:
        status = _budget_status(total["cost_usd"], total["partial"], budget)
        if status["exceeded"]:
            error(
                f"Budget exceeded: est. cost ${status['cost']:.4f} "
                f"> budget ${budget:.2f}"
            )
        elif status["cost"] is None:
            info(f"Budget: n/a of ${budget:.2f} used (unknown pricing)")
        else:
            pct = (status["cost"] / budget * 100) if budget > 0 else 0.0
            info(f"Budget: ${status['cost']:.4f} of ${budget:.2f} used ({pct:.0f}%)")
        if status["partial"]:
            warn("some models have unknown pricing — the true cost may be higher")
        if status["exceeded"]:
            raise typer.Exit(code=1)
