import pytest
from pathlib import Path

from giki.wiki.linker import Linker
from giki.wiki.parser import WikiLink, WikiPage, parse_page
from giki.wiki.store import WikiStore


def _write(store: WikiStore, slug: str, *, title: str, aliases=None) -> None:
    aliases_block = f"aliases: {aliases}\n" if aliases else ""
    body = f"""---
title: {title}
{aliases_block}created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---

# {title}

body.
"""
    store.write(slug, body)


def _mk_store(tmp_path: Path) -> WikiStore:
    (tmp_path / "wiki").mkdir()
    return WikiStore(tmp_path)


class TestResolve:
    def test_direct_filename(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "observer-pattern", title="Observer")
        linker = Linker(store)
        assert linker.resolve("observer-pattern") == "observer-pattern"

    def test_alias_lookup(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "observer-pattern", title="Observer", aliases=["Observer Pattern", "obs"])
        linker = Linker(store)
        assert linker.resolve("Observer Pattern") == "observer-pattern"
        assert linker.resolve("obs") == "observer-pattern"

    def test_direct_wins_over_alias(self, tmp_path):
        """If two pages exist and one is aliased with the other's slug,
        direct filename lookup should win."""
        store = _mk_store(tmp_path)
        _write(store, "foo", title="Foo")
        _write(store, "bar", title="Bar", aliases=["foo"])  # Bar aliases 'foo'
        linker = Linker(store)
        assert linker.resolve("foo") == "foo"  # direct match wins

    def test_no_match_returns_none(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "a", title="A")
        assert Linker(store).resolve("nonexistent") is None

    def test_case_sensitive(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "observer", title="Observer")
        assert Linker(store).resolve("Observer") is None  # case matters


class TestDeadLinks:
    def test_returns_unresolved(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "a", title="A")
        page = parse_page(store.read("a") + "\n\nSee [[nonexistent]] and [[a]].")
        linker = Linker(store)
        dead = linker.dead_links(page, "a")
        assert WikiLink(target="nonexistent", display=None) in dead
        assert WikiLink(target="a", display=None) not in dead  # 'a' resolves (self-link OK)

    def test_excludes_self_link(self, tmp_path):
        """A page linking to itself should not be flagged as dead
        (since it resolves), but explicitly the linker excludes self-links."""
        store = _mk_store(tmp_path)
        _write(store, "a", title="A")
        page = parse_page(store.read("a") + "\n\nSelf [[a]].")
        linker = Linker(store)
        dead = linker.dead_links(page, "a")
        assert dead == []

    def test_empty_when_all_resolve(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "a", title="A")
        _write(store, "b", title="B")
        page = parse_page(store.read("a") + "\n\n[[b]] and [[b]] again.")
        linker = Linker(store)
        assert linker.dead_links(page, "a") == []

    def test_via_alias(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "a", title="A", aliases=["Alpha"])
        _write(store, "b", title="B")
        page = parse_page(store.read("b") + "\n\n[[Alpha]] (alias)")
        linker = Linker(store)
        assert linker.dead_links(page, "b") == []


class TestReindex:
    def test_picks_up_new_page(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "a", title="A")
        linker = Linker(store)
        assert linker.resolve("b") is None

        _write(store, "b", title="B")
        # Before reindex: linker doesn't know about b
        assert linker.resolve("b") is None
        linker.reindex()
        # After reindex: b resolves
        assert linker.resolve("b") == "b"

    def test_picks_up_new_alias(self, tmp_path):
        store = _mk_store(tmp_path)
        _write(store, "a", title="A")
        linker = Linker(store)
        assert linker.resolve("Alpha") is None

        _write(store, "a", title="A", aliases=["Alpha"])
        linker.reindex()
        assert linker.resolve("Alpha") == "a"


from giki.wiki.linker import apply_related_block


class TestRelatedBlock:
    def test_below_min_neighbors_unchanged(self):
        body = "# Title\n\nSome content.\n"
        assert apply_related_block(body, [], min_neighbors=1) == body
        assert apply_related_block(body, [], min_neighbors=2) == body
        assert apply_related_block(body, ["one"], min_neighbors=2) == body

    def test_first_time_append(self):
        body = "# Title\n\nSome content.\n"
        result = apply_related_block(body, ["a", "b"], min_neighbors=1)
        assert "# Title" in result
        assert "Some content." in result
        assert "## Related" in result
        assert "- [[a]]" in result
        assert "- [[b]]" in result
        # The separator '---' should appear once before Related
        related_pos = result.index("## Related")
        content_before = result[:related_pos]
        assert "---" in content_before

    def test_existing_block_replaced(self):
        body = """# Title

Content.

---

## Related
- [[old-neighbor]]
"""
        result = apply_related_block(body, ["new-a", "new-b"], min_neighbors=1)
        assert "old-neighbor" not in result
        assert "- [[new-a]]" in result
        assert "- [[new-b]]" in result
        # Should still have exactly one ## Related
        assert result.count("## Related") == 1

    def test_order_preserved(self):
        body = "# T\n\nContent.\n"
        result = apply_related_block(body, ["c", "a", "b"], min_neighbors=1)
        ia = result.index("[[a]]")
        ib = result.index("[[b]]")
        ic = result.index("[[c]]")
        # Neighbors written in the order given
        assert ic < ia < ib

    def test_empty_neighbors_with_existing_block_removes_it(self):
        """If neighbors becomes empty and a block exists, the block should be removed."""
        body = """# T

Content.

---

## Related
- [[old]]
"""
        result = apply_related_block(body, [], min_neighbors=1)
        assert "## Related" not in result
        assert "old" not in result
        # The main content should still be present
        assert "Content." in result

    def test_no_double_appended_when_re_run(self):
        body = "# T\n\nContent.\n"
        once = apply_related_block(body, ["a"], min_neighbors=1)
        twice = apply_related_block(once, ["a"], min_neighbors=1)
        # Should not have two "## Related" sections
        assert twice.count("## Related") == 1
