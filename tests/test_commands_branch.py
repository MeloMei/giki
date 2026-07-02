"""Tests for `giki branch list / create / switch` commands."""

from __future__ import annotations

from pathlib import Path

import git
import pytest
from typer.testing import CliRunner

from giki.commands.branch import branch_app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init_repo(path: Path) -> git.Repo:
    """Create a git repo with an initial commit so HEAD is valid."""
    repo = git.Repo.init(str(path))
    # Need at least one commit for HEAD / active_branch to work
    dummy = path / "README.md"
    dummy.write_text("# test\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("initial commit")
    return repo


class TestBranchList:
    def test_list_shows_current_branch(self, tmp_path, runner):
        _init_repo(tmp_path)
        result = runner.invoke(branch_app, ["list", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        # Default branch (master or main) should be marked with *
        lines = result.output.strip().splitlines()
        starred = [l for l in lines if l.startswith("*")]
        assert len(starred) == 1

    def test_list_shows_all_branches(self, tmp_path, runner):
        repo = _init_repo(tmp_path)
        repo.create_head("feature-a")
        repo.create_head("feature-b")
        result = runner.invoke(branch_app, ["list", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "feature-a" in result.output
        assert "feature-b" in result.output

    def test_list_not_a_repo(self, runner, monkeypatch):
        from giki.git_utils import GitError
        def raise_git_error(*args, **kwargs):
            raise GitError("not a git repo")
        monkeypatch.setattr("giki.commands.branch.open_repo", raise_git_error)
        result = runner.invoke(branch_app, ["list", "--root", "/nonexistent"])
        assert result.exit_code != 0


class TestBranchCreate:
    def test_create_new_branch(self, tmp_path, runner):
        repo = _init_repo(tmp_path)
        result = runner.invoke(
            branch_app, ["create", "my-feature", "--root", str(tmp_path)]
        )
        assert result.exit_code == 0, result.output
        assert "my-feature" in result.output
        # Should now be on the new branch
        assert repo.active_branch.name == "my-feature"

    def test_create_existing_branch_fails(self, tmp_path, runner):
        repo = _init_repo(tmp_path)
        repo.create_head("existing")
        result = runner.invoke(
            branch_app, ["create", "existing", "--root", str(tmp_path)]
        )
        assert result.exit_code != 0

    def test_create_not_a_repo(self, runner, monkeypatch):
        from giki.git_utils import GitError
        def raise_git_error(*args, **kwargs):
            raise GitError("not a git repo")
        monkeypatch.setattr("giki.commands.branch.open_repo", raise_git_error)
        result = runner.invoke(
            branch_app, ["create", "my-feature", "--root", "/nonexistent"]
        )
        assert result.exit_code != 0


class TestBranchSwitch:
    def test_switch_to_existing_branch(self, tmp_path, runner):
        repo = _init_repo(tmp_path)
        repo.create_head("target")
        result = runner.invoke(
            branch_app, ["switch", "target", "--root", str(tmp_path)]
        )
        assert result.exit_code == 0, result.output
        assert "target" in result.output
        assert repo.active_branch.name == "target"

    def test_switch_nonexistent_branch_fails(self, tmp_path, runner):
        _init_repo(tmp_path)
        result = runner.invoke(
            branch_app, ["switch", "no-such-branch", "--root", str(tmp_path)]
        )
        assert result.exit_code != 0

    def test_switch_not_a_repo(self, runner, monkeypatch):
        from giki.git_utils import GitError
        def raise_git_error(*args, **kwargs):
            raise GitError("not a git repo")
        monkeypatch.setattr("giki.commands.branch.open_repo", raise_git_error)
        result = runner.invoke(
            branch_app, ["switch", "main", "--root", "/nonexistent"]
        )
        assert result.exit_code != 0
