"""`giki lint` -- wiki health check with optional --fix mode.

Checks:
1. Dead wikilinks  (reuses ``check_dead_links`` from ``review_agent``)
2. Missing frontmatter (pages without ``---`` header)
3. Orphan pages (no inbound links from other pages)
4. Slug violations (filenames not matching ``^[a-z0-9-]+$``)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import typer

from ..console import console, error, info, success, warn


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintFinding:
    severity: str          # "error", "warn"
    slug: str
    message: str
    fixable: bool = False


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _check_dead_links_lint(
    root: Path,
) -> list[LintFinding]:
    """Find dead wikilinks across all pages using the Linker."""
    from ..wiki.linker import Linker
    from ..wiki.parser import ParseError, parse_page
    from ..wiki.store import WikiStore

    findings: list[LintFinding] = []
    store = WikiStore(root)

    # Build linker — it also calls all_pages, so guard against parse errors
    try:
        linker = Linker(store)
    except ParseError:
        # If Linker can't build because some pages lack frontmatter,
        # build it manually from parseable pages
        from ..wiki.parser import WikiLink as _WL

        linker = Linker.__new__(Linker)
        linker._store = store
        linker._slugs = set()
        linker._alias_to_slug = {}
        for slug in store.list_pages():
            raw = store.read(slug)
            try:
                page = parse_page(raw)
            except ParseError:
                linker._slugs.add(slug)
                continue
            linker._slugs.add(slug)
            for alias in page.aliases:
                linker._alias_to_slug.setdefault(alias, slug)

    for slug in sorted(store.list_pages()):
        raw = store.read(slug)
        try:
            page = parse_page(raw)
        except ParseError:
            # Skip pages that can't be parsed (missing frontmatter check handles these)
            continue
        dead = linker.dead_links(page, slug)
        for link in dead:
            findings.append(
                LintFinding(
                    severity="error",
                    slug=slug,
                    message=f"broken link [[{link.target}]]",
                    fixable=True,
                )
            )
    return findings


def _check_missing_frontmatter(
    root: Path,
) -> list[LintFinding]:
    """Pages whose raw content doesn't start with ``---``."""
    from ..wiki.store import WikiStore

    findings: list[LintFinding] = []
    store = WikiStore(root)
    for slug in sorted(store.list_pages()):
        raw = store.read(slug)
        if not raw.startswith("---"):
            findings.append(
                LintFinding(
                    severity="error",
                    slug=slug,
                    message="missing frontmatter",
                    fixable=True,
                )
            )
    return findings


def _check_orphan_pages(
    root: Path,
) -> list[LintFinding]:
    """Pages with zero inbound links from other pages."""
    from ..wiki.parser import ParseError, parse_page
    from ..wiki.store import WikiStore

    findings: list[LintFinding] = []
    store = WikiStore(root)

    # Collect all inbound targets
    inbound: dict[str, int] = {slug: 0 for slug in store.list_pages()}
    for slug in store.list_pages():
        raw = store.read(slug)
        try:
            page = parse_page(raw)
        except ParseError:
            continue
        for link in page.links:
            if link.target in inbound and link.target != slug:
                inbound[link.target] += 1

    for slug in sorted(inbound):
        if inbound[slug] == 0:
            findings.append(
                LintFinding(
                    severity="warn",
                    slug=slug,
                    message="orphan page (no inbound links)",
                    fixable=False,
                )
            )
    return findings


def _check_slug_violations(
    root: Path,
) -> list[LintFinding]:
    """Filenames not matching ``^[a-z0-9-]+$``."""
    from ..wiki.store import WikiStore

    findings: list[LintFinding] = []
    store = WikiStore(root)
    wiki_dir = store.wiki_dir
    if not wiki_dir.exists():
        return findings

    for p in sorted(wiki_dir.iterdir()):
        if not p.is_file() or p.suffix != ".md" or p.name.startswith("."):
            continue
        slug = p.stem
        if not _SLUG_RE.match(slug):
            findings.append(
                LintFinding(
                    severity="warn",
                    slug=slug,
                    message=f"slug violates pattern (expected ^[a-z0-9-]+$)",
                    fixable=False,
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Fix helpers
# ---------------------------------------------------------------------------


def _fix_dead_links(
    root: Path,
    dead_link_findings: list[LintFinding],
) -> int:
    """Remove broken ``[[link]]`` from page bodies. Returns count of fixes."""
    from ..wiki.parser import _WIKILINK_RE
    from ..wiki.store import WikiStore

    if not dead_link_findings:
        return 0

    store = WikiStore(root)
    # Group findings by slug and collect broken targets per page
    broken_by_slug: dict[str, set[str]] = {}
    for f in dead_link_findings:
        broken_by_slug.setdefault(f.slug, set()).add(
            # Extract target from message "broken link [[target]]"
            f.message.split("[[")[1].split("]]")[0]
        )

    fixed = 0
    for slug, targets in broken_by_slug.items():
        if not store.exists(slug):
            continue
        raw = store.read(slug)
        new_raw = raw
        for target in targets:
            # Remove [[target]], [[target|display]], [[type::target]], [[type::target|display]]
            pattern = re.compile(
                r"\[\[(?:[a-z][a-z_-]*::)?" + re.escape(target) + r"(?:\|[^\[\]]+?)?\]\]"
            )
            new_raw = pattern.sub("", new_raw)
        if new_raw != raw:
            store.write(slug, new_raw)
            fixed += len(targets)

    return fixed


def _fix_missing_frontmatter(
    root: Path,
    fm_findings: list[LintFinding],
) -> int:
    """Add minimal frontmatter to pages that lack it. Returns count of fixes."""
    from ..wiki.store import WikiStore

    if not fm_findings:
        return 0

    store = WikiStore(root)
    now = datetime.now(timezone.utc).isoformat()
    fixed = 0

    for f in fm_findings:
        if not store.exists(f.slug):
            continue
        raw = store.read(f.slug)
        if raw.startswith("---"):
            # Already has frontmatter (maybe added between check and fix)
            continue
        # Build minimal frontmatter with title=slug
        fm = (
            "---\n"
            f"title: {f.slug}\n"
            f"created: {now}\n"
            f"updated: {now}\n"
            "aliases: []\n"
            "tags: []\n"
            "sources: []\n"
            "---\n"
        )
        store.write(f.slug, fm + raw)
        fixed += 1

    return fixed


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def lint_command(
    fix: bool = typer.Option(False, "--fix", help="Auto-fix what can be fixed."),
    root: Path = typer.Option(Path("."), "--root", help="Wiki project root."),
) -> None:
    """Health check for your wiki: dead links, orphans, frontmatter, slugs."""
    root = root.resolve()
    wiki_dir = root / "wiki"
    if not wiki_dir.exists():
        error(f"wiki/ directory not found at {wiki_dir}")
        raise typer.Exit(code=1)

    # Run all checks
    all_findings: list[LintFinding] = []
    all_findings.extend(_check_dead_links_lint(root))
    all_findings.extend(_check_missing_frontmatter(root))
    all_findings.extend(_check_orphan_pages(root))
    all_findings.extend(_check_slug_violations(root))

    # Print findings
    for f in all_findings:
        prefix = f"[{f.severity}]"
        console.print(f"{prefix} {f.slug}: {f.message}")

    # Summary
    total = len(all_findings)
    fixable = sum(1 for f in all_findings if f.fixable)

    if total == 0:
        success("No issues found.")
        return

    console.print(f"\n{total} issues found ({fixable} fixable)")

    # Apply fixes if requested
    if fix and fixable > 0:
        dead_links = [f for f in all_findings if f.message.startswith("broken link")]
        fm_missing = [f for f in all_findings if f.message == "missing frontmatter"]

        fixed_count = 0
        fixed_count += _fix_dead_links(root, dead_links)
        fixed_count += _fix_missing_frontmatter(root, fm_missing)

        success(f"Fixed {fixed_count} of {total} issues")
