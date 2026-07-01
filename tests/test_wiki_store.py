import pytest
from pathlib import Path

from giki.wiki.store import WikiStore, WikiStoreError


PAGE_BODY = """---
title: T
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---

# T

body.
"""


def _mk_store(tmp_path: Path) -> WikiStore:
    (tmp_path / "wiki").mkdir()
    return WikiStore(tmp_path)


class TestBasics:
    def test_list_empty(self, tmp_path):
        assert _mk_store(tmp_path).list_pages() == []

    def test_write_and_read(self, tmp_path):
        store = _mk_store(tmp_path)
        store.write("observer", PAGE_BODY)
        assert store.read("observer") == PAGE_BODY

    def test_write_creates_md_file(self, tmp_path):
        store = _mk_store(tmp_path)
        store.write("observer", PAGE_BODY)
        assert (tmp_path / "wiki" / "observer.md").exists()

    def test_exists(self, tmp_path):
        store = _mk_store(tmp_path)
        assert store.exists("x") is False
        store.write("x", PAGE_BODY)
        assert store.exists("x") is True

    def test_read_missing_raises(self, tmp_path):
        with pytest.raises(WikiStoreError, match="not found"):
            _mk_store(tmp_path).read("missing")

    def test_list_pages_returns_slugs(self, tmp_path):
        store = _mk_store(tmp_path)
        store.write("a", PAGE_BODY)
        store.write("b", PAGE_BODY)
        store.write("c", PAGE_BODY)
        assert sorted(store.list_pages()) == ["a", "b", "c"]

    def test_list_pages_ignores_non_md(self, tmp_path):
        store = _mk_store(tmp_path)
        (tmp_path / "wiki" / "not-a-page.txt").write_text("x")
        (tmp_path / "wiki" / ".hidden").write_text("x")
        store.write("real", PAGE_BODY)
        assert store.list_pages() == ["real"]

    def test_overwrite_existing(self, tmp_path):
        store = _mk_store(tmp_path)
        store.write("x", PAGE_BODY)
        store.write("x", PAGE_BODY + "\nmore\n")
        assert "more" in store.read("x")


class TestAtomicWrite:
    def test_no_tmp_file_after_success(self, tmp_path):
        store = _mk_store(tmp_path)
        store.write("x", PAGE_BODY)
        files = list((tmp_path / "wiki").iterdir())
        assert all(not f.name.endswith(".tmp") for f in files)


class TestSlugValidation:
    def test_slug_traversal_blocked(self, tmp_path):
        store = _mk_store(tmp_path)
        with pytest.raises(WikiStoreError, match="slug"):
            store.write("../evil", "x")

    def test_slug_backslash_blocked(self, tmp_path):
        store = _mk_store(tmp_path)
        with pytest.raises(WikiStoreError, match="slug"):
            store.write("evil\\subpath", "x")

    def test_slug_absolute_blocked(self, tmp_path):
        store = _mk_store(tmp_path)
        with pytest.raises(WikiStoreError, match="slug"):
            store.write("/etc/passwd", "x")

    def test_slug_leading_dot_blocked(self, tmp_path):
        store = _mk_store(tmp_path)
        with pytest.raises(WikiStoreError, match="slug"):
            store.write(".hidden", "x")

    def test_slug_uppercase_rejected(self, tmp_path):
        store = _mk_store(tmp_path)
        with pytest.raises(WikiStoreError, match="slug"):
            store.write("UPPER", "x")

    def test_slug_space_rejected(self, tmp_path):
        store = _mk_store(tmp_path)
        with pytest.raises(WikiStoreError, match="slug"):
            store.write("has space", "x")

    def test_slug_underscore_rejected(self, tmp_path):
        """Default pattern is [a-z0-9-]+ — underscores not allowed in slugs."""
        store = _mk_store(tmp_path)
        with pytest.raises(WikiStoreError, match="slug"):
            store.write("has_underscore", "x")

    def test_slug_max_length_enforced(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        store = WikiStore(tmp_path, max_slug_length=10)
        with pytest.raises(WikiStoreError, match="length"):
            store.write("a" * 20, "x")

    def test_slug_at_max_length_ok(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        store = WikiStore(tmp_path, max_slug_length=10)
        store.write("a" * 10, PAGE_BODY)  # should not raise
        assert store.exists("a" * 10)

    def test_read_invalid_slug_raises_before_touching_disk(self, tmp_path):
        with pytest.raises(WikiStoreError, match="slug"):
            _mk_store(tmp_path).read("../etc/passwd")

    def test_custom_slug_pattern(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        store = WikiStore(tmp_path, slug_pattern=r"^[a-z]+$")  # only letters
        with pytest.raises(WikiStoreError):
            store.write("abc-def", "x")
        store.write("abc", PAGE_BODY)  # ok


class TestAllPages:
    def test_yields_parsed_pages(self, tmp_path):
        store = _mk_store(tmp_path)
        body = """---
title: The Observer
aliases: [obs]
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# The Observer
"""
        store.write("observer", body)
        pages = list(store.all_pages())
        assert len(pages) == 1
        slug, page = pages[0]
        assert slug == "observer"
        assert page.title == "The Observer"
        assert page.aliases == ["obs"]

    def test_empty_store_yields_nothing(self, tmp_path):
        assert list(_mk_store(tmp_path).all_pages()) == []

    def test_multiple_pages(self, tmp_path):
        store = _mk_store(tmp_path)
        for slug in ("a", "b", "c"):
            store.write(slug, PAGE_BODY)
        pages = list(store.all_pages())
        assert len(pages) == 3
        assert {p[0] for p in pages} == {"a", "b", "c"}
