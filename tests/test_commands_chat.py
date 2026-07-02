"""Tests for ``giki chat`` command -- BM25 retrieval and RAG Q&A."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.commands.chat import _build_rag_prompt, chat_command
from giki.llm.base import LLMResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_wiki_page(wiki_dir: Path, slug: str, title: str, body: str) -> None:
    """Write a minimal wiki page with valid frontmatter."""
    wiki_dir.mkdir(parents=True, exist_ok=True)
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
    (wiki_dir / f"{slug}.md").write_text(content, encoding="utf-8")


def _write_config(root: Path) -> None:
    """Write a minimal .giki/config.yaml."""
    giki_dir = root / ".giki"
    giki_dir.mkdir(parents=True, exist_ok=True)
    config_content = (
        "llm:\n"
        "  compile:\n"
        "    provider: openai\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: TEST_OPENAI_KEY\n"
        "  review:\n"
        "    provider: openai\n"
        "    model: gpt-4\n"
        "    base_url: https://api.openai.com/v1\n"
        "    api_key_env: TEST_OPENAI_KEY\n"
    )
    (giki_dir / "config.yaml").write_text(config_content, encoding="utf-8")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Tests: RAG prompt builder
# ---------------------------------------------------------------------------


class TestBuildRagPrompt:
    def test_with_context_pages(self):
        pages = [
            ("Page A", "Body of page A"),
            ("Page B", "Body of page B"),
        ]
        system, user = _build_rag_prompt(pages, "What is X?")
        assert "knowledge base assistant" in system
        assert "## Context" in user
        assert "### Page: Page A" in user
        assert "Body of page A" in user
        assert "### Page: Page B" in user
        assert "Question: What is X?" in user
        assert "clear, concise answer" in user

    def test_without_context_pages(self):
        system, user = _build_rag_prompt([], "What is X?")
        assert "knowledge base assistant" in system
        assert "No relevant wiki pages" in user
        assert "Question: What is X?" in user


# ---------------------------------------------------------------------------
# Tests: CLI help
# ---------------------------------------------------------------------------


class TestChatCLIHelp:
    def test_chat_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        out = result.stdout
        assert "--top-k" in out
        assert "--root" in out

    def test_chat_listed_in_main_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "chat" in result.stdout


# ---------------------------------------------------------------------------
# Tests: single-query mode (mocked LLM)
# ---------------------------------------------------------------------------


class TestChatSingleQuery:
    def test_chat_single_question(self, runner: CliRunner, tmp_path: Path) -> None:
        wiki_dir = tmp_path / "wiki"
        _write_wiki_page(wiki_dir, "test-page", "Test Page", "This is about testing.")
        _write_config(tmp_path)

        # Build a search index
        from giki.search import SearchIndex

        idx = SearchIndex(tmp_path)
        idx.build(wiki_dir)
        idx.save()

        fake_response = LLMResponse(text="The answer is 42.")
        fake_client = MagicMock()
        fake_client.chat.return_value = fake_response

        with patch("giki.llm.build_client", return_value=fake_client):
            result = runner.invoke(
                app,
                ["chat", "What is testing?", "--root", str(tmp_path)],
            )

        assert result.exit_code == 0, result.output
        assert "42" in result.stdout
        fake_client.chat.assert_called_once()

    def test_chat_single_question_no_index(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Index should be built on the fly if missing."""
        wiki_dir = tmp_path / "wiki"
        _write_wiki_page(wiki_dir, "hello", "Hello", "World.")
        _write_config(tmp_path)

        fake_response = LLMResponse(text="Hello world!")
        fake_client = MagicMock()
        fake_client.chat.return_value = fake_response

        with patch("giki.llm.build_client", return_value=fake_client):
            result = runner.invoke(
                app,
                ["chat", "What is hello?", "--root", str(tmp_path)],
            )

        assert result.exit_code == 0, result.output
        assert "Hello world" in result.stdout

    def test_chat_single_question_error_exit(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """LLM failure should exit with code 1."""
        _write_config(tmp_path)
        (tmp_path / "wiki").mkdir()

        with patch(
            "giki.llm.build_client",
            side_effect=RuntimeError("API key missing"),
        ):
            result = runner.invoke(
                app,
                ["chat", "fail?", "--root", str(tmp_path)],
            )

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Tests: REPL mode
# ---------------------------------------------------------------------------


class TestChatREPL:
    def test_chat_repl_eof(self, runner: CliRunner, tmp_path: Path) -> None:
        """REPL should exit gracefully on EOF (empty input)."""
        wiki_dir = tmp_path / "wiki"
        _write_wiki_page(wiki_dir, "page", "Page", "Content.")
        _write_config(tmp_path)

        fake_response = LLMResponse(text="Answer!")
        fake_client = MagicMock()
        fake_client.chat.return_value = fake_response

        with patch("giki.llm.build_client", return_value=fake_client):
            result = runner.invoke(
                app,
                ["chat", "--root", str(tmp_path)],
                input="What?\n",
            )

        assert result.exit_code == 0
        assert "Answer!" in result.stdout

    def test_chat_repl_empty_lines_skipped(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Empty input lines should be ignored in REPL mode."""
        wiki_dir = tmp_path / "wiki"
        _write_wiki_page(wiki_dir, "page", "Page", "Content.")
        _write_config(tmp_path)

        fake_response = LLMResponse(text="Yes.")
        fake_client = MagicMock()
        fake_client.chat.return_value = fake_response

        with patch("giki.llm.build_client", return_value=fake_client):
            result = runner.invoke(
                app,
                ["chat", "--root", str(tmp_path)],
                input="\n\nQuestion?\n",
            )

        assert result.exit_code == 0
        # LLM should be called once, not three times
        assert fake_client.chat.call_count == 1
