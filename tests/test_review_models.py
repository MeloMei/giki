"""Tests for review data models."""

from __future__ import annotations

import pytest

from giki.review_models import (
    ChangeType,
    FileChange,
    MechanicalFinding,
    ReviewResult,
    Rule,
    SemanticFinding,
    Verdict,
)


class TestChangeType:
    def test_values(self):
        assert ChangeType.NEW.value == "new"
        assert ChangeType.UPDATED.value == "updated"
        assert ChangeType.DELETED.value == "deleted"
        assert ChangeType.RENAMED.value == "renamed"


class TestVerdict:
    def test_values(self):
        assert Verdict.APPROVE.value == "approve"
        assert Verdict.COMMENT.value == "comment"
        assert Verdict.REQUEST_CHANGES.value == "request-changes"

    def test_exit_codes(self):
        assert Verdict.APPROVE.exit_code == 0
        assert Verdict.COMMENT.exit_code == 0
        assert Verdict.REQUEST_CHANGES.exit_code == 1


class TestRule:
    def test_construction(self):
        r = Rule(anchor="R-1", name="test", severity="blocker", body="body text")
        assert r.anchor == "R-1"
        assert r.name == "test"
        assert r.severity == "blocker"
        assert r.body == "body text"


class TestFileChange:
    def test_wiki_slug_from_wiki_path(self):
        fc = FileChange(path="wiki/observer-pattern.md", change_type=ChangeType.NEW)
        assert fc.wiki_slug == "observer-pattern"

    def test_wiki_slug_none_for_non_wiki(self):
        fc = FileChange(path="index.md", change_type=ChangeType.UPDATED)
        assert fc.wiki_slug is None

    def test_wiki_slug_none_for_sources(self):
        fc = FileChange(path="sources/notes.md", change_type=ChangeType.NEW)
        assert fc.wiki_slug is None

    def test_old_path_for_rename(self):
        fc = FileChange(
            path="wiki/new-slug.md",
            change_type=ChangeType.RENAMED,
            old_path="wiki/old-slug.md",
        )
        assert fc.old_path == "wiki/old-slug.md"

    def test_old_path_default_none(self):
        fc = FileChange(path="wiki/x.md", change_type=ChangeType.NEW)
        assert fc.old_path is None


class TestMechanicalFinding:
    def test_to_semantic(self):
        mf = MechanicalFinding(
            rule_id="R-2",
            severity="blocker",
            message="broken link to [[missing]]",
            page_slug="test-page",
        )
        sf = mf.to_semantic()
        assert isinstance(sf, SemanticFinding)
        assert sf.rule_id == "R-2"
        assert sf.severity == "blocker"
        assert sf.evidence == "broken link to [[missing]]"
        assert sf.page_slug == "test-page"
        assert sf.suggestion == ""


class TestReviewResult:
    def test_construction(self):
        result = ReviewResult(
            verdict=Verdict.APPROVE,
            findings=[],
            pages_reviewed=3,
            pages_skipped=1,
        )
        assert result.verdict == Verdict.APPROVE
        assert result.findings == []
        assert result.pages_reviewed == 3
        assert result.pages_skipped == 1
