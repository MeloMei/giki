"""Format review results as markdown or JSON; post to GitHub PRs."""

from __future__ import annotations

import subprocess
from typing import Any

from ..review_models import (
    MechanicalFinding,
    ReviewResult,
    SemanticFinding,
    Verdict,
)


def format_markdown(
    result: ReviewResult, *, collapse_nits: bool = True
) -> str:
    """Render a review result as human-readable markdown."""
    if not result.findings:
        skipped_note = f", {result.pages_skipped} skipped" if result.pages_skipped else ""
        return (
            f"## giki review: approve\n\n"
            f"No issues found. {result.pages_reviewed} pages reviewed{skipped_note}.\n"
        )

    verdict_label = {
        Verdict.APPROVE: "approve",
        Verdict.COMMENT: "comment",
        Verdict.REQUEST_CHANGES: "request-changes",
    }.get(result.verdict, str(result.verdict.value))

    lines = [f"## giki review: {verdict_label}\n"]

    counts: dict[str, int] = {}
    for f in result.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    total = len(result.findings)
    parts = []
    for sev in ("blocker", "warn", "nit"):
        if sev in counts:
            label = sev if counts[sev] == 1 else sev + "s"
            parts.append(f"{counts[sev]} {label}")
    summary = f"**{total} findings** ({', '.join(parts)})"
    summary += f" across {result.pages_reviewed} pages reviewed"
    if result.pages_skipped:
        summary += f", {result.pages_skipped} skipped"
    lines.append(summary + "\n")

    blockers_and_warns: list = []
    nits: list = []
    for f in result.findings:
        if f.severity == "nit":
            nits.append(f)
        else:
            blockers_and_warns.append(f)

    for f in blockers_and_warns:
        lines.append(_format_finding_md(f))

    if nits:
        if collapse_nits:
            lines.append(f"\n<details>\n<summary>{len(nits)} nit finding(s)</summary>\n")
            for f in nits:
                lines.append(_format_finding_md(f))
            lines.append("</details>\n")
        else:
            for f in nits:
                lines.append(_format_finding_md(f))

    return "\n".join(lines)


def _format_finding_md(f: MechanicalFinding | SemanticFinding) -> str:
    sev_icon = {"blocker": "[blocker]", "warn": "[warn]", "nit": "[nit]"}.get(f.severity, "[?]")
    page_ref = f" `{f.page_slug}`" if f.page_slug else ""
    if isinstance(f, SemanticFinding):
        evidence = f.evidence
        suggestion = f"\n  - **Suggestion:** {f.suggestion}" if f.suggestion else ""
    else:
        evidence = f.message
        suggestion = ""
    return f"- {sev_icon} **[{f.severity}]** {f.rule_id}{page_ref}: {evidence}{suggestion}"


def format_json(result: ReviewResult) -> dict[str, Any]:
    """Render a review result as a JSON-serializable dict."""

    def _finding_to_dict(f: MechanicalFinding | SemanticFinding) -> dict:
        d: dict[str, Any] = {
            "rule_id": f.rule_id,
            "severity": f.severity,
            "page_slug": f.page_slug,
        }
        if isinstance(f, SemanticFinding):
            d["evidence"] = f.evidence
            d["suggestion"] = f.suggestion
        else:
            d["message"] = f.message
        return d

    counts: dict[str, int] = {}
    for f in result.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    return {
        "verdict": result.verdict.value,
        "findings": [_finding_to_dict(f) for f in result.findings],
        "pages_reviewed": result.pages_reviewed,
        "pages_skipped": result.pages_skipped,
        "summary": {
            "total": len(result.findings),
            "by_severity": counts,
        },
    }


def post_pr_comment(pr_id: int, body: str) -> None:
    """Post review body as a PR comment via ``gh pr comment``.

    Raises RuntimeError on gh CLI failure.
    """
    result = subprocess.run(
        ["gh", "pr", "comment", str(pr_id), "--body", body],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh pr comment failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
