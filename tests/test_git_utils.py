import pytest
from pathlib import Path

import git

from giki.git_utils import (
    open_repo, ensure_clean_worktree, checkout_branch, add_and_commit, GitError,
)


def _init_repo(path: Path) -> git.Repo:
    """Init a repo with one initial commit so branches can be created."""
    repo = git.Repo.init(path, initial_branch="main")
    # Configure user for the test
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    # Make an initial commit
    readme = path / "README.md"
    readme.write_text("# test\n", encoding="utf-8")
    repo.index.add([str(readme)])
    repo.index.commit("initial")
    return repo


class TestOpenRepo:
    def test_opens_existing_repo(self, tmp_path):
        _init_repo(tmp_path)
        repo = open_repo(tmp_path)
        assert repo.working_dir == str(tmp_path)

    def test_not_a_repo_raises(self, tmp_path):
        # open_repo searches parent dirs, so on systems where tmp_path
        # lives under a git repo it will succeed.  We only assert the
        # "not a git repo" error when no parent repo is found.
        try:
            repo = open_repo(tmp_path)
        except GitError as exc:
            assert "not a git repo" in str(exc)
        else:
            # A parent repo was found — just verify it's not at tmp_path.
            assert Path(repo.working_dir).resolve() != tmp_path.resolve()


class TestEnsureCleanWorktree:
    def test_clean_worktree_ok(self, tmp_path):
        repo = _init_repo(tmp_path)
        ensure_clean_worktree(repo)  # no raise

    def test_dirty_modified_file_raises(self, tmp_path):
        repo = _init_repo(tmp_path)
        (tmp_path / "README.md").write_text("modified\n", encoding="utf-8")
        with pytest.raises(GitError, match="dirty|modified"):
            ensure_clean_worktree(repo)

    def test_untracked_file_raises(self, tmp_path):
        repo = _init_repo(tmp_path)
        (tmp_path / "new.txt").write_text("x", encoding="utf-8")
        with pytest.raises(GitError):
            ensure_clean_worktree(repo)

    def test_giki_state_untracked_allowed(self, tmp_path):
        """Files under .giki-state/ are allowed to be untracked (state is regeneratable)."""
        repo = _init_repo(tmp_path)
        state_dir = tmp_path / ".giki-state"
        state_dir.mkdir()
        (state_dir / "sources.json").write_text("{}", encoding="utf-8")
        # Should NOT raise
        ensure_clean_worktree(repo)


class TestCheckoutBranch:
    def test_creates_new_branch(self, tmp_path):
        repo = _init_repo(tmp_path)
        checkout_branch(repo, "feature/x", create=True)
        assert repo.active_branch.name == "feature/x"

    def test_switches_to_existing_branch(self, tmp_path):
        repo = _init_repo(tmp_path)
        repo.create_head("existing")
        checkout_branch(repo, "existing", create=True)  # create=True still ok if exists
        assert repo.active_branch.name == "existing"

    def test_refuses_if_dirty(self, tmp_path):
        repo = _init_repo(tmp_path)
        (tmp_path / "dirty.txt").write_text("x", encoding="utf-8")
        with pytest.raises(GitError):
            checkout_branch(repo, "feature/y")


class TestAddAndCommit:
    def test_stages_and_commits(self, tmp_path):
        repo = _init_repo(tmp_path)
        new_file = tmp_path / "new.txt"
        new_file.write_text("hello\n", encoding="utf-8")
        commit = add_and_commit(repo, [new_file], "add new.txt")
        assert commit.message.strip() == "add new.txt"
        committed_paths = list(commit.stats.files.keys())
        assert "new.txt" in committed_paths

    def test_returns_commit_object(self, tmp_path):
        repo = _init_repo(tmp_path)
        (tmp_path / "x.txt").write_text("x", encoding="utf-8")
        commit = add_and_commit(repo, ["x.txt"], "add x")
        assert commit is not None
        assert commit.hexsha  # SHA is set
