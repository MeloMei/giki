import re
import pytest
from pathlib import Path

from giki.utils import extract_json, to_slug, iso_now, safe_relpath


class TestExtractJson:
    def test_bare_object(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json_block(self):
        text = 'Some prose\n```json\n{"a": 1}\n```\ntrailing'
        assert extract_json(text) == {"a": 1}

    def test_fenced_without_lang(self):
        assert extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_array_top_level(self):
        assert extract_json('[1, 2, 3]') == [1, 2, 3]

    def test_leading_prose_bare_object(self):
        assert extract_json('Response follows:\n{"a": 1}\nEnd.') == {"a": 1}

    def test_nested_object(self):
        assert extract_json('{"a": {"b": [1, 2]}}') == {"a": {"b": [1, 2]}}

    def test_string_with_braces_inside(self):
        assert extract_json('{"x": "has { and } inside"}') == {"x": "has { and } inside"}

    def test_string_with_escaped_quote(self):
        assert extract_json(r'{"x": "quote \" here"}') == {"x": 'quote " here'}

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            extract_json("no json here at all")

    def test_malformed_raises(self):
        with pytest.raises(ValueError):
            extract_json('{"a": ')

    def test_unterminated_raises(self):
        with pytest.raises(ValueError):
            extract_json('{"a": 1')


class TestToSlug:
    def test_ascii_simple(self):
        assert to_slug("Observer Pattern") == "observer-pattern"

    def test_strip_special_chars(self):
        assert to_slug("Hello, World!") == "hello-world"

    def test_collapse_whitespace(self):
        assert to_slug("a  b   c") == "a-b-c"

    def test_lowercase(self):
        assert to_slug("MyPage") == "mypage"

    def test_trim_dashes(self):
        assert to_slug("--hello--") == "hello"

    def test_underscore_becomes_dash(self):
        assert to_slug("foo_bar_baz") == "foo-bar-baz"

    def test_digits_preserved(self):
        assert to_slug("test 123") == "test-123"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            to_slug("")

    def test_only_special_chars_raises(self):
        with pytest.raises(ValueError):
            to_slug("!@#$%")

    def test_max_length_truncation(self):
        result = to_slug("a" * 200, max_len=80)
        assert len(result) == 80
        assert result == "a" * 80

    def test_max_length_trims_trailing_dash(self):
        # a truncated slug shouldn't end in a dash
        result = to_slug("abc-" * 30, max_len=15)
        assert not result.endswith("-")


class TestIsoNow:
    def test_returns_iso8601_with_tz(self):
        s = iso_now()
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$", s), \
            f"unexpected iso_now format: {s!r}"

    def test_returns_string(self):
        assert isinstance(iso_now(), str)


class TestSafeRelpath:
    def test_within_root(self, tmp_path):
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "foo.md").write_text("x")
        result = safe_relpath(tmp_path, tmp_path / "wiki" / "foo.md")
        assert result == Path("wiki/foo.md")

    def test_root_itself(self, tmp_path):
        result = safe_relpath(tmp_path, tmp_path)
        assert result == Path(".")

    def test_escape_root_raises(self, tmp_path):
        inner = tmp_path / "repo"
        inner.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("x")
        with pytest.raises(ValueError, match="escape|outside"):
            safe_relpath(inner, outside)

    def test_dotdot_normalized_and_raises(self, tmp_path):
        (tmp_path / "repo").mkdir()
        with pytest.raises(ValueError, match="escape|outside"):
            safe_relpath(tmp_path / "repo", tmp_path / "repo" / ".." / ".." / "outside.md")
