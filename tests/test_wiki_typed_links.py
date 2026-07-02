"""Tests for typed wikilinks: [[type::target]] and [[type::target|display]]."""

import pytest

from giki.wiki.parser import parse_page, WikiLink


_PAGE_TMPL = """---
title: T
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# T

{body}
"""


def _parse(body: str):
    return parse_page(_PAGE_TMPL.format(body=body))


class TestTypedWikilinks:
    def test_parse_typed_wikilink(self):
        """[[requires::singleton-pattern]] -> link_type='requires', target='singleton-pattern'."""
        p = _parse("See [[requires::singleton-pattern]].")
        assert len(p.links) == 1
        link = p.links[0]
        assert link.link_type == "requires"
        assert link.target == "singleton-pattern"
        assert link.display is None

    def test_parse_typed_wikilink_with_display(self):
        """[[requires::singleton|Singleton Pattern]] -> link_type, target, display."""
        p = _parse("See [[requires::singleton|Singleton Pattern]].")
        assert len(p.links) == 1
        link = p.links[0]
        assert link.link_type == "requires"
        assert link.target == "singleton"
        assert link.display == "Singleton Pattern"

    def test_parse_plain_wikilink_no_type(self):
        """[[observer-pattern]] -> link_type=None (backward compatible)."""
        p = _parse("See [[observer-pattern]].")
        assert len(p.links) == 1
        link = p.links[0]
        assert link.link_type is None
        assert link.target == "observer-pattern"
        assert link.display is None

    def test_parse_mixed_links(self):
        """Body with both plain and typed wikilinks parses all correctly."""
        p = _parse(
            "Uses [[observer-pattern]] and [[requires::singleton]] "
            "plus [[implements::strategy|Strategy Pattern]] and [[plain-link|a display]]."
        )
        assert p.links == [
            WikiLink(target="observer-pattern", display=None, link_type=None),
            WikiLink(target="singleton", display=None, link_type="requires"),
            WikiLink(target="strategy", display="Strategy Pattern", link_type="implements"),
            WikiLink(target="plain-link", display="a display", link_type=None),
        ]

    def test_typed_link_equality_with_plain_constructor(self):
        """WikiLink constructed without link_type defaults to None — equality holds."""
        link = WikiLink(target="foo", display=None)
        assert link.link_type is None
        assert link == WikiLink(target="foo", display=None, link_type=None)

    def test_typed_link_with_hyphenated_type(self):
        """link_type may contain hyphens: [[see-also::some-target]]."""
        p = _parse("[[see-also::some-target]]")
        assert len(p.links) == 1
        assert p.links[0].link_type == "see-also"
        assert p.links[0].target == "some-target"

    def test_uppercase_prefix_not_treated_as_type(self):
        """Uppercase letters do NOT start a type prefix: [[Foo::bar]] is a plain link."""
        p = _parse("[[Foo::bar]]")
        assert len(p.links) == 1
        link = p.links[0]
        # Should be parsed as a plain link whose target is "Foo::bar"
        assert link.link_type is None
