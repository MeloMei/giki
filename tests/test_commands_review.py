# tests/test_commands_review.py
"""Tests for the giki review CLI command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import git
import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.llm.base import LLMAdapter, LLMResponse, Message


@pytest.fixture
def runner():
    return CliRunner()


_CFG_YAML = """
llm:
  compile:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
  review:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
review:
  unrelated_edit_threshold: 0.30
  severity_blocking: [blocker]
  pr_comment_collapse: true
"""

_RULES_MD = """\
# Wiki Rules

## R-1

**test-rule** — severity: `blocker`

Test rule body.
"""


def _init_review_repo(tmp_path, slugs=None):
    """Set up a minimal giki KB with a feature branch containing wiki changes."""
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.co").release()

    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(_CFG_YAML, encoding="utf-8")
    (tmp_path / "wiki-rules.md").write_text(_RULES_MD, encoding="utf-8")
    (tmp_path / "wiki").mkdir()

    slug_lines = "\n".join(f"- [[{s}]] — {s}" for s in (slugs or []))
    (tmp_path / "index.md").write_text(
        "# Index\n\n<!-- giki:index-begin -->\n"
        f"## Uncategorized\n{slug_lines}\n"
        "<!-- giki:index-end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    repo.index.add([
        ".giki/config.yaml", "wiki-rules.md", "index.md", "README.md",
    ])
    repo.index.commit("initial")

    repo.create_head("feature").checkout()
    return repo


class FakeLLM(LLMAdapter):
    provider = "fake"
    model = "fake-m"
    name = "fake:fake-m"

    def __init__(self, responses=None):
        self._responses = list(responses or [])

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        if self._responses:
            r = self._responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return LLMResponse(text=r, finish_reason="stop")
        return LLMResponse(
            text=json.dumps({"findings": [], "verdict": "approve"}),
            finish_reason="stop",
        )


class TestReviewHelp:
    def test_help_shows_flags(self, runner):
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0, result.output
        for flag in ("--pr", "--post", "--json"):
            assert flag in result.stdout


class TestReviewJson:
    def test_json_output(self, runner, tmp_path):
        _init_review_repo(tmp_path, slugs=["test-page"])

        page_content = (
            "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\nsources:\n  - path: src.md\n"
            "---\n\nTest body.\n"
        )
        (tmp_path / "wiki" / "test-page.md").write_text(
            page_content, encoding="utf-8",
        )
        repo = git.Repo(tmp_path)
        repo.index.add(["wiki/test-page.md"])
        repo.index.commit("add test page")

        with patch("giki.commands.review.build_client", return_value=FakeLLM()):
            result = runner.invoke(
                app,
                ["review", "--json", "--root", str(tmp_path)],
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["verdict"] == "approve"


class TestReviewMarkdown:
    def test_markdown_output(self, runner, tmp_path):
        _init_review_repo(tmp_path, slugs=["test"])

        page_content = (
            "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\nBody.\n"
        )
        (tmp_path / "wiki" / "test.md").write_text(page_content, encoding="utf-8")
        repo = git.Repo(tmp_path)
        repo.index.add(["wiki/test.md"])
        repo.index.commit("add test")

        with patch("giki.commands.review.build_client", return_value=FakeLLM()):
            result = runner.invoke(
                app,
                ["review", "--root", str(tmp_path)],
            )

        assert result.exit_code == 0
        assert "approve" in result.stdout.lower()


class TestReviewExitCode:
    def test_request_changes_exits_1(self, runner, tmp_path):
        _init_review_repo(tmp_path)

        # Page with a dead link to nonexistent page
        page_content = (
            "---\ntitle: Bad\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\nsources:\n  - path: s.md\n"
            "---\n\nSee [[nonexistent]].\n"
        )
        (tmp_path / "wiki" / "bad-page.md").write_text(
            page_content, encoding="utf-8",
        )
        repo = git.Repo(tmp_path)
        repo.index.add(["wiki/bad-page.md"])
        repo.index.commit("add bad page")

        with patch("giki.commands.review.build_client", return_value=FakeLLM()):
            result = runner.invoke(
                app,
                ["review", "--root", str(tmp_path)],
            )

        # Dead link -> blocker -> request-changes -> exit 1
        assert result.exit_code == 1


class TestReviewPost:
    def test_post_requires_pr(self, runner, tmp_path):
        _init_review_repo(tmp_path)
        result = runner.invoke(
            app,
            ["review", "--post", "--root", str(tmp_path)],
        )
        assert result.exit_code != 0

    def test_post_calls_gh(self, runner, tmp_path):
        _init_review_repo(tmp_path)

        page_content = (
            "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\n---\n\nBody.\n"
        )
        (tmp_path / "wiki" / "test.md").write_text(page_content, encoding="utf-8")
        repo = git.Repo(tmp_path)
        repo.index.add(["wiki/test.md"])
        repo.index.commit("add test")

        with patch(
            "giki.commands.review.build_client", return_value=FakeLLM()
        ), patch("giki.wiki.review_fmt.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr="",
            )
            result = runner.invoke(
                app,
                ["review", "--pr", "42", "--post", "--root", str(tmp_path)],
            )

        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert "42" in args
