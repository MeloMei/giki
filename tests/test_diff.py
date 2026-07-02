"""Tests for diff extraction and change classification."""

from __future__ import annotations

import git
import pytest

from giki.diff import (
    classify_changes,
    get_diff_changes,
    parse_name_status,
    read_file_at_commit,
)
from giki.review_models import ChangeType, FileChange


class TestParseNameStatus:
    def test_added(self):
        assert parse_name_status("A\twiki/new.md\n")[0].change_type == ChangeType.NEW
    def test_modified(self):
        assert parse_name_status("M\twiki/x.md\n")[0].change_type == ChangeType.UPDATED
    def test_deleted(self):
        assert parse_name_status("D\twiki/old.md\n")[0].change_type == ChangeType.DELETED
    def test_renamed(self):
        c = parse_name_status("R100\twiki/old.md\twiki/new.md\n")[0]
        assert c.change_type == ChangeType.RENAMED
        assert c.old_path == "wiki/old.md"
    def test_multiple(self):
        assert len(parse_name_status("A\twiki/a.md\nM\twiki/b.md\nD\tindex.md\n")) == 3
    def test_empty(self):
        assert parse_name_status("") == []
    def test_rename_similarity_score(self):
        c = parse_name_status("R095\twiki/old.md\twiki/new.md\n")[0]
        assert c.change_type == ChangeType.RENAMED


class TestClassifyChanges:
    def test_wiki(self):
        assert len(classify_changes([FileChange("wiki/a.md", ChangeType.NEW)])["wiki"]) == 1
    def test_index(self):
        assert len(classify_changes([FileChange("index.md", ChangeType.UPDATED)])["index"]) == 1
    def test_rules(self):
        assert len(classify_changes([FileChange("wiki-rules.md", ChangeType.UPDATED)])["rules"]) == 1
    def test_other(self):
        assert len(classify_changes([FileChange("sources/x.md", ChangeType.NEW)])["other"]) == 1
    def test_mixed(self):
        changes = [
            FileChange("wiki/a.md", ChangeType.NEW),
            FileChange("index.md", ChangeType.UPDATED),
            FileChange("wiki-rules.md", ChangeType.UPDATED),
            FileChange("sources/x.md", ChangeType.NEW),
        ]
        c = classify_changes(changes)
        assert len(c["wiki"]) == 1 and len(c["index"]) == 1 and len(c["rules"]) == 1 and len(c["other"]) == 1


class TestGetDiffChanges:
    def test_branch_diff(self, tmp_path):
        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        (tmp_path / "base.md").write_text("base\n", encoding="utf-8")
        repo.index.add(["base.md"])
        repo.index.commit("initial")
        repo.create_head("feature").checkout()
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "new.md").write_text("new\n", encoding="utf-8")
        repo.index.add(["wiki/new.md"])
        repo.index.commit("add wiki page")
        changes = get_diff_changes(tmp_path, base="main")
        assert len(changes) == 1
        assert changes[0].path == "wiki/new.md"


class TestReadFileAtCommit:
    def test_read_existing(self, tmp_path):
        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "test.md").write_text("v1\n", encoding="utf-8")
        repo.index.add(["wiki/test.md"])
        commit = repo.index.commit("add test")
        assert "v1" in read_file_at_commit(tmp_path, "wiki/test.md", commit.hexsha)
    def test_nonexistent_returns_none(self, tmp_path):
        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        (tmp_path / "base.md").write_text("x\n", encoding="utf-8")
        repo.index.add(["base.md"])
        commit = repo.index.commit("initial")
        assert read_file_at_commit(tmp_path, "wiki/nope.md", commit.hexsha) is None
