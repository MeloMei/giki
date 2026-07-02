"""Tests for review report formatting."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from giki.review_models import (
    MechanicalFinding,
    ReviewResult,
    SemanticFinding,
    Verdict,
)
from giki.wiki.review_fmt import format_json, format_markdown, post_pr_comment


class TestFormatMarkdown:
    def test_approve_no_findings(self):
        result = ReviewResult(
            verdict=Verdict.APPROVE, findings=[], pages_reviewed=2, pages_skipped=0,
        )
        md = format_markdown(result)
        assert "approve" in md.lower()
        assert "No issues" in md

    def test_blocker_finding_shown(self):
        result = ReviewResult(
            verdict=Verdict.REQUEST_CHANGES,
            findings=[SemanticFinding("R-1", "blocker", "contradicts X", "fix", "page-a")],
            pages_reviewed=1, pages_skipped=0,
        )
        md = format_markdown(result)
        assert "R-1" in md
        assert "page-a" in md

    def test_nit_collapsed_in_details(self):
        result = ReviewResult(
            verdict=Verdict.COMMENT,
            findings=[SemanticFinding("R-5", "nit", "long paragraph", "split", "page-a")],
            pages_reviewed=1, pages_skipped=0,
        )
        md = format_markdown(result, collapse_nits=True)
        assert "<details>" in md

    def test_nit_not_collapsed_when_disabled(self):
        result = ReviewResult(
            verdict=Verdict.COMMENT,
            findings=[SemanticFinding("R-5", "nit", "long paragraph", "split", "page-a")],
            pages_reviewed=1, pages_skipped=0,
        )
        md = format_markdown(result, collapse_nits=False)
        assert "<details>" not in md

    def test_summary_counts(self):
        result = ReviewResult(
            verdict=Verdict.REQUEST_CHANGES,
            findings=[
                SemanticFinding("R-1", "blocker", "bad", "fix", "a"),
                SemanticFinding("R-3", "warn", "style", "fix", "b"),
                SemanticFinding("R-5", "nit", "long", "split", "c"),
            ],
            pages_reviewed=3, pages_skipped=1,
        )
        md = format_markdown(result)
        assert "3 findings" in md

    def test_mechanical_finding_included(self):
        result = ReviewResult(
            verdict=Verdict.REQUEST_CHANGES,
            findings=[MechanicalFinding("dead-link", "blocker", "broken [[x]]", "page-a")],
            pages_reviewed=1, pages_skipped=0,
        )
        md = format_markdown(result)
        assert "dead-link" in md or "broken" in md


class TestFormatJson:
    def test_structure(self):
        result = ReviewResult(
            verdict=Verdict.APPROVE, findings=[], pages_reviewed=2, pages_skipped=0,
        )
        d = format_json(result)
        assert d["verdict"] == "approve"
        assert d["findings"] == []
        assert d["pages_reviewed"] == 2
        assert "summary" in d

    def test_findings_serialized(self):
        result = ReviewResult(
            verdict=Verdict.REQUEST_CHANGES,
            findings=[
                SemanticFinding("R-1", "blocker", "bad", "fix it", "page-a"),
                MechanicalFinding("dead-link", "blocker", "broken", "page-b"),
            ],
            pages_reviewed=2, pages_skipped=0,
        )
        d = format_json(result)
        assert len(d["findings"]) == 2
        assert d["findings"][0]["rule_id"] == "R-1"
        assert d["findings"][1]["rule_id"] == "dead-link"

    def test_json_serializable(self):
        result = ReviewResult(
            verdict=Verdict.COMMENT,
            findings=[SemanticFinding("R-3", "warn", "style", "fix", "page-a")],
            pages_reviewed=1, pages_skipped=0,
        )
        d = format_json(result)
        text = json.dumps(d)
        assert isinstance(text, str)


class TestPostPrComment:
    def test_calls_gh_cli(self):
        with patch("giki.wiki.review_fmt.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            post_pr_comment(42, "Review body here")
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "gh"
            assert "42" in args

    def test_gh_failure_raises(self):
        with patch("giki.wiki.review_fmt.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=1, stdout="", stderr="auth error",
            )
            with pytest.raises(RuntimeError, match="gh"):
                post_pr_comment(1, "body")
