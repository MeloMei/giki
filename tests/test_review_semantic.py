"""Tests for semantic review + verdict aggregation."""

from __future__ import annotations

import json

import pytest

from giki.llm.base import LLMAdapter, LLMResponse, Message
from giki.review_models import (
    MechanicalFinding,
    Rule,
    SemanticFinding,
    Verdict,
)
from giki.wiki.review_agent import (
    aggregate_verdict,
    render_review_prompt,
    review_page_semantic,
)


class FakeLLM(LLMAdapter):
    provider = "fake"
    model = "fake-m"
    name = "fake:fake-m"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        self.calls.append(list(messages))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return LLMResponse(text=r, finish_reason="stop")


class TestRenderReviewPrompt:
    def test_renders_all_variables(self):
        rules = [Rule("R-1", "test-rule", "blocker", "Body text.")]
        prompt = render_review_prompt(
            rules=rules,
            page_slug="test-page",
            page_before="",
            page_after="# Test\n\nNew content.\n",
            neighbors_summary="- [[other]] — Other Page",
            mechanical_findings_text="(none)",
        )
        assert "R-1" in prompt
        assert "test-page" in prompt
        assert "New content" in prompt

    def test_before_content_for_updates(self):
        prompt = render_review_prompt(
            rules=[],
            page_slug="updated-page",
            page_before="# Old\n\nOld content.\n",
            page_after="# New\n\nNew content.\n",
            neighbors_summary="(none)",
            mechanical_findings_text="(none)",
        )
        assert "Old content" in prompt
        assert "New content" in prompt

    def test_empty_before_shows_new_page(self):
        prompt = render_review_prompt(
            rules=[],
            page_slug="new-page",
            page_before="",
            page_after="# New\n\nContent.\n",
            neighbors_summary="(none)",
            mechanical_findings_text="(none)",
        )
        assert "(new page" in prompt


class TestReviewPageSemantic:
    def test_parse_llm_findings(self):
        response_text = json.dumps({
            "findings": [
                {
                    "rule_id": "R-1",
                    "severity": "warn",
                    "evidence": "claim X is unsupported",
                    "suggestion": "add citation",
                }
            ],
            "verdict": "comment",
        })
        llm = FakeLLM([response_text])
        rules = [Rule("R-1", "test", "warn", "body")]
        findings, verdict = review_page_semantic(
            llm=llm,
            rules=rules,
            page_slug="test-page",
            page_before="",
            page_after="# Test\n\nBody.\n",
            neighbors_summary="(none)",
            mechanical_findings_text="(none)",
        )
        assert len(findings) == 1
        assert findings[0].rule_id == "R-1"
        assert findings[0].page_slug == "test-page"
        assert verdict == "comment"

    def test_no_findings_returns_approve(self):
        response_text = json.dumps({"findings": [], "verdict": "approve"})
        llm = FakeLLM([response_text])
        findings, verdict = review_page_semantic(
            llm=llm, rules=[], page_slug="ok",
            page_before="", page_after="# OK\n",
            neighbors_summary="(none)", mechanical_findings_text="(none)",
        )
        assert findings == []
        assert verdict == "approve"

    def test_hand_written_page_skipped(self):
        llm = FakeLLM([])
        findings, verdict = review_page_semantic(
            llm=llm, rules=[], page_slug="notes",
            page_before="", page_after="# Notes\n\nPersonal notes.\n",
            neighbors_summary="(none)", mechanical_findings_text="(none)",
            is_hand_written=True,
        )
        assert findings == []
        assert verdict == "approve"
        assert len(llm.calls) == 0

    def test_malformed_json_returns_comment(self):
        llm = FakeLLM(["this is not json at all"])
        findings, verdict = review_page_semantic(
            llm=llm, rules=[], page_slug="test",
            page_before="", page_after="# Test\n",
            neighbors_summary="(none)", mechanical_findings_text="(none)",
        )
        assert verdict == "comment"


class TestAggregateVerdict:
    def test_no_findings_approve(self):
        assert aggregate_verdict([], severity_blocking=["blocker"]) == Verdict.APPROVE

    def test_blocker_request_changes(self):
        findings = [SemanticFinding("R-1", "blocker", "bad", "fix it", "page-a")]
        assert aggregate_verdict(findings, severity_blocking=["blocker"]) == Verdict.REQUEST_CHANGES

    def test_warn_only_comment(self):
        findings = [SemanticFinding("R-3", "warn", "style", "fix", "page-a")]
        assert aggregate_verdict(findings, severity_blocking=["blocker"]) == Verdict.COMMENT

    def test_nit_only_comment(self):
        findings = [SemanticFinding("R-5", "nit", "long para", "split", "page-a")]
        assert aggregate_verdict(findings, severity_blocking=["blocker"]) == Verdict.COMMENT

    def test_custom_blocking(self):
        findings = [SemanticFinding("R-3", "warn", "bad style", "fix", "page-a")]
        assert aggregate_verdict(findings, severity_blocking=["blocker", "warn"]) == Verdict.REQUEST_CHANGES

    def test_mechanical_blocker_counts(self):
        findings = [MechanicalFinding("dead-link", "blocker", "broken [[x]]", "page-a")]
        assert aggregate_verdict(findings, severity_blocking=["blocker"]) == Verdict.REQUEST_CHANGES

    def test_mixed_blocker_wins(self):
        findings: list = [
            SemanticFinding("R-5", "nit", "long", "split", "page-a"),
            MechanicalFinding("dead-link", "blocker", "broken", "page-b"),
            SemanticFinding("R-3", "warn", "style", "fix", "page-c"),
        ]
        assert aggregate_verdict(findings, severity_blocking=["blocker"]) == Verdict.REQUEST_CHANGES
