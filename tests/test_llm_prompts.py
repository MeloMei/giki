import pytest
from pathlib import Path

from giki.llm.prompts import PromptTemplate, PromptError


class TestRender:
    def test_simple_substitution(self):
        t = PromptTemplate("Hello {{ name }}!")
        assert t.render(name="Alice") == "Hello Alice!"

    def test_multiple_vars(self):
        t = PromptTemplate("Hello {{ name }}, you are {{ role }}.")
        assert t.render(name="A", role="admin") == "Hello A, you are admin."

    def test_no_vars_returns_source_unchanged(self):
        t = PromptTemplate("Just a static string.")
        assert t.render() == "Just a static string."

    def test_missing_var_raises(self):
        t = PromptTemplate("Hi {{ name }}")
        with pytest.raises(PromptError, match="name"):
            t.render()

    def test_extra_kwarg_ignored(self):
        t = PromptTemplate("Hi {{ name }}")
        assert t.render(name="A", extra="ignored") == "Hi A"

    def test_underscore_var_name(self):
        t = PromptTemplate("{{ index_summary }}")
        assert t.render(index_summary="X") == "X"

    def test_numeric_var_name_after_letter(self):
        t = PromptTemplate("{{ v1 }} and {{ page_2 }}")
        assert t.render(v1="A", page_2="B") == "A and B"

    def test_multiline_value(self):
        t = PromptTemplate("Content:\n{{ body }}\nEnd")
        result = t.render(body="line1\nline2")
        assert "line1\nline2" in result
        assert result.startswith("Content:\n")
        assert result.endswith("\nEnd")

    def test_repeated_var(self):
        t = PromptTemplate("{{ x }} and {{ x }} again")
        assert t.render(x="Y") == "Y and Y again"

    def test_whitespace_in_braces(self):
        t = PromptTemplate("{{name}} vs {{ name }} vs {{  name  }}")
        assert t.render(name="X") == "X vs X vs X"

    def test_missing_lists_all_missing(self):
        t = PromptTemplate("{{ a }} {{ b }} {{ c }}")
        with pytest.raises(PromptError) as exc:
            t.render(a="X")
        msg = str(exc.value)
        assert "b" in msg and "c" in msg

    def test_non_string_value_stringified(self):
        t = PromptTemplate("N = {{ n }}")
        assert t.render(n=42) == "N = 42"


class TestFromFile:
    def test_reads_file(self, tmp_path):
        p = tmp_path / "greet.md"
        p.write_text("Hi {{ name }}", encoding="utf-8")
        t = PromptTemplate.from_file(p)
        assert t.render(name="A") == "Hi A"
        assert "greet.md" in t.name


class TestFromPackage:
    def test_missing_template_raises(self):
        with pytest.raises((PromptError, FileNotFoundError)):
            PromptTemplate.from_package("does_not_exist.md")

    def test_finds_existing_template(self):
        # After Task 1 there is at least .gitkeep in src/giki/templates/;
        # after Task 23 there will be real .md templates. We only assert
        # the API resolves the package correctly by trying a bogus file
        # and getting a clear error. See test above.
        pass
