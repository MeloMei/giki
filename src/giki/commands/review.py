# src/giki/commands/review.py
"""giki review — two-phase PR Review Bot (mechanical + semantic)."""

from __future__ import annotations

import json as json_module
import subprocess as _subprocess
from pathlib import Path

import typer

from ..config import ConfigError, load_config
from ..console import console, error as _error, info, print_panel, warn as _warn
from ..diff import (
    classify_changes,
    get_diff_changes,
    get_pr_diff_changes,
    read_file_at_commit,
)
from ..llm import build_client
from ..llm.base import LLMAdapter
from ..llm.usage import UsageTracker
from ..review_models import (
    ChangeType,
    FileChange,
    MechanicalFinding,
    ReviewResult,
    SemanticFinding,
    Verdict,
)
from ..rules import parse_rules
from ..wiki.parser import parse_page
from ..wiki.review_agent import (
    aggregate_verdict,
    check_dead_links,
    check_frontmatter,
    check_index_sync,
    check_typed_links,
    check_unrelated_edits,
    cross_page_analysis,
    review_page_semantic,
    summarize_neighbors,
)
from ..wiki.review_fmt import format_json, format_markdown, post_pr_comment


def review_command(
    pr: int | None = typer.Option(None, "--pr", help="PR number (via gh CLI)"),
    post: bool = typer.Option(False, "--post", help="Post findings as PR comment"),
    json_output: bool = typer.Option(
        False, "--json", help="Output JSON (CI-friendly)"
    ),
    root: Path = typer.Option(
        Path("."), "--root", help="Knowledge base root directory"
    ),
    base: str = typer.Option("main", "--base", help="Base branch for diff"),
) -> None:
    """Review wiki changes — mechanical checks + LLM semantic review."""
    root = Path(root).resolve()

    # --post requires --pr
    if post and pr is None:
        _error("--post requires --pr <id>")
        raise typer.Exit(code=2)

    # Load config
    try:
        cfg = load_config(root)
    except ConfigError as e:
        _error(str(e))
        raise typer.Exit(code=2)

    # Parse wiki-rules.md (optional — empty rules if missing)
    rules_path = root / "wiki-rules.md"
    try:
        rules = parse_rules(rules_path)
    except (FileNotFoundError, ValueError):
        rules = []

    # Get diff changes
    try:
        if pr is not None:
            changes = get_pr_diff_changes(pr, repo_root=root)
        else:
            changes = get_diff_changes(root, base=base)
    except RuntimeError as e:
        _error(str(e))
        raise typer.Exit(code=2)

    classified = classify_changes(changes)
    wiki_changes = classified["wiki"]

    # Run mechanical checks
    all_findings: list[MechanicalFinding | SemanticFinding] = []
    wiki_dir = root / "wiki"

    all_findings.extend(check_dead_links(wiki_dir, wiki_changes))
    all_findings.extend(
        check_frontmatter(
            wiki_dir,
            wiki_changes,
            slug_pattern=cfg.wiki.enforce_slug_pattern,
            max_slug_length=cfg.wiki.max_slug_length,
        )
    )

    # Index sync check
    index_path = root / "index.md"
    index_text = (
        index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    )
    all_findings.extend(check_index_sync(wiki_changes, index_text))

    # Unrelated edits check
    all_findings.extend(
        check_unrelated_edits(changes, cfg.review.unrelated_edit_threshold)
    )

    # Typed wikilink validation
    all_findings.extend(check_typed_links(wiki_dir, wiki_changes))

    # Semantic review per page
    pages_reviewed = 0
    pages_skipped = 0
    changed_pages: list[tuple[str, str]] = []
    usage = UsageTracker(command="review", pricing=cfg.pricing)
    review_client: LLMAdapter = usage.wrap(lambda: build_client(cfg.llm.review))

    # Build mechanical findings text for prompt
    mech_text = "\n".join(
        f"- [{f.severity}] {f.rule_id}: {f.message}" for f in all_findings
    ) or "(none)"

    # Get base commit for "before" content
    base_commit_result = _subprocess.run(
        ["git", "rev-parse", base],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    base_commit = (
        base_commit_result.stdout.strip()
        if base_commit_result.returncode == 0
        else None
    )

    for change in wiki_changes:
        slug = change.wiki_slug
        if not slug:
            continue
        page_path = wiki_dir / f"{slug}.md"
        if not page_path.exists() and change.change_type != ChangeType.DELETED:
            continue

        # Read "after" content
        after_text = (
            page_path.read_text(encoding="utf-8") if page_path.exists() else ""
        )

        # Read "before" content
        before_text = ""
        if change.change_type == ChangeType.UPDATED and base_commit:
            before_text = read_file_at_commit(root, change.path, base_commit) or ""

        # Check if hand-written (no sources frontmatter)
        is_hand_written = False
        if after_text:
            try:
                page = parse_page(after_text)
                is_hand_written = page.is_hand_written
            except Exception:
                pass

        # Build neighbors context from linked pages
        neighbors = summarize_neighbors(wiki_dir, slug)

        findings, _verdict = review_page_semantic(
            llm=review_client,
            rules=rules,
            page_slug=slug,
            page_before=before_text,
            page_after=after_text,
            neighbors_summary=neighbors,
            mechanical_findings_text=mech_text,
            is_hand_written=is_hand_written,
        )
        all_findings.extend(findings)

        if is_hand_written:
            pages_skipped += 1
        else:
            pages_reviewed += 1

        # Collect page content for cross-page analysis
        if after_text and not is_hand_written:
            changed_pages.append((slug, after_text))

    # Cross-page analysis: contradictions and semantic overlap
    if len(changed_pages) >= 2:
        cross_findings = cross_page_analysis(
            llm=review_client,
            pages=changed_pages,
            rules=rules,
        )
        all_findings.extend(cross_findings)

    # Aggregate verdict
    verdict = aggregate_verdict(
        all_findings, severity_blocking=cfg.review.severity_blocking
    )

    result = ReviewResult(
        verdict=verdict,
        findings=all_findings,
        pages_reviewed=pages_reviewed,
        pages_skipped=pages_skipped,
    )

    # Persist the usage ledger (file side effect; safe in --json mode too).
    # Only when LLM calls were actually made. The ledger is an audit aid —
    # a write failure must not fail the review.
    ledger = None
    ledger_error = None
    if usage.records:
        try:
            ledger = usage.append_ledger(cfg.state_dir)
        except OSError as e:
            ledger_error = str(e)
            _warn(f"could not write usage ledger: {e}")

    # Output
    if json_output:
        data = format_json(result)
        if usage.records:
            data["usage"] = usage.payload(ledger_error)
        console.print_json(
            json_module.dumps(data, indent=2, ensure_ascii=False)
        )
    else:
        # Show verdict header
        verdict_style = {
            "approve": "green",
            "comment": "yellow",
            "request-changes": "red",
        }.get(result.verdict.value, "white")
        verdict_icon = {
            "approve": "[green]✓ APPROVE[/green]",
            "comment": "[yellow]○ COMMENT[/yellow]",
            "request-changes": "[red]✗ REQUEST CHANGES[/red]",
        }.get(result.verdict.value, result.verdict.value)

        stats = f"{result.pages_reviewed} page(s) reviewed"
        if result.pages_skipped:
            stats += f", {result.pages_skipped} skipped (hand-written)"

        print_panel(
            f"{verdict_icon}\n\n{stats}",
            title="Review Verdict",
            style=verdict_style,
        )

        # Mechanical findings summary
        mech_count = len([f for f in result.findings if f.finding_type == "mechanical"])
        sem_count = len([f for f in result.findings if f.finding_type == "semantic"])
        if result.findings:
            console.print(f"\n[bold]{len(result.findings)} finding(s)[/bold] "
                          f"([dim]{mech_count} mechanical, {sem_count} semantic[/dim])\n")

        # Detailed output
        md = format_markdown(result, collapse_nits=cfg.review.pr_comment_collapse)
        console.print(md)

        # LLM usage panel
        if usage.records:
            lines = usage.summary_lines()
            if ledger is not None:
                lines.append(f"ledger: {ledger.relative_to(root)}")
            print_panel("\n".join(lines), title="LLM Usage")

    # Post to PR
    if post and pr is not None:
        md = format_markdown(result, collapse_nits=cfg.review.pr_comment_collapse)
        try:
            post_pr_comment(pr, md)
            info(f"Posted review to PR #{pr}")
        except RuntimeError as e:
            _error(str(e))

    raise typer.Exit(code=verdict.exit_code)
