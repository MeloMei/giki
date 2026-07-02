"""Tests for the top-level ``giki`` Typer app and ``giki ingest`` command."""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.orchestrator import IngestResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Top-level help / registered commands
# ---------------------------------------------------------------------------


class TestTopLevelHelp:
    def test_help_lists_v01_commands(self, runner: CliRunner) -> None:
        import re

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0, result.output
        out = result.stdout
        for name in ("init", "ingest", "config", "review"):
            assert name in out, f"expected {name!r} in help output:\n{out}"
        for name in ("lint", "merge", "collab", "serve", "chat", "fusion"):
            # word-boundary match so unrelated words like 'preserve' don't trigger
            assert not re.search(rf"\b{name}\b", out), (
                f"did not expect standalone {name!r} in v0.1 help:\n{out}"
            )


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
        out = result.stdout
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
            m_load.return_value = object()
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
            "1 sources processed, 0 pages created, 0 pages updated, 0 pages failed"
            in result.stdout
        )


# ---------------------------------------------------------------------------
# Stub modules — parametrized
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mod_name",
    ["lint", "merge", "collab", "serve", "chat", "fusion"],
)
def test_stub_modules_raise_notimplementederror(mod_name: str) -> None:
    mod = importlib.import_module(f"giki.commands.{mod_name}")
    assert callable(mod.app), f"expected {mod_name}.app to be callable"
    with pytest.raises(NotImplementedError):
        mod.app()
