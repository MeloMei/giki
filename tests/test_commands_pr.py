"""Tests for `giki pr create / list / review / merge` commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import git
import pytest
from typer.testing import CliRunner

from giki.commands.pr import pr_app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _init_repo(path: Path) -> git.Repo:
    """Create a git repo with an initial commit so HEAD is valid."""
    repo = git.Repo.init(str(path))
    dummy = path / "README.md"
    dummy.write_text("# test\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("initial commit")
    return repo


class TestGhRequired:
    def test_create_without_gh_fails(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda _: None)
        result = runner.invoke(pr_app, ["create", "--title", "test"])
        assert result.exit_code != 0

    def test_list_without_gh_fails(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda _: None)
        result = runner.invoke(pr_app, ["list"])
        assert result.exit_code != 0

    def test_merge_without_gh_fails(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda _: None)
        result = runner.invoke(pr_app, ["merge", "1"])
        assert result.exit_code != 0


class TestPrCreate:
    def test_create_success(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda x: "/usr/bin/gh")

        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = "https://github.com/owner/repo/pull/42\n"
        fake.stderr = ""
        monkeypatch.setattr("giki.commands.pr.subprocess.run", lambda *a, **kw: fake)

        result = runner.invoke(
            pr_app, ["create", "--title", "My PR", "--body", "desc"]
        )
        assert result.exit_code == 0, result.output
        assert "pull request created" in result.output.lower() or "42" in result.output

    def test_create_failure(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda x: "/usr/bin/gh")

        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ""
        fake.stderr = "error: no commits between main and feature"
        monkeypatch.setattr("giki.commands.pr.subprocess.run", lambda *a, **kw: fake)

        result = runner.invoke(
            pr_app, ["create", "--title", "My PR"]
        )
        assert result.exit_code != 0


class TestPrList:
    def test_list_success(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda x: "/usr/bin/gh")

        pr_data = [
            {
                "number": 1,
                "title": "First PR",
                "author": {"login": "alice"},
                "state": "OPEN",
                "url": "https://github.com/owner/repo/pull/1",
            },
            {
                "number": 2,
                "title": "Second PR",
                "author": {"login": "bob"},
                "state": "MERGED",
                "url": "https://github.com/owner/repo/pull/2",
            },
        ]

        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = json.dumps(pr_data)
        fake.stderr = ""
        monkeypatch.setattr("giki.commands.pr.subprocess.run", lambda *a, **kw: fake)

        result = runner.invoke(pr_app, ["list"])
        assert result.exit_code == 0, result.output
        assert "First PR" in result.output
        assert "Second PR" in result.output

    def test_list_empty(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda x: "/usr/bin/gh")

        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = "[]"
        fake.stderr = ""
        monkeypatch.setattr("giki.commands.pr.subprocess.run", lambda *a, **kw: fake)

        result = runner.invoke(pr_app, ["list"])
        assert result.exit_code == 0, result.output
        assert "no pull requests" in result.output.lower()

    def test_list_with_state_filter(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda x: "/usr/bin/gh")

        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = "[]"
        fake.stderr = ""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return fake

        monkeypatch.setattr("giki.commands.pr.subprocess.run", fake_run)

        result = runner.invoke(pr_app, ["list", "--state", "merged"])
        assert result.exit_code == 0
        assert "--state" in captured["cmd"]
        assert "merged" in captured["cmd"]


class TestPrMerge:
    def test_merge_success(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda x: "/usr/bin/gh")

        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = ""
        fake.stderr = ""
        monkeypatch.setattr("giki.commands.pr.subprocess.run", lambda *a, **kw: fake)

        result = runner.invoke(pr_app, ["merge", "42"])
        assert result.exit_code == 0, result.output
        assert "42" in result.output

    def test_merge_failure(self, runner, monkeypatch):
        monkeypatch.setattr("giki.commands.pr.shutil.which", lambda x: "/usr/bin/gh")

        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ""
        fake.stderr = "error: PR is not mergeable"
        monkeypatch.setattr("giki.commands.pr.subprocess.run", lambda *a, **kw: fake)

        result = runner.invoke(pr_app, ["merge", "42"])
        assert result.exit_code != 0


class TestPrReview:
    def test_review_delegates_to_review_command(self, runner, monkeypatch, tmp_path):
        _init_repo(tmp_path)
        called_with = {}

        def fake_review(**kwargs):
            called_with.update(kwargs)

        # Mock at the source module since pr.py uses a local import
        monkeypatch.setattr("giki.commands.review.review_command", fake_review)

        result = runner.invoke(pr_app, ["review", "7", "--root", str(tmp_path)])
        # review_command was called with pr=7
        assert called_with.get("pr") == 7
