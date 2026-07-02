"""Review orchestration: mechanical checks + semantic review + aggregation.

This module implements the core review pipeline from spec \u00a77.
Mechanical checks (Phase 2) reuse Linker and WikiParser from Plan 1.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..review_models import (
    ChangeType,
    FileChange,
    MechanicalFinding,
    SemanticFinding,
    Verdict,
)
from .linker import Linker
from .parser import ParseError, parse_page
from .relations import is_valid_relation_type
from .store import WikiStore

from ..llm.base import LLMAdapter, Message
from ..llm.prompts import PromptTemplate
from ..utils import extract_json


def check_dead_links(
    wiki_dir: Path, changes: list[FileChange]
) -> list[MechanicalFinding]:
    """Check for broken wikilinks in changed pages and orphaned links from deletions."""
    findings: list[MechanicalFinding] = []
    store = WikiStore(wiki_dir.parent)
    linker = Linker(store)

    for change in changes:
        if change.change_type not in (ChangeType.NEW, ChangeType.UPDATED):
            continue
        slug = change.wiki_slug
        if not slug or not store.exists(slug):
            continue
        page = parse_page(store.read(slug))
        dead = linker.dead_links(page, slug)
        for link in dead:
            findings.append(
                MechanicalFinding(
                    rule_id="dead-link",
                    severity="blocker",
                    message=f"broken link [[{link.target}]] in page '{slug}'",
                    page_slug=slug,
                )
            )

    deleted_slugs = {
        c.wiki_slug
        for c in changes
        if c.change_type == ChangeType.DELETED and c.wiki_slug
    }
    if deleted_slugs:
        for slug, page in store.all_pages():
            if slug in deleted_slugs:
                continue
            for link in page.links:
                if link.target in deleted_slugs:
                    findings.append(
                        MechanicalFinding(
                            rule_id="dead-link",
                            severity="blocker",
                            message=(
                                f"page '{slug}' links to deleted page "
                                f"[[{link.target}]]"
                            ),
                            page_slug=slug,
                        )
                    )

    return findings


def check_frontmatter(
    wiki_dir: Path,
    changes: list[FileChange],
    *,
    slug_pattern: str = r"^[a-z0-9-]+$",
    max_slug_length: int = 80,
) -> list[MechanicalFinding]:
    """Validate frontmatter and slug constraints for NEW/UPDATED pages."""
    findings: list[MechanicalFinding] = []
    slug_re = re.compile(slug_pattern)

    for change in changes:
        if change.change_type not in (ChangeType.NEW, ChangeType.UPDATED):
            continue
        slug = change.wiki_slug
        if not slug:
            continue

        if not slug_re.match(slug):
            findings.append(
                MechanicalFinding(
                    rule_id="R-3",
                    severity="warn",
                    message=f"slug '{slug}' does not match pattern {slug_pattern}",
                    page_slug=slug,
                )
            )
        if len(slug) > max_slug_length:
            findings.append(
                MechanicalFinding(
                    rule_id="R-3",
                    severity="warn",
                    message=(
                        f"slug '{slug}' length {len(slug)} exceeds "
                        f"max {max_slug_length}"
                    ),
                    page_slug=slug,
                )
            )

        page_path = wiki_dir / f"{slug}.md"
        if not page_path.exists():
            continue
        try:
            parse_page(page_path.read_text(encoding="utf-8"))
        except ParseError as e:
            findings.append(
                MechanicalFinding(
                    rule_id="frontmatter",
                    severity="blocker",
                    message=f"parse error in '{slug}': {e}",
                    page_slug=slug,
                )
            )

    return findings


def check_index_sync(
    changes: list[FileChange], index_text: str
) -> list[MechanicalFinding]:
    """Check that NEW wiki pages appear in index.md content."""
    findings: list[MechanicalFinding] = []
    new_slugs = {
        c.wiki_slug
        for c in changes
        if c.change_type == ChangeType.NEW and c.wiki_slug
    }
    for slug in new_slugs:
        if f"[[{slug}]]" not in index_text:
            findings.append(
                MechanicalFinding(
                    rule_id="index-sync",
                    severity="warn",
                    message=f"new page '{slug}' not found in index.md",
                    page_slug=slug,
                )
            )
    return findings


def check_unrelated_edits(
    changes: list[FileChange], threshold: float
) -> list[MechanicalFinding]:
    """Warn if non-wiki changes exceed the configured threshold ratio."""
    if not changes:
        return []
    wiki_count = sum(
        1
        for c in changes
        if c.path.startswith("wiki/") or c.path.startswith(".giki-state/")
    )
    total = len(changes)
    unrelated_ratio = 1.0 - (wiki_count / total) if total else 0.0
    if unrelated_ratio > threshold:
        return [
            MechanicalFinding(
                rule_id="unrelated-edits",
                severity="warn",
                message=(
                    f"{unrelated_ratio:.0%} of changes are outside wiki/ "
                    f"(threshold: {threshold:.0%})"
                ),
            )
        ]
    return []


def check_typed_links(
    wiki_dir: Path, changes: list[FileChange]
) -> list[MechanicalFinding]:
    """Validate that typed wikilinks use one of the canonical relation types."""
    findings: list[MechanicalFinding] = []

    for change in changes:
        if change.change_type not in (ChangeType.NEW, ChangeType.UPDATED):
            continue
        slug = change.wiki_slug
        if not slug:
            continue

        page_path = wiki_dir / f"{slug}.md"
        if not page_path.exists():
            continue
        try:
            page = parse_page(page_path.read_text(encoding="utf-8"))
        except ParseError:
            continue

        for link in page.links:
            if link.link_type is not None and not is_valid_relation_type(
                link.link_type
            ):
                findings.append(
                    MechanicalFinding(
                        rule_id="MECH-TYPED-LINK",
                        severity="warn",
                        message=(
                            f"unknown link type '{link.link_type}' in "
                            f"[[{link.link_type}::{link.target}]] on page "
                            f"'{slug}'"
                        ),
                        page_slug=slug,
                    )
                )

    return findings

# --- Semantic Review (Phase 3) ---


def render_review_prompt(
    *,
    rules: list,
    page_slug: str,
    page_before: str,
    page_after: str,
    neighbors_summary: str,
    mechanical_findings_text: str,
) -> str:
    """Render the semantic review prompt for one page."""
    if rules:
        rules_text = "\n\n".join(
            f"## {r.anchor} — {r.name} (severity: {r.severity})\n{r.body}"
            for r in rules
        )
    else:
        rules_text = "(no rules configured)"

    before_content = page_before if page_before else "(new page — no prior content)"

    tmpl = PromptTemplate.from_package("review.md")
    return tmpl.render(
        rules_text=rules_text,
        page_slug=page_slug,
        before_content=before_content,
        after_content=page_after,
        neighbors_summary=neighbors_summary or "(none)",
        mechanical_findings_text=mechanical_findings_text or "(none)",
    )


def review_page_semantic(
    *,
    llm: LLMAdapter,
    rules: list,
    page_slug: str,
    page_before: str,
    page_after: str,
    neighbors_summary: str,
    mechanical_findings_text: str,
    is_hand_written: bool = False,
) -> tuple[list[SemanticFinding], str]:
    """Call LLM for semantic review of one page.

    Returns (findings, per_page_verdict).
    Hand-written pages are skipped — returns ([], "approve").
    """
    if is_hand_written:
        return [], "approve"

    prompt = render_review_prompt(
        rules=rules,
        page_slug=page_slug,
        page_before=page_before,
        page_after=page_after,
        neighbors_summary=neighbors_summary,
        mechanical_findings_text=mechanical_findings_text,
    )
    system_prompt = PromptTemplate.from_package("review-system.md").render()
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=prompt),
    ]

    try:
        response = llm.chat(messages)
        data = extract_json(response.text)
    except (ValueError, Exception):
        return [], "comment"

    if not isinstance(data, dict):
        return [], "comment"

    raw_findings = data.get("findings", [])
    findings: list[SemanticFinding] = []
    for f in raw_findings:
        if not isinstance(f, dict):
            continue
        findings.append(
            SemanticFinding(
                rule_id=str(f.get("rule_id", "")),
                severity=str(f.get("severity", "warn")),
                evidence=str(f.get("evidence", "")),
                suggestion=str(f.get("suggestion", "")),
                page_slug=page_slug,
            )
        )

    verdict = str(data.get("verdict", "comment"))
    if verdict not in ("approve", "comment", "request-changes"):
        verdict = "comment"

    return findings, verdict


# --- Aggregation (Phase 4) ---


def aggregate_verdict(
    findings: list[MechanicalFinding | SemanticFinding],
    *,
    severity_blocking: list[str] | None = None,
) -> Verdict:
    """Compute overall verdict from all findings.

    Rules (spec §7 Phase 4):
    - Any finding with severity in severity_blocking → REQUEST_CHANGES
    - No findings at all → APPROVE
    - Otherwise → COMMENT
    """
    if severity_blocking is None:
        severity_blocking = ["blocker"]

    if not findings:
        return Verdict.APPROVE

    for f in findings:
        if f.severity in severity_blocking:
            return Verdict.REQUEST_CHANGES

    return Verdict.COMMENT
