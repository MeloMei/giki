"""`giki decay` — knowledge decay report for the whole wiki.

Scans every page for time-sensitive signals (version references,
time-relative phrases, page age), then asks the LLM to judge which claims
may have gone stale. Prints a risk-sorted report. This is a report, not a
gate: findings never affect the exit code (only environment errors like a
missing wiki/ directory or broken config exit non-zero).
"""

from __future__ import annotations

import json as json_module
from dataclasses import asdict
from pathlib import Path

import typer

from ..config import ConfigError, load_config
from ..console import console, error, info, print_panel, warn
from ..llm import build_client
from ..llm.usage import UsageTracker
from ..wiki.decay import (
    DecayAssessment,
    assess_page_decay,
    extract_signals,
    page_age_days,
    risk_sort_key,
)
from ..wiki.parser import ParseError, parse_page
from ..wiki.store import WikiStore, WikiStoreError

_RISK_ICON = {
    "high": "[red]HIGH[/red]",
    "medium": "[yellow]MEDIUM[/yellow]",
    "low": "[green]LOW[/green]",
    "unknown": "[dim]UNKNOWN[/dim]",
}

# Pages this old are suspicious on their own, even without textual signals.
_AGE_ANCHOR_DAYS = 180


def decay_command(
    root: Path = typer.Option(
        Path("."), "--root", help="Knowledge base root directory"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output JSON (CI-friendly)"
    ),
    max_pages: int = typer.Option(
        20, "--max-pages", min=0,
        help="Max pages to assess with the LLM (cost control)",
    ),
    min_age_days: int = typer.Option(
        0, "--min-age-days", help="Only assess pages older than this"
    ),
    all_pages: bool = typer.Option(
        False, "--all", help="Assess pages even without time-sensitive signals"
    ),
) -> None:
    """Report wiki pages whose claims may have gone stale."""
    root = root.resolve()
    wiki_dir = root / "wiki"
    if not wiki_dir.exists():
        error(f"wiki/ directory not found at {wiki_dir}")
        raise typer.Exit(code=1)

    try:
        cfg = load_config(root)
    except ConfigError as e:
        error(str(e))
        raise typer.Exit(code=1)

    store = WikiStore(root)

    # Mechanical pass: collect candidate pages with their signals.
    # One bad page (invalid filename, unreadable file, broken frontmatter)
    # must never crash the report.
    candidates: list[tuple[str, str, str, int | None, list[str]]] = []
    skipped_no_signals = 0
    skipped_unparseable = 0
    for slug in sorted(store.list_pages()):
        try:
            raw = store.read(slug)
            page = parse_page(raw)
        except (WikiStoreError, ParseError, OSError, UnicodeDecodeError):
            skipped_unparseable += 1
            continue
        age = page_age_days(page.updated)
        if age is not None and age < min_age_days:
            continue
        signals = extract_signals(page.body)
        anchored = bool(signals) or (age is not None and age >= _AGE_ANCHOR_DAYS)
        if not anchored and not all_pages:
            skipped_no_signals += 1
            continue
        candidates.append((slug, page.title, page.body, age, signals))

    # Rank candidates BEFORE truncating: oldest pages first, then most
    # signals — the LLM budget goes to the likeliest decay, not to
    # alphabetical order.
    candidates.sort(key=lambda c: (c[3] is None, -(c[3] or 0), -len(c[4])))

    if not candidates:
        if json_output:
            console.print_json(json_module.dumps({
                "pages_assessed": 0,
                "pages_skipped_no_signals": skipped_no_signals,
                "pages_skipped_unparseable": skipped_unparseable,
                "assessments": [],
            }, indent=2, ensure_ascii=False))
            return
        info("No pages with time-sensitive signals found — nothing to assess. "
             "(run with --all to assess every page)")
        if skipped_unparseable:
            warn(f"{skipped_unparseable} page(s) skipped (unparseable)")
        return

    # LLM pass (usage-tracked, like ingest/review).
    usage = UsageTracker(command="decay", pricing=cfg.pricing)
    client = usage.wrap(lambda: build_client(cfg.llm.review))

    assessments: list[DecayAssessment] = []
    for slug, title, body, age, signals in candidates[: max(0, max_pages)]:
        assessments.append(
            assess_page_decay(
                llm=client,
                slug=slug,
                title=title,
                body=body,
                age_days=age,
                signals=signals,
            )
        )
    assessments.sort(key=risk_sort_key)

    # Persist the usage ledger (audit aid; failure must not fail the report).
    ledger = None
    ledger_error = None
    if usage.records:
        try:
            ledger = usage.append_ledger(cfg.state_dir)
        except OSError as e:
            ledger_error = str(e)
            warn(f"could not write usage ledger: {e}")

    if json_output:
        payload = {
            "pages_assessed": len(assessments),
            "pages_skipped_no_signals": skipped_no_signals,
            "pages_skipped_unparseable": skipped_unparseable,
            "assessments": [asdict(a) for a in assessments],
        }
        if usage.records:
            payload["usage"] = usage.payload(ledger_error)
        console.print_json(json_module.dumps(payload, indent=2, ensure_ascii=False))
        return

    # Human report.
    high = sum(1 for a in assessments if a.risk == "high")
    medium = sum(1 for a in assessments if a.risk == "medium")
    stats = (
        f"{len(assessments)} page(s) assessed · {high} high · {medium} medium risk"
    )
    if skipped_no_signals:
        stats += f"\n{skipped_no_signals} page(s) skipped (no time-sensitive signals)"
    if skipped_unparseable:
        stats += f"\n{skipped_unparseable} page(s) skipped (unparseable)"
    if len(candidates) > max_pages:
        stats += f"\n{len(candidates) - max_pages} page(s) not assessed (--max-pages)"
    style = "red" if high else ("yellow" if medium else "green")
    print_panel(stats, title="Knowledge Decay Report", style=style)

    for a in assessments:
        if a.risk in ("low", "unknown") and not a.stale_claims:
            continue
        icon = _RISK_ICON.get(a.risk, a.risk)
        age_text = f"{a.age_days}d old" if a.age_days is not None else "age unknown"
        console.print(f"\n{icon} [bold]{a.slug}[/bold] [dim]({age_text})[/dim]")
        for c in a.stale_claims:
            console.print(f"  · {c.claim}")
            console.print(f"    [dim]reason: {c.reason}[/dim]")
            if c.suggestion:
                console.print(f"    [dim]fix: {c.suggestion}[/dim]")

    if usage.records:
        lines = usage.summary_lines()
        if ledger is not None:
            lines.append(f"ledger: {ledger.relative_to(root)}")
        print_panel("\n".join(lines), title="LLM Usage")
