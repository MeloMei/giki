"""Tests for `giki init` — scaffolding a new knowledge base directory."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import git

from giki.commands.init import init_app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _read(p: Path) -> str:
    """Read file, normalizing Windows line endings."""
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def _init_git_repo(path: Path) -> None:
    git.Repo.init(str(path))


class TestInitBasics:
    def test_init_creates_all_files_on_empty_dir(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        result = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert result.exit_code == 0, result.output

        assert (tmp_path / ".giki" / "config.yaml").exists()
        assert (tmp_path / "wiki-rules.md").exists()
        assert (tmp_path / "index.md").exists()
        assert (tmp_path / "log.md").exists()
        assert (tmp_path / "README.md").exists()
        assert (tmp_path / ".gitignore").exists()

        cfg_text = _read(tmp_path / ".giki" / "config.yaml")
        cfg = yaml.safe_load(cfg_text)
        assert cfg["llm"]["compile"]["provider"] == "claude"
        assert cfg["ingest"]["chunk_size"] == 12000
        assert cfg["review"]["severity_blocking"] == ["blocker"]

        index_text = _read(tmp_path / "index.md")
        assert "<!-- giki:index-begin -->" in index_text
        assert "<!-- giki:index-end -->" in index_text

        log_text = _read(tmp_path / "log.md")
        assert log_text.startswith("# Log")

        rules_text = _read(tmp_path / "wiki-rules.md")
        assert "## R-1" in rules_text
        assert "## R-2" in rules_text
        assert "## R-5" in rules_text

        gi_text = _read(tmp_path / ".gitignore")
        assert ".giki-state/*.json" in gi_text

        readme_text = _read(tmp_path / "README.md")
        assert "giki" in readme_text.lower()

    def test_init_creates_all_directories(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        result = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert result.exit_code == 0

        assert (tmp_path / ".giki").is_dir()
        assert (tmp_path / "sources").is_dir()
        assert (tmp_path / "wiki").is_dir()
        assert (tmp_path / ".giki-state").is_dir()

    def test_init_is_idempotent(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        r1 = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert r1.exit_code == 0, r1.stdout

        # Modify config to prove it's not overwritten
        cfg_path = tmp_path / ".giki" / "config.yaml"
        cfg_path.write_text("marker: mine\n", encoding="utf-8")

        r2 = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert r2.exit_code == 0, r2.stdout
        assert "kept" in r2.stdout

        # File was not overwritten
        assert _read(cfg_path) == "marker: mine\n"


class TestGitInit:
    def test_init_non_git_dir_with_yes_runs_git_init(self, tmp_path, runner, monkeypatch):
        # Force TTY so the confirm prompt is reached; feed 'y' to accept.
        monkeypatch.setattr("giki.commands.init._stdin_is_tty", lambda: True)
        result = runner.invoke(init_app, ["--root", str(tmp_path)], input="y\n")
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".git").exists()
        assert (tmp_path / ".giki" / "config.yaml").exists()

    def test_init_non_git_dir_with_no_aborts(self, tmp_path, runner, monkeypatch):
        # Force TTY so the confirm prompt is reached; feed 'n' to decline.
        monkeypatch.setattr("giki.commands.init._stdin_is_tty", lambda: True)
        result = runner.invoke(init_app, ["--root", str(tmp_path)], input="n\n")
        assert result.exit_code == 1
        assert not (tmp_path / ".git").exists()
        assert not (tmp_path / ".giki").exists()


class TestActionWorkflow:
    def test_init_with_action_creates_workflow(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        result = runner.invoke(init_app, ["--root", str(tmp_path), "--with-action"])
        assert result.exit_code == 0, result.stdout

        wf = tmp_path / ".github" / "workflows" / "giki-review.yml"
        assert wf.exists()
        text = _read(wf)
        assert "giki review --pr" in text

    def test_init_without_action_skips_workflow(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        result = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert result.exit_code == 0

        wf = tmp_path / ".github" / "workflows" / "giki-review.yml"
        assert not wf.exists()


class TestNextSteps:
    def test_init_prints_next_steps(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        result = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert result.exit_code == 0
        assert "giki ingest" in result.stdout
        assert "Next Steps" in result.stdout or "Next steps" in result.stdout


class TestNonTTY:
    def test_init_non_tty_proceeds_without_confirm(self, tmp_path, runner, monkeypatch):
        # Simulate non-TTY on a non-git directory. Init should proceed without
        # prompting and without exiting with code 1.
        monkeypatch.setattr("giki.commands.init._stdin_is_tty", lambda: False)
        result = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / ".git").exists()
        assert (tmp_path / ".giki" / "config.yaml").exists()


class TestPartialPreexistence:
    def test_init_partial_preexistence(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        # Pre-create some scaffolding files but not others.
        (tmp_path / "index.md").write_text("preexisting index\n", encoding="utf-8")
        (tmp_path / "README.md").write_text("preexisting readme\n", encoding="utf-8")

        result = runner.invoke(init_app, ["--root", str(tmp_path)])
        assert result.exit_code == 0, result.output

        # config.yaml should be created; index.md and README.md should be kept.
        assert "created" in result.stdout
        assert str(tmp_path / ".giki" / "config.yaml") in result.stdout
        assert "kept" in result.stdout
        assert str(tmp_path / "index.md") in result.stdout
        assert str(tmp_path / "README.md") in result.stdout


class TestWithActionIdempotent:
    def test_init_with_action_idempotent(self, tmp_path, runner):
        _init_git_repo(tmp_path)
        r1 = runner.invoke(init_app, ["--root", str(tmp_path), "--with-action"])
        assert r1.exit_code == 0, r1.output

        r2 = runner.invoke(init_app, ["--root", str(tmp_path), "--with-action"])
        assert r2.exit_code == 0, r2.output
        wf_path = tmp_path / ".github" / "workflows" / "giki-review.yml"
        assert wf_path.exists()
        assert "kept" in r2.stdout and str(wf_path) in r2.stdout
