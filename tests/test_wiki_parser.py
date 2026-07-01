import pytest

from giki.wiki.parser import parse_page, WikiPage, WikiLink, ParseError


SIMPLE = """---
title: Observer Pattern
tags: [design-pattern]
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
sources:
  - path: sources/manual.pdf
    pages: "23-27"
---

# Observer Pattern

Body with [[event-bus]] and [[subject|the Subject role]].
"""


HANDWRITTEN = """---
title: My Notes
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---

# My Notes

Just [[some-link]] here.
"""


NO_FRONTMATTER = """# Bare page

No frontmatter.
"""


BAD_FRONTMATTER = """---
title: Broken
not_yaml: [[[
---

body
"""


class TestFrontmatter:
    def test_parse_simple(self):
        p = parse_page(SIMPLE)
        assert p.title == "Observer Pattern"
        assert p.tags == ["design-pattern"]
        assert p.sources == [{"path": "sources/manual.pdf", "pages": "23-27"}]
        assert p.created == "2026-06-30T14:00:00+08:00"
        assert p.updated == "2026-06-30T14:00:00+08:00"

    def test_is_hand_written_flag(self):
        assert parse_page(SIMPLE).is_hand_written is False
        assert parse_page(HANDWRITTEN).is_hand_written is True

    def test_missing_frontmatter_raises(self):
        with pytest.raises(ParseError, match="frontmatter"):
            parse_page(NO_FRONTMATTER)

    def test_malformed_frontmatter_raises(self):
        with pytest.raises(ParseError):
            parse_page(BAD_FRONTMATTER)

    def test_missing_required_title_raises(self):
        src = """---
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# T
"""
        with pytest.raises(ParseError, match="title"):
            parse_page(src)

    def test_missing_required_created_raises(self):
        src = """---
title: T
updated: 2026-06-30T14:00:00+08:00
---
# T
"""
        with pytest.raises(ParseError, match="created"):
            parse_page(src)

    def test_missing_required_updated_raises(self):
        src = """---
title: T
created: 2026-06-30T14:00:00+08:00
---
# T
"""
        with pytest.raises(ParseError, match="updated"):
            parse_page(src)

    def test_frontmatter_not_a_mapping_raises(self):
        src = "---\n- item1\n- item2\n---\n\n# T\n"
        with pytest.raises(ParseError, match="mapping"):
            parse_page(src)


class TestAliases:
    def test_aliases_default_empty(self):
        p = parse_page(HANDWRITTEN)
        assert p.aliases == []

    def test_aliases_parsed(self):
        src = """---
title: T
aliases: ["A1", "A2"]
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# T
"""
        p = parse_page(src)
        assert p.aliases == ["A1", "A2"]


class TestTags:
    def test_tags_default_empty(self):
        p = parse_page(HANDWRITTEN)
        assert p.tags == []

    def test_tags_parsed(self):
        p = parse_page(SIMPLE)
        assert p.tags == ["design-pattern"]


class TestWikilinks:
    def test_plain_links_extracted(self):
        p = parse_page(HANDWRITTEN)
        assert WikiLink(target="some-link", display=None) in p.links

    def test_display_link_extracted(self):
        p = parse_page(SIMPLE)
        assert WikiLink(target="event-bus", display=None) in p.links
        assert WikiLink(target="subject", display="the Subject role") in p.links

    def test_link_target_with_hash_stripped(self):
        """[[foo#heading]] -> target=foo (v0.1 ignores # segments)."""
        src = """---
title: T
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# T

See [[foo#bar]] and [[foo#bar|display]].
"""
        p = parse_page(src)
        assert WikiLink(target="foo", display=None) in p.links
        assert WikiLink(target="foo", display="display") in p.links

    def test_no_links(self):
        src = """---
title: T
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# T

Body without any wikilinks.
"""
        p = parse_page(src)
        assert p.links == []

    def test_multiple_links_preserved_order(self):
        src = """---
title: T
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# T

[[a]] and [[b]] and [[c]]
"""
        p = parse_page(src)
        assert p.links == [
            WikiLink(target="a", display=None),
            WikiLink(target="b", display=None),
            WikiLink(target="c", display=None),
        ]

    def test_whitespace_in_target_stripped(self):
        src = """---
title: T
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# T

[[ foo ]] and [[ bar | baz ]]
"""
        p = parse_page(src)
        assert WikiLink(target="foo", display=None) in p.links
        assert WikiLink(target="bar", display="baz") in p.links


class TestBody:
    def test_body_contains_content_after_frontmatter(self):
        p = parse_page(SIMPLE)
        assert "# Observer Pattern" in p.body
        assert "[[event-bus]]" in p.body
