"""Tests for cross-page analysis and neighbor summarization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from giki.llm.base import LLMAdapter, LLMResponse, Message
from giki.review_models import MechanicalFinding, SemanticFinding
from giki.wiki.review_agent import cross_page_analysis, summarize_neighbors


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_PAGE = """\
---
title: Test Page
aliases: []
tags: [test]
created: 2026-01-01T00:00:00+00:00
updated: 2026-01-01T00:00:00+00:00
sources:
  - path: src.md
    ingested_at: 2026-01-01T00:00:00+00:00
---

This is the body of the test page.

## Related

See [[other-page]] for more details.
Also check [[third-page]].
"""

_OTHER_PAGE = """\
---
title: Other Page
aliases: []
tags: [related]
created: 2026-01-01T00:00:00+00:00
updated: 2026-01-01T00:00:00+00:00
sources:
  - path: other.md
    ingested_at: 2026-01-01T00:00:00+00:00
---

This page covers a related topic with some details.
"""

_THIRD_PAGE = """\
---
title: Third Page
aliases: []
tags: []
created: 2026-01-01T00:00:00+00:00
updated: 2026-01-01T00:00:00+00:00
sources:
  - path: third.md
    ingested_at: 2026-01-01T00:00:00+00:00
---

A third page with additional context.
"""


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


def _make_wiki(tmp_path: Path, pages: dict[str, str]) -> Path:
    """Create wiki/ dir with given pages."""
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(exist_ok=True)
    for slug, content in pages.items():
        (wiki_dir / f"{slug}.md").write_text(content, encoding="utf-8")
    return wiki_dir


# ---------------------------------------------------------------------------
# summarize_neighbors
# ---------------------------------------------------------------------------


class TestSummarizeNeighbors:
    def test_returns_empty_for_missing_page(self, tmp_path: Path) -> None:
        wiki_dir = _make_wiki(tmp_path, {})
        assert summarize_neighbors(wiki_dir, "nonexistent") == ""

    def test_returns_empty_for_unparseable_page(self, tmp_path: Path) -> None:
        wiki_dir = _make_wiki(tmp_path, {"bad": "no frontmatter here"})
        assert summarize_neighbors(wiki_dir, "bad") == ""

    def test_summarizes_linked_pages(self, tmp_path: Path) -> None:
        wiki_dir = _make_wiki(tmp_path, {
            "test-page": _SAMPLE_PAGE,
            "other-page": _OTHER_PAGE,
            "third-page": _THIRD_PAGE,
        })
        result = summarize_neighbors(wiki_dir, "test-page")
        assert "Other Page" in result
        assert "[[other-page]]" in result
        assert "Third Page" in result
        assert "[[third-page]]" in result

    def test_skips_missing_linked_pages(self, tmp_path: Path) -> None:
        wiki_dir = _make_wiki(tmp_path, {
            "test-page": _SAMPLE_PAGE,
            # other-page and third-page are missing
        })
        result = summarize_neighbors(wiki_dir, "test-page")
        # Should return empty since no linked pages exist
        assert result == ""

    def test_respects_max_pages_limit(self, tmp_path: Path) -> None:
        wiki_dir = _make_wiki(tmp_path, {
            "test-page": _SAMPLE_PAGE,
            "other-page": _OTHER_PAGE,
            "third-page": _THIRD_PAGE,
        })
        result = summarize_neighbors(wiki_dir, "test-page", max_pages=1)
        # Should only include one neighbor
        count = result.count("### ")
        assert count == 1


# ---------------------------------------------------------------------------
# cross_page_analysis
# ---------------------------------------------------------------------------


class TestCrossPageAnalysis:
    def test_returns_empty_for_single_page(self) -> None:
        llm = FakeLLM([])
        result = cross_page_analysis(
            llm=llm,
            pages=[("page-a", "content")],
            rules=[],
        )
        assert result == []
        assert len(llm.calls) == 0

    def test_detects_contradiction(self) -> None:
        response = json.dumps({
            "findings": [{
                "rule_id": "cross-contradiction",
                "severity": "blocker",
                "evidence": "Page A says Python 3.8 is EOL, page B says it's supported",
                "suggestion": "Reconcile the Python version claims",
                "page_slug": "page-a",
            }]
        })
        llm = FakeLLM([response])
        result = cross_page_analysis(
            llm=llm,
            pages=[
                ("page-a", "Python 3.8 reached end-of-life in October 2024."),
                ("page-b", "Python 3.8 is still actively supported."),
            ],
            rules=[],
        )
        assert len(result) == 1
        assert result[0].rule_id == "cross-contradiction"
        assert result[0].severity == "blocker"
        assert result[0].page_slug == "page-a"

    def test_detects_overlap(self) -> None:
        response = json.dumps({
            "findings": [{
                "rule_id": "cross-overlap",
                "severity": "warn",
                "evidence": "Both pages cover the same topic with 80% overlap",
                "suggestion": "Consider merging into one page",
                "page_slug": "page-a",
            }]
        })
        llm = FakeLLM([response])
        result = cross_page_analysis(
            llm=llm,
            pages=[
                ("page-a", "Design patterns: Observer pattern implementation guide."),
                ("page-b", "Design patterns: How to implement the Observer pattern."),
            ],
            rules=[],
        )
        assert len(result) == 1
        assert result[0].rule_id == "cross-overlap"
        assert result[0].severity == "warn"

    def test_returns_empty_when_no_issues(self) -> None:
        response = json.dumps({"findings": []})
        llm = FakeLLM([response])
        result = cross_page_analysis(
            llm=llm,
            pages=[
                ("page-a", "Content about topic A."),
                ("page-b", "Content about topic B."),
            ],
            rules=[],
        )
        assert result == []

    def test_handles_llm_error_gracefully(self) -> None:
        llm = FakeLLM([RuntimeError("API down")])
        result = cross_page_analysis(
            llm=llm,
            pages=[
                ("page-a", "Content A."),
                ("page-b", "Content B."),
            ],
            rules=[],
        )
        assert result == []

    def test_handles_invalid_json_gracefully(self) -> None:
        llm = FakeLLM(["not valid json at all"])
        result = cross_page_analysis(
            llm=llm,
            pages=[
                ("page-a", "Content A."),
                ("page-b", "Content B."),
            ],
            rules=[],
        )
        assert result == []

    def test_includes_rules_in_prompt(self) -> None:
        from giki.review_models import Rule
        rules = [Rule("R-1", "no-contradictions", "blocker", "Pages must not contradict.")]
        response = json.dumps({"findings": []})
        llm = FakeLLM([response])
        cross_page_analysis(
            llm=llm,
            pages=[
                ("page-a", "A"),
                ("page-b", "B"),
            ],
            rules=rules,
        )
        user_msg = llm.calls[0][1].content
        assert "R-1" in user_msg
        assert "no-contradictions" in user_msg


# ---------------------------------------------------------------------------
# finding_type property
# ---------------------------------------------------------------------------


class TestFindingType:
    def test_mechanical_finding_type(self) -> None:
        f = MechanicalFinding(rule_id="dead-link", severity="blocker", message="broken")
        assert f.finding_type == "mechanical"

    def test_semantic_finding_type(self) -> None:
        f = SemanticFinding(
            rule_id="R-1", severity="warn",
            evidence="issue", suggestion="fix",
        )
        assert f.finding_type == "semantic"
