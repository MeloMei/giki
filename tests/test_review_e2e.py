"""End-to-end tests for the giki review pipeline.

Uses FakeLLM (from Plan 1 pattern) to exercise the full review pipeline
without real LLM API calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import git
import pytest

from giki.config import load_config
from giki.llm.base import LLMAdapter, LLMResponse, Message
from giki.review_models import ChangeType, FileChange, ReviewResult, Verdict
from giki.rules import parse_rules
from giki.wiki.review_agent import (
    aggregate_verdict,
    check_dead_links,
    check_frontmatter,
    review_page_semantic,
)
from giki.wiki.review_fmt import format_json, format_markdown


_CFG_YAML = """
llm:
  compile:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
  review:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
review:
  unrelated_edit_threshold: 0.30
  severity_blocking: [blocker]
  pr_comment_collapse: true
"""


class FakeLLM(LLMAdapter):
    provider = "fake"
    model = "fake-m"
    name = "fake:fake-m"

    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.calls = []

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        self.calls.append(list(messages))
        if self._responses:
            r = self._responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return LLMResponse(text=r, finish_reason="stop")
        return LLMResponse(
            text=json.dumps({"findings": [], "verdict": "approve"}),
            finish_reason="stop",
        )


def _init_review_kb(tmp_path):
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.co").release()

    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(_CFG_YAML, encoding="utf-8")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki-rules.md").write_text(
        "# Rules\n\n## R-1\n\n**test** — severity: `blocker`\n\nBody.\n",
        encoding="utf-8",
    )
    (tmp_path / "index.md").write_text(
        "# Index\n\n<!-- giki:index-begin -->\n"
        "## Uncategorized\n- [[existing-page]] — Existing\n"
        "<!-- giki:index-end -->\n",
        encoding="utf-8",
    )

    existing = (
        "---\ntitle: Existing\ncreated: 2026-01-01T00:00:00+00:00\n"
        "updated: 2026-01-01T00:00:00+00:00\nsources:\n  - path: s.md\n"
        "---\n\nOriginal content.\n"
    )
    (tmp_path / "wiki" / "existing-page.md").write_text(existing, encoding="utf-8")

    repo.index.add([
        ".giki/config.yaml", "wiki-rules.md", "index.md", "wiki/existing-page.md",
    ])
    repo.index.commit("initial")

    return load_config(tmp_path)


class TestReviewE2E:
    def test_full_pipeline_approve(self, tmp_path):
        cfg = _init_review_kb(tmp_path)

        new_page = (
            "---\ntitle: New\ncreated: 2026-01-02T00:00:00+00:00\n"
            "updated: 2026-01-02T00:00:00+00:00\nsources:\n  - path: s2.md\n"
            "---\n\nNew content about [[existing-page]].\n"
        )
        (tmp_path / "wiki" / "new-page.md").write_text(new_page, encoding="utf-8")

        changes = [FileChange("wiki/new-page.md", ChangeType.NEW)]

        # Mechanical
        mech = check_dead_links(tmp_path / "wiki", changes)
        mech.extend(check_frontmatter(tmp_path / "wiki", changes))
        assert all(f.severity != "blocker" for f in mech)

        # Semantic
        llm = FakeLLM([json.dumps({"findings": [], "verdict": "approve"})])
        rules = parse_rules(tmp_path / "wiki-rules.md")
        findings, verdict = review_page_semantic(
            llm=llm,
            rules=rules,
            page_slug="new-page",
            page_before="",
            page_after=new_page,
            neighbors_summary="- [[existing-page]] — Existing",
            mechanical_findings_text="(none)",
        )
        assert verdict == "approve"

        # Aggregate
        all_findings = list(mech) + list(findings)
        overall = aggregate_verdict(all_findings, severity_blocking=["blocker"])
        assert overall == Verdict.APPROVE

        # Format
        result = ReviewResult(
            verdict=overall, findings=all_findings,
            pages_reviewed=1, pages_skipped=0,
        )
        md = format_markdown(result)
        assert "approve" in md.lower()

    def test_dead_link_triggers_request_changes(self, tmp_path):
        _init_review_kb(tmp_path)

        bad_page = (
            "---\ntitle: Bad\ncreated: 2026-01-02T00:00:00+00:00\n"
            "updated: 2026-01-02T00:00:00+00:00\nsources:\n  - path: s2.md\n"
            "---\n\nSee [[nonexistent-page]].\n"
        )
        (tmp_path / "wiki" / "bad-page.md").write_text(bad_page, encoding="utf-8")

        changes = [FileChange("wiki/bad-page.md", ChangeType.NEW)]
        mech = check_dead_links(tmp_path / "wiki", changes)
        assert any(f.severity == "blocker" for f in mech)

        overall = aggregate_verdict(mech, severity_blocking=["blocker"])
        assert overall == Verdict.REQUEST_CHANGES

    def test_format_roundtrip(self):
        """format_json output is JSON-serializable and contains expected keys."""
        from giki.review_models import SemanticFinding

        result = ReviewResult(
            verdict=Verdict.COMMENT,
            findings=[
                SemanticFinding("R-3", "warn", "style issue", "fix it", "page-a"),
            ],
            pages_reviewed=1,
            pages_skipped=0,
        )
        d = format_json(result)
        text = json.dumps(d)
        parsed = json.loads(text)
        assert parsed["verdict"] == "comment"
        assert len(parsed["findings"]) == 1
