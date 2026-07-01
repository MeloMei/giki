import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

# The subcommand app is exposed at giki.commands.config_cmd.config_app
from giki.commands.config_cmd import config_app


VALID_YAML = """
llm:
  compile:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
  review:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
"""


def _setup_giki_dir(tmp_path: Path) -> Path:
    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(VALID_YAML, encoding="utf-8")
    return tmp_path


runner = CliRunner()


class TestShow:
    def test_prints_top_level_keys(self, tmp_path):
        root = _setup_giki_dir(tmp_path)
        result = runner.invoke(config_app, ["show", "--root", str(root)])
        assert result.exit_code == 0, result.output
        assert "llm" in result.output
        assert "compile" in result.output
        assert "review" in result.output
        assert "claude" in result.output

    def test_defaults_shown(self, tmp_path):
        root = _setup_giki_dir(tmp_path)
        result = runner.invoke(config_app, ["show", "--root", str(root)])
        assert result.exit_code == 0
        # Ingest defaults should appear since they have default values
        assert "chunk_size" in result.output


class TestSet:
    def test_update_scalar(self, tmp_path):
        root = _setup_giki_dir(tmp_path)
        result = runner.invoke(
            config_app, ["set", "ingest.chunk_size", "8000", "--root", str(root)]
        )
        assert result.exit_code == 0, result.output
        raw = (root / ".giki" / "config.yaml").read_text(encoding="utf-8")
        assert "chunk_size: 8000" in raw

    def test_update_nested_string(self, tmp_path):
        root = _setup_giki_dir(tmp_path)
        result = runner.invoke(
            config_app,
            ["set", "llm.compile.model", "claude-4-opus", "--root", str(root)],
        )
        assert result.exit_code == 0
        raw = (root / ".giki" / "config.yaml").read_text(encoding="utf-8")
        assert "claude-4-opus" in raw

    def test_update_bool(self, tmp_path):
        root = _setup_giki_dir(tmp_path)
        result = runner.invoke(
            config_app,
            ["set", "review.pr_comment_collapse", "false", "--root", str(root)],
        )
        assert result.exit_code == 0
        raw = (root / ".giki" / "config.yaml").read_text(encoding="utf-8")
        # yaml should serialize as `false`
        assert "pr_comment_collapse: false" in raw

    def test_reject_missing_config_file(self, tmp_path):
        """No .giki/config.yaml -> error clearly."""
        result = runner.invoke(
            config_app, ["set", "ingest.chunk_size", "100", "--root", str(tmp_path)]
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "no such" in result.output.lower()


class TestTips:
    def test_tips_prints_help(self):
        result = runner.invoke(config_app, ["tips"])
        assert result.exit_code == 0
        # Should mention the spec doc or key config sections
        assert "config" in result.output.lower()
        # Should mention llm.compile / llm.review as key hints
        assert "llm" in result.output
