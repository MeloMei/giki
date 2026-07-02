"""Tests for giki.wiki.review_agent -- mechanical checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from giki.review_models import ChangeType, FileChange
from giki.wiki.review_agent import (
    check_dead_links,
    check_frontmatter,
    check_index_sync,
    check_unrelated_edits,
)

_VALID_PAGE = (
    "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
    "updated: 2026-01-01T00:00:00+00:00\n---\n\nBody.\n"
)


def _make_wiki(tmp_path: Path, slug: str, content: str) -> None:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / f"{slug}.md").write_text(content, encoding="utf-8")


# -- check_dead_links --


class TestCheckDeadLinks:
    def test_no_dead_links(self, tmp_path: Path) -> None:
        _make_wiki(tmp_path, "a", _VALID_PAGE)
        _make_wiki(tmp_path, "b", _VALID_PAGE)
        changes = [FileChange("wiki/a.md", ChangeType.UPDATED)]
        assert check_dead_links(tmp_path / "wiki", changes) == []

    def test_dead_link_in_new_page(self, tmp_path: Path) -> None:
        page = (
            "---\ntitle: A\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\nSee [[missing]].\n"
        )
        _make_wiki(tmp_path, "a", page)
        changes = [FileChange("wiki/a.md", ChangeType.NEW)]
        findings = check_dead_links(tmp_path / "wiki", changes)
        assert len(findings) == 1
        assert findings[0].rule_id == "dead-link"
        assert findings[0].severity == "blocker"
        assert "missing" in findings[0].message

    def test_dead_link_in_updated_page(self, tmp_path: Path) -> None:
        page = (
            "---\ntitle: A\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\nSee [[gone]].\n"
        )
        _make_wiki(tmp_path, "a", page)
        changes = [FileChange("wiki/a.md", ChangeType.UPDATED)]
        findings = check_dead_links(tmp_path / "wiki", changes)
        assert len(findings) == 1
        assert findings[0].rule_id == "dead-link"

    def test_deleted_page_causes_orphan_links(self, tmp_path: Path) -> None:
        _make_wiki(tmp_path, "a", _VALID_PAGE)
        linker_page = (
            "---\ntitle: B\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\nSee [[a]].\n"
        )
        _make_wiki(tmp_path, "b", linker_page)
        changes = [FileChange("wiki/a.md", ChangeType.DELETED)]
        (tmp_path / "wiki" / "a.md").unlink()
        findings = check_dead_links(tmp_path / "wiki", changes)
        assert len(findings) == 1
        assert findings[0].rule_id == "dead-link"
        assert findings[0].page_slug == "b"

    def test_no_changes_no_findings(self, tmp_path: Path) -> None:
        _make_wiki(tmp_path, "a", _VALID_PAGE)
        assert check_dead_links(tmp_path / "wiki", []) == []

    def test_alias_link_not_flagged(self, tmp_path: Path) -> None:
        alias_page = (
            "---\ntitle: A\naliases: [alias-a]\n"
            "created: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\nBody.\n"
        )
        _make_wiki(tmp_path, "a", alias_page)
        linker_page = (
            "---\ntitle: B\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\nSee [[alias-a]].\n"
        )
        _make_wiki(tmp_path, "b", linker_page)
        changes = [FileChange("wiki/b.md", ChangeType.UPDATED)]
        findings = check_dead_links(tmp_path / "wiki", changes)
        assert findings == []


# -- check_frontmatter --


class TestCheckFrontmatter:
    def test_valid_page_no_findings(self, tmp_path: Path) -> None:
        _make_wiki(tmp_path, "valid-slug", _VALID_PAGE)
        changes = [FileChange("wiki/valid-slug.md", ChangeType.NEW)]
        assert check_frontmatter(tmp_path / "wiki", changes) == []

    def test_missing_frontmatter_blocker(self, tmp_path: Path) -> None:
        _make_wiki(tmp_path, "bad", "No frontmatter here.")
        changes = [FileChange("wiki/bad.md", ChangeType.NEW)]
        findings = check_frontmatter(tmp_path / "wiki", changes)
        blockers = [f for f in findings if f.severity == "blocker"]
        assert len(blockers) == 1
        assert blockers[0].rule_id == "frontmatter"

    def test_invalid_slug_pattern_warn(self, tmp_path: Path) -> None:
        _make_wiki(tmp_path, "Invalid_Slug", _VALID_PAGE)
        changes = [FileChange("wiki/Invalid_Slug.md", ChangeType.NEW)]
        findings = check_frontmatter(tmp_path / "wiki", changes)
        warns = [f for f in findings if f.rule_id == "R-3"]
        assert len(warns) >= 1

    def test_slug_too_long_warn(self, tmp_path: Path) -> None:
        slug = "a" * 81
        _make_wiki(tmp_path, slug, _VALID_PAGE)
        changes = [FileChange(f"wiki/{slug}.md", ChangeType.NEW)]
        findings = check_frontmatter(tmp_path / "wiki", changes)
        warns = [f for f in findings if f.rule_id == "R-3" and "exceeds" in f.message]
        assert len(warns) == 1

    def test_deleted_page_skipped(self, tmp_path: Path) -> None:
        changes = [FileChange("wiki/gone.md", ChangeType.DELETED)]
        assert check_frontmatter(tmp_path / "wiki", changes) == []


# -- check_index_sync --


class TestCheckIndexSync:
    def test_new_page_in_index_ok(self) -> None:
        changes = [FileChange("wiki/my-page.md", ChangeType.NEW)]
        assert check_index_sync(changes, "See [[my-page]] for details.") == []

    def test_new_page_missing_from_index_warn(self) -> None:
        changes = [FileChange("wiki/my-page.md", ChangeType.NEW)]
        findings = check_index_sync(changes, "Nothing here.")
        assert len(findings) == 1
        assert findings[0].rule_id == "index-sync"

    def test_no_wiki_changes_ok(self) -> None:
        changes = [FileChange("src/main.py", ChangeType.UPDATED)]
        assert check_index_sync(changes, "") == []

    def test_updated_page_not_checked(self) -> None:
        changes = [FileChange("wiki/existing.md", ChangeType.UPDATED)]
        assert check_index_sync(changes, "") == []


# -- check_unrelated_edits --


class TestCheckUnrelatedEdits:
    def test_all_wiki_ok(self) -> None:
        changes = [
            FileChange("wiki/a.md", ChangeType.NEW),
            FileChange("wiki/b.md", ChangeType.UPDATED),
        ]
        assert check_unrelated_edits(changes, threshold=0.5) == []

    def test_high_unrelated_ratio_warn(self) -> None:
        changes = [
            FileChange("wiki/a.md", ChangeType.NEW),
            FileChange("src/main.py", ChangeType.UPDATED),
            FileChange("src/util.py", ChangeType.UPDATED),
            FileChange("README.md", ChangeType.UPDATED),
        ]
        findings = check_unrelated_edits(changes, threshold=0.5)
        assert len(findings) == 1
        assert findings[0].rule_id == "unrelated-edits"

    def test_below_threshold_ok(self) -> None:
        changes = [
            FileChange("wiki/a.md", ChangeType.NEW),
            FileChange("wiki/b.md", ChangeType.NEW),
            FileChange("wiki/c.md", ChangeType.NEW),
            FileChange("src/main.py", ChangeType.UPDATED),
        ]
        assert check_unrelated_edits(changes, threshold=0.5) == []

    def test_empty_changes_ok(self) -> None:
        assert check_unrelated_edits([], threshold=0.5) == []

    def test_giki_state_counts_as_wiki(self) -> None:
        changes = [
            FileChange(".giki-state/sources/a.json", ChangeType.NEW),
            FileChange("wiki/a.md", ChangeType.NEW),
        ]
        assert check_unrelated_edits(changes, threshold=0.5) == []
