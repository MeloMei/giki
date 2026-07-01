import pytest
from pathlib import Path

import git
import yaml

from giki.config import load_config, Config
from giki.orchestrator import Ingester


VALID_CFG_YAML = """
llm:
  compile:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: TEST_KEY
  review:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: TEST_KEY
"""


def _init_giki_repo(tmp_path: Path) -> Config:
    """Init a fresh git repo with a valid .giki/config.yaml."""
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(VALID_CFG_YAML, encoding="utf-8")
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    repo.index.add([".giki/config.yaml", "README.md"])
    repo.index.commit("initial")
    return load_config(tmp_path)


class TestBootstrap:
    def test_opens_repo_and_returns_it(self, tmp_path):
        cfg = _init_giki_repo(tmp_path)
        ing = Ingester(cfg)
        repo = ing.bootstrap(branch=None)
        assert repo.active_branch.name == "main"

    def test_creates_and_switches_branch(self, tmp_path):
        cfg = _init_giki_repo(tmp_path)
        ing = Ingester(cfg)
        repo = ing.bootstrap(branch="wiki/foo")
        assert repo.active_branch.name == "wiki/foo"

    def test_refuses_dirty_worktree(self, tmp_path):
        from giki.git_utils import GitError
        cfg = _init_giki_repo(tmp_path)
        (tmp_path / "dirty.txt").write_text("x", encoding="utf-8")
        ing = Ingester(cfg)
        with pytest.raises(GitError):
            ing.bootstrap(branch="wiki/foo")


class TestLoadSource:
    def test_new_source_needs_ingest(self, tmp_path):
        cfg = _init_giki_repo(tmp_path)
        src = tmp_path / "note.md"
        src.write_text("# Hello", encoding="utf-8")
        ing = Ingester(cfg)
        loaded, needs = ing.load_source(src)
        assert loaded.text == "# Hello"
        assert needs is True

    def test_unchanged_source_skipped(self, tmp_path):
        """Second load with same hash returns needs=False."""
        cfg = _init_giki_repo(tmp_path)
        src = tmp_path / "note.md"
        src.write_text("stable", encoding="utf-8")

        ing = Ingester(cfg)
        loaded, needs = ing.load_source(src)
        assert needs is True

        # Simulate a "successful ingest" by marking the state
        from giki.sources.state import SourceState
        state = SourceState.load(cfg.root)
        state.mark(src, loaded.sha256, pages=["fake-page"])
        state.save()

        # New Ingester instance re-reads state
        ing2 = Ingester(cfg)
        loaded2, needs2 = ing2.load_source(src)
        assert needs2 is False

    def test_changed_source_needs_ingest_again(self, tmp_path):
        cfg = _init_giki_repo(tmp_path)
        src = tmp_path / "note.md"
        src.write_text("v1", encoding="utf-8")

        ing = Ingester(cfg)
        loaded_v1, _ = ing.load_source(src)

        # Mark v1 hash as done
        from giki.sources.state import SourceState
        state = SourceState.load(cfg.root)
        state.mark(src, loaded_v1.sha256, pages=[])
        state.save()

        # Modify source
        src.write_text("v2 different", encoding="utf-8")

        ing2 = Ingester(cfg)
        loaded_v2, needs_v2 = ing2.load_source(src)
        assert needs_v2 is True
        assert loaded_v2.sha256 != loaded_v1.sha256
