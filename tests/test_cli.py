"""Tests for the top-level ``giki`` Typer app and ``giki ingest`` command."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.orchestrator import IngestResult

# Typer/rich may inject ANSI color codes in CI, splitting e.g. "--branch"
# into "\x1b[1;36m-\x1b[1;36m-branch\x1b[0m".  Strip before substring checks.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Top-level help / registered commands
# ---------------------------------------------------------------------------


class TestTopLevelHelp:
    def test_help_lists_v01_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        for name in ("init", "ingest", "config", "review", "lint", "mcp-serve"):
            assert name in out, f"expected {name!r} in help output:\n{out}"


class TestVersionFlag:
    def test_version_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0, result.output
        from giki import __version__

        assert __version__ in result.stdout


# ---------------------------------------------------------------------------
# giki ingest — help + validation
# ---------------------------------------------------------------------------


class TestIngestHelp:
    def test_ingest_help_shows_flags(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        for flag in ("--branch", "--yes", "--dry-run", "--retry-failed"):
            assert flag in out, f"expected flag {flag!r} in ingest --help:\n{out}"


class TestIngestPathValidation:
    def test_ingest_nonexistent_path_errors(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nonexistent-file.md"
        result = runner.invoke(app, ["ingest", str(missing)])
        assert result.exit_code != 0
        combined = result.output or ""
        assert (
            str(missing) in combined
            or "nonexistent-file.md" in combined
            or "does not exist" in combined.lower()
        )


# ---------------------------------------------------------------------------
# giki ingest --dry-run delegates to Ingester.ingest
# ---------------------------------------------------------------------------


class TestIngestDelegation:
    def test_ingest_dry_run_prints_candidates_without_writing(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        source = tmp_path / "src.md"
        source.write_text("# hello\n", encoding="utf-8")

        fake_result = IngestResult(
            source_path=source,
            branch=None,
            created=[],
            updated=[],
            failed=[],
            commit_sha=None,
            skipped=False,
        )

        with patch("giki.commands.ingest.load_config") as m_load, patch(
            "giki.commands.ingest.Ingester"
        ) as m_ingester_cls:
            import types

            m_load.return_value = types.SimpleNamespace(pricing={})
            m_ingester = m_ingester_cls.return_value
            m_ingester.ingest.return_value = fake_result

            result = runner.invoke(
                app,
                ["ingest", str(source), "--dry-run", "--root", str(tmp_path)],
            )

        assert result.exit_code == 0, result.output
        assert m_ingester.ingest.called
        _, kwargs = m_ingester.ingest.call_args
        assert kwargs.get("dry_run") is True
        assert (
            "1 source(s) processed" in result.stdout
            and "0 page(s) created" in result.stdout
        )
