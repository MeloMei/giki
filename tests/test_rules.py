"""Tests for wiki-rules.md parser."""

from __future__ import annotations

import pytest

from giki.rules import parse_rules


_RULES_TEXT = """\
# Wiki Rules

_Starter rules._

## R-1 consistency

severity: `blocker`

Facts must not contradict.

## R-2 citation integrity

severity: `blocker`

Claims need sources.

## R-3 naming convention

severity: `warn`

Slugs must match pattern.

## R-4 bidirectional links

severity: `warn`

Prefer [[wiki-link]].

## R-5 paragraph length

severity: `nit`

Keep paragraphs short.
"""


class TestParseRules:
    def test_parse_five_rules(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert len(rules) == 5
        assert [r.anchor for r in rules] == ["R-1", "R-2", "R-3", "R-4", "R-5"]

    def test_severities(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert rules[0].severity == "blocker"
        assert rules[2].severity == "warn"
        assert rules[4].severity == "nit"

    def test_names_extracted(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert "consistency" in rules[0].name

    def test_body(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert "contradict" in rules[0].body

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_rules(tmp_path / "nonexistent.md")

    def test_no_anchors_raises(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text("# Just a heading\n\nNo rules.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no.*R-N"):
            parse_rules(f)

    def test_missing_severity_defaults_warn(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text("## R-1\n\n**unnamed**\n\nBody.\n", encoding="utf-8")
        rules = parse_rules(f)
        assert rules[0].severity == "warn"

    def test_multidigit_anchor(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text("## R-42\n\n**rule** — severity: `blocker`\n\nBody.\n", encoding="utf-8")
        rules = parse_rules(f)
        assert rules[0].anchor == "R-42"
