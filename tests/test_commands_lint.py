"""Tests for ``giki lint`` command -- wiki health check with --fix mode."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.commands.lint import (
    LintFinding,
    _check_dead_links_lint,
    _check_missing_frontmatter,
    _check_orphan_pages,
    _check_slug_violations,
    lint_command,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_page(
    wiki_dir: Path,
    slug: str,
    title: str,
    body: str,
    *,
    with_frontmatter: bool = True,
) -> None:
    """Write a wiki page, optionally without frontmatter."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
    if with_frontmatter:
        content = (
            "---\n"
            f"title: {title}\n"
            "created: 2024-01-01T00:00:00+00:00\n"
            "updated: 2024-01-01T00:00:00+00:00\n"
            "aliases: []\n"
            "tags: []\n"
            "sources: []\n"
            "---\n"
            f"{body}"
        )
    else:
        content = body
    (wiki_dir / f"{slug}.md").write_text(content, encoding="utf-8")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Tests: dead links check
# ---------------------------------------------------------------------------


class TestDeadLinksCheck:
    def test_no_dead_links(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "page-a", "Page A", "Link to [[page-b]].")
        _write_page(wiki_dir, "page-b", "Page B", "No links.")

        findings = _check_dead_links_lint(tmp_path)
        assert findings == []

    def test_dead_link_found(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "page-a", "Page A", "Link to [[nonexistent]].")

        findings = _check_dead_links_lint(tmp_path)
        assert len(findings) == 1
        assert findings[0].severity == "error"
        assert findings[0].slug == "page-a"
        assert "nonexistent" in findings[0].message
        assert findings[0].fixable is True

    def test_self_link_not_dead(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "page-a", "Page A", "Self link [[page-a]].")

        findings = _check_dead_links_lint(tmp_path)
        assert findings == []


# ---------------------------------------------------------------------------
# Tests: missing frontmatter check
# ---------------------------------------------------------------------------


class TestMissingFrontmatter:
    def test_all_pages_have_frontmatter(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "good", "Good", "Content.")

        findings = _check_missing_frontmatter(tmp_path)
        assert findings == []

    def test_page_without_frontmatter(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "bad", "Bad", "No frontmatter here.", with_frontmatter=False)

        findings = _check_missing_frontmatter(tmp_path)
        assert len(findings) == 1
        assert findings[0].slug == "bad"
        assert "missing frontmatter" in findings[0].message
        assert findings[0].fixable is True


# ---------------------------------------------------------------------------
# Tests: orphan pages check
# ---------------------------------------------------------------------------


class TestOrphanPages:
    def test_no_orphans(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "page-a", "Page A", "Link to [[page-b]].")
        _write_page(wiki_dir, "page-b", "Page B", "No links.")

        findings = _check_orphan_pages(tmp_path)
        # page-a has no inbound links, page-b is linked from page-a
        orphans = [f.slug for f in findings]
        assert "page-a" in orphans
        assert "page-b" not in orphans

    def test_single_page_is_orphan(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "lonely", "Lonely", "All alone.")

        findings = _check_orphan_pages(tmp_path)
        assert len(findings) == 1
        assert findings[0].slug == "lonely"
        assert findings[0].severity == "warn"
        assert findings[0].fixable is False

    def test_mutual_links_no_orphans(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "a", "A", "Link to [[b]].")
        _write_page(wiki_dir, "b", "B", "Link to [[a]].")

        findings = _check_orphan_pages(tmp_path)
        assert findings == []


# ---------------------------------------------------------------------------
# Tests: slug violations check
# ---------------------------------------------------------------------------


class TestSlugViolations:
    def test_valid_slug(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "good-slug", "Good", "Content.")

        findings = _check_slug_violations(tmp_path)
        assert findings == []

    def test_invalid_slug_uppercase(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        # Write file directly with an invalid slug
        content = (
            "---\n"
            "title: Bad Slug\n"
            "created: 2024-01-01T00:00:00+00:00\n"
            "updated: 2024-01-01T00:00:00+00:00\n"
            "aliases: []\n"
            "tags: []\n"
            "sources: []\n"
            "---\n"
            "Content."
        )
        (wiki_dir / "Bad-Slug.md").write_text(content, encoding="utf-8")

        findings = _check_slug_violations(tmp_path)
        assert len(findings) == 1
        assert findings[0].slug == "Bad-Slug"
        assert findings[0].fixable is False

    def test_invalid_slug_underscore(self, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "---\n"
            "title: Under Score\n"
            "created: 2024-01-01T00:00:00+00:00\n"
            "updated: 2024-01-01T00:00:00+00:00\n"
            "aliases: []\n"
            "tags: []\n"
            "sources: []\n"
            "---\n"
            "Content."
        )
        (wiki_dir / "under_score.md").write_text(content, encoding="utf-8")

        findings = _check_slug_violations(tmp_path)
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# Tests: CLI integration
# ---------------------------------------------------------------------------


class TestLintCLI:
    def test_lint_help(self, runner: CliRunner) -> None:
        import re
        result = runner.invoke(app, ["lint", "--help"])
        assert result.exit_code == 0
        out = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        assert "--fix" in out
        assert "--root" in out

    def test_lint_listed_in_main_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "lint" in result.stdout

    def test_lint_no_wiki_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(app, ["lint", "--root", str(tmp_path)])
        assert result.exit_code != 0

    def test_lint_clean_wiki(self, runner: CliRunner, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "page-a", "Page A", "Link to [[page-b]].")
        _write_page(wiki_dir, "page-b", "Page B", "Link to [[page-a]].")

        result = runner.invoke(app, ["lint", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    def test_lint_reports_issues(self, runner: CliRunner, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "page-a", "Page A", "Link to [[nonexistent]].")

        result = runner.invoke(app, ["lint", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "issues found" in result.stdout
        assert "broken link" in result.stdout

    def test_lint_fix_dead_links(self, runner: CliRunner, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(
            wiki_dir,
            "page-a",
            "Page A",
            "Some text [[nonexistent]] more text.",
        )

        result = runner.invoke(app, ["lint", "--fix", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Fixed" in result.stdout

        # Verify the dead link was removed
        raw = (wiki_dir / "page-a.md").read_text(encoding="utf-8")
        assert "[[nonexistent]]" not in raw
        assert "Some text" in raw
        assert "more text" in raw

    def test_lint_fix_missing_frontmatter(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "bare", "Bare", "Just body.", with_frontmatter=False)

        result = runner.invoke(app, ["lint", "--fix", "--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "Fixed" in result.stdout

        # Verify frontmatter was added
        raw = (wiki_dir / "bare.md").read_text(encoding="utf-8")
        assert raw.startswith("---")
        assert "title: bare" in raw

    def test_lint_fix_preserves_body(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        wiki_dir = tmp_path / "wiki"
        body = "This is the original body content."
        _write_page(wiki_dir, "bare", "Bare", body, with_frontmatter=False)

        result = runner.invoke(app, ["lint", "--fix", "--root", str(tmp_path)])
        assert result.exit_code == 0

        raw = (wiki_dir / "bare.md").read_text(encoding="utf-8")
        assert body in raw

    def test_lint_summary_format(self, runner: CliRunner, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_page(wiki_dir, "lonely", "Lonely", "No links anywhere.")

        result = runner.invoke(app, ["lint", "--root", str(tmp_path)])
        assert result.exit_code == 0
        # Should have the summary format: "N issues found (M fixable)"
        assert re.search(r"\d+ issues? found \(\d+ fixable\)", result.stdout)
