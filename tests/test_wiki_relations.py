"""Tests for giki.wiki.relations and check_typed_links mechanical check."""

from __future__ import annotations

from pathlib import Path

import pytest

from giki.review_models import ChangeType, FileChange
from giki.wiki.relations import (
    RELATION_TYPES,
    get_relation_info,
    is_valid_relation_type,
)
from giki.wiki.review_agent import check_typed_links


_VALID_PAGE = (
    "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
    "updated: 2026-01-01T00:00:00+00:00\n---\n\nBody.\n"
)


def _make_wiki(tmp_path: Path, slug: str, content: str) -> None:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / f"{slug}.md").write_text(content, encoding="utf-8")


# -- RELATION_TYPES --


class TestRelationTypes:
    def test_eight_types_defined(self) -> None:
        assert len(RELATION_TYPES) == 8

    @pytest.mark.parametrize(
        "rtype",
        [
            "requires",
            "contradicts",
            "implements",
            "extends",
            "example-of",
            "related",
            "prerequisite",
            "alternative",
        ],
    )
    def test_all_canonical_types_valid(self, rtype: str) -> None:
        assert is_valid_relation_type(rtype) is True

    @pytest.mark.parametrize(
        "rtype",
        ["see-also", "references", "depends-on", "", "Requires", "RELATED"],
    )
    def test_invalid_types_rejected(self, rtype: str) -> None:
        assert is_valid_relation_type(rtype) is False


# -- get_relation_info --


class TestGetRelationInfo:
    @pytest.mark.parametrize(
        "rtype,direction",
        [
            ("requires", "forward"),
            ("contradicts", "bidirectional"),
            ("implements", "forward"),
            ("extends", "forward"),
            ("example-of", "forward"),
            ("related", "bidirectional"),
            ("prerequisite", "forward"),
            ("alternative", "bidirectional"),
        ],
    )
    def test_direction(self, rtype: str, direction: str) -> None:
        info = get_relation_info(rtype)
        assert info["direction"] == direction

    def test_description_is_nonempty_string(self) -> None:
        for rtype in RELATION_TYPES:
            info = get_relation_info(rtype)
            assert isinstance(info["description"], str)
            assert len(info["description"]) > 0

    def test_unknown_type_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="unknown relation type"):
            get_relation_info("bogus-type")

    def test_returns_copy(self) -> None:
        """Mutating the returned dict must not affect the internal store."""
        info = get_relation_info("requires")
        info["direction"] = "MUTATED"
        assert get_relation_info("requires")["direction"] == "forward"


# -- check_typed_links --


class TestCheckTypedLinks:
    def test_valid_typed_links_no_findings(self, tmp_path: Path) -> None:
        page = (
            "---\ntitle: A\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\n"
            "See [[requires::singleton]] and [[implements::strategy]].\n"
        )
        _make_wiki(tmp_path, "a", page)
        changes = [FileChange("wiki/a.md", ChangeType.NEW)]
        assert check_typed_links(tmp_path / "wiki", changes) == []

    def test_unknown_type_produces_warning(self, tmp_path: Path) -> None:
        page = (
            "---\ntitle: A\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\n"
            "See [[see-also::some-page]].\n"
        )
        _make_wiki(tmp_path, "a", page)
        changes = [FileChange("wiki/a.md", ChangeType.NEW)]
        findings = check_typed_links(tmp_path / "wiki", changes)
        assert len(findings) == 1
        assert findings[0].rule_id == "MECH-TYPED-LINK"
        assert findings[0].severity == "warn"
        assert "see-also" in findings[0].message
        assert findings[0].page_slug == "a"

    def test_plain_wikilinks_ignored(self, tmp_path: Path) -> None:
        page = (
            "---\ntitle: A\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\n"
            "See [[some-page]] and [[other|display text]].\n"
        )
        _make_wiki(tmp_path, "a", page)
        changes = [FileChange("wiki/a.md", ChangeType.UPDATED)]
        assert check_typed_links(tmp_path / "wiki", changes) == []

    def test_multiple_invalid_types(self, tmp_path: Path) -> None:
        page = (
            "---\ntitle: A\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\n"
            "See [[foo::x]] and [[bar::y]].\n"
        )
        _make_wiki(tmp_path, "a", page)
        changes = [FileChange("wiki/a.md", ChangeType.NEW)]
        findings = check_typed_links(tmp_path / "wiki", changes)
        assert len(findings) == 2
        assert all(f.rule_id == "MECH-TYPED-LINK" for f in findings)

    def test_deleted_pages_skipped(self, tmp_path: Path) -> None:
        changes = [FileChange("wiki/gone.md", ChangeType.DELETED)]
        assert check_typed_links(tmp_path / "wiki", changes) == []

    def test_no_wiki_changes(self, tmp_path: Path) -> None:
        assert check_typed_links(tmp_path / "wiki", []) == []

    def test_non_wiki_changes_skipped(self, tmp_path: Path) -> None:
        changes = [FileChange("src/main.py", ChangeType.UPDATED)]
        assert check_typed_links(tmp_path / "wiki", changes) == []

    def test_mix_valid_and_invalid(self, tmp_path: Path) -> None:
        page = (
            "---\ntitle: A\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\n"
            "See [[requires::singleton]] and [[badtype::other]].\n"
        )
        _make_wiki(tmp_path, "a", page)
        changes = [FileChange("wiki/a.md", ChangeType.NEW)]
        findings = check_typed_links(tmp_path / "wiki", changes)
        assert len(findings) == 1
        assert "badtype" in findings[0].message

    def test_parse_error_skipped(self, tmp_path: Path) -> None:
        _make_wiki(tmp_path, "broken", "No frontmatter here.")
        changes = [FileChange("wiki/broken.md", ChangeType.NEW)]
        assert check_typed_links(tmp_path / "wiki", changes) == []
