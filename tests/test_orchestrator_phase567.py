import json
from pathlib import Path

import pytest
import git

from giki.config import load_config
from giki.llm.base import LLMAdapter, LLMError, LLMResponse, Message
from giki.orchestrator import Ingester, SuggestedPage, IngestResult
from giki.sources.loader import load_source
from giki.wiki.parser import parse_page
from giki.wiki.store import WikiStore


VALID_CFG_YAML = """
llm:
  compile:
    provider: claude
    model: m
    base_url: https://x
    api_key_env: TEST_KEY
  review:
    provider: claude
    model: m
    base_url: https://x
    api_key_env: TEST_KEY
ingest:
  chunk_size: 100
  chunk_overlap: 20
  synthesize_context: 200
wiki:
  related_min_neighbors: 1
"""


def _init_giki(tmp_path):
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.co").release()
    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(VALID_CFG_YAML, encoding="utf-8")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "README.md").write_text("# t\n", encoding="utf-8")
    repo.index.add([".giki/config.yaml", "README.md"])
    repo.index.commit("initial")
    return load_config(tmp_path)


class FakeLLM(LLMAdapter):
    provider = "fake"
    model = "fake-m"
    name = "fake:fake-m"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        self.calls.append(list(messages))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return LLMResponse(text=r, finish_reason="stop")


def _loaded(tmp_path, text="source content"):
    p = tmp_path / "src.md"
    p.write_text(text, encoding="utf-8")
    return load_source(p)


def _write_page(store, slug, title, body="body."):
    content = f"""---
title: {title}
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
sources:
  - path: sources/x.md
---

# {title}

{body}
"""
    store.write(slug, content)


class TestCrosslink:
    def test_related_block_added(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "a", "A")
        _write_page(store, "b", "B")
        _write_page(store, "c", "C")

        # LLM says c has neighbors a and b
        llm = FakeLLM([
            json.dumps({"neighbors": ["a", "b"], "inline_hints": []})
        ])

        ing = Ingester(cfg)
        succeeded, failed = ing.crosslink(["c"], llm_client=llm)
        assert succeeded == ["c"]
        assert failed == []

        content = store.read("c")
        assert "## Related" in content
        assert "- [[a]]" in content
        assert "- [[b]]" in content

    def test_inline_hints_applied_when_target_resolves(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "observer", "Observer")
        _write_page(store, "topic", "Topic", body="Body mentions observer pattern here.")

        llm = FakeLLM([json.dumps({
            "neighbors": [],  # will not create Related block (min=1)
            "inline_hints": [{"phrase": "observer pattern", "target": "observer"}],
        })])

        ing = Ingester(cfg)
        ing.crosslink(["topic"], llm_client=llm)
        content = store.read("topic")
        # phrase should now be a wikilink
        assert "[[observer]]" in content or "[[observer|observer pattern]]" in content

    def test_inline_hint_skipped_when_target_unresolved(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "topic", "Topic", body="Body mentions nonexistent thing here.")

        llm = FakeLLM([json.dumps({
            "neighbors": [],
            "inline_hints": [{"phrase": "nonexistent thing", "target": "does-not-exist"}],
        })])

        ing = Ingester(cfg)
        ing.crosslink(["topic"], llm_client=llm)
        content = store.read("topic")
        # No wikilink should have been inserted for the unresolved target
        assert "[[does-not-exist]]" not in content

    def test_below_min_neighbors_no_related_block(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "lonely", "Lonely")

        llm = FakeLLM([json.dumps({"neighbors": [], "inline_hints": []})])

        ing = Ingester(cfg)
        ing.crosslink(["lonely"], llm_client=llm)
        content = store.read("lonely")
        assert "## Related" not in content

    def test_llm_error_recorded_as_failure(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "a", "A")

        llm = FakeLLM([LLMError("blown", retryable=False)])
        ing = Ingester(cfg)
        succeeded, failed = ing.crosslink(["a"], llm_client=llm)
        assert succeeded == []
        assert failed == ["a"]

    def test_neighbors_filtered_to_resolvable_only(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "a", "A")
        _write_page(store, "b", "B")

        # LLM suggests one existing and one nonexistent neighbor
        llm = FakeLLM([json.dumps({
            "neighbors": ["b", "ghost"],
            "inline_hints": [],
        })])

        ing = Ingester(cfg)
        ing.crosslink(["a"], llm_client=llm)
        content = store.read("a")
        assert "[[b]]" in content
        assert "ghost" not in content


class TestUpdateIndexAndLog:
    def test_creates_index_and_log(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "a", "Alpha")

        src = _loaded(tmp_path)
        ing = Ingester(cfg)
        ing.update_index_and_log(
            src, created=["a"], updated=[], failed=[],
            timestamp_iso="2026-06-30T14:00:00+08:00",
        )
        index_content = (cfg.root / "index.md").read_text(encoding="utf-8")
        log_content = (cfg.root / "log.md").read_text(encoding="utf-8")
        assert "[[a]] \u2014 Alpha" in index_content
        assert "created: [[a]]" in log_content
        assert "src.md" in log_content

    def test_state_updated_with_pages(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "a", "A")
        _write_page(store, "b", "B")
        src = _loaded(tmp_path)

        ing = Ingester(cfg)
        ing.update_index_and_log(
            src, created=["a"], updated=["b"], failed=[],
            timestamp_iso="2026-06-30T14:00:00+08:00",
        )
        from giki.sources.state import SourceState
        state = SourceState.load(cfg.root)
        assert set(state.pages_for(src.path)) == {"a", "b"}


class TestCommit:
    def test_commits_with_summary_message(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "a", "Alpha")

        src = _loaded(tmp_path)
        ing = Ingester(cfg)
        # Set up state/index/log first
        ing.update_index_and_log(src, created=["a"], updated=[], failed=[], timestamp_iso="2026-06-30T14:00:00+08:00")

        repo = git.Repo(cfg.root)
        commit = ing.commit(repo, src, created=["a"], updated=[], failed=[])
        assert commit is not None
        assert "ingest:" in commit.message
        assert "src.md" in commit.message
        assert "1 of 1" in commit.message

    def test_commit_message_reflects_failures(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        _write_page(store, "ok", "Ok")

        src = _loaded(tmp_path)
        ing = Ingester(cfg)
        ing.update_index_and_log(src, created=["ok"], updated=[], failed=["bad"], timestamp_iso="2026-06-30T14:00:00+08:00")

        repo = git.Repo(cfg.root)
        commit = ing.commit(repo, src, created=["ok"], updated=[], failed=["bad"])
        assert "1 of 2" in commit.message
        assert "1 failed" in commit.message


class TestFullIngest:
    def test_end_to_end_ingest(self, tmp_path):
        cfg = _init_giki(tmp_path)
        sources_dir = tmp_path / "sources"
        sources_dir.mkdir(exist_ok=True)
        src_path = sources_dir / "src.md"
        src_path.write_text("Some content about observer pattern.", encoding="utf-8")

        analyze_resp = json.dumps({
            "suggested_pages": [
                {"filename": "observer", "title": "Observer", "action": "create",
                 "hints": ["describe"], "source_anchors": ["chunk 1"], "aliases_suggested": []}
            ]
        })
        synth_resp = "# Observer\n\nBody content."
        crosslink_resp = json.dumps({"neighbors": [], "inline_hints": []})
        llm = FakeLLM([analyze_resp, synth_resp, crosslink_resp])

        ing = Ingester(cfg)
        result = ing.ingest(
            src_path,
            branch="wiki/observer",
            yes=True,
            dry_run=False,
            llm_client=llm,
        )
        assert isinstance(result, IngestResult)
        assert result.branch == "wiki/observer"
        assert "observer" in result.created
        assert result.failed == []
        assert result.commit_sha is not None
        assert result.skipped is False

        # Verify side effects
        store = WikiStore(cfg.root)
        assert store.exists("observer")
        assert (cfg.root / "index.md").exists()
        assert (cfg.root / "log.md").exists()

        # Verify commit exists on the correct branch
        repo = git.Repo(cfg.root)
        assert repo.active_branch.name == "wiki/observer"
        assert result.commit_sha == repo.head.commit.hexsha

    def test_ingest_hash_short_circuit(self, tmp_path):
        cfg = _init_giki(tmp_path)
        sources_dir = tmp_path / "sources"
        sources_dir.mkdir(exist_ok=True)
        src_path = sources_dir / "src.md"
        src_path.write_text("stable content", encoding="utf-8")

        # First run: analyze + synth + crosslink
        llm1 = FakeLLM([
            json.dumps({"suggested_pages": [{
                "filename": "s", "title": "S", "action": "create",
                "hints": [], "source_anchors": [], "aliases_suggested": [],
            }]}),
            "# S\n\nbody",
            json.dumps({"neighbors": [], "inline_hints": []}),
        ])
        ing1 = Ingester(cfg)
        r1 = ing1.ingest(src_path, branch=None, yes=True, dry_run=False, llm_client=llm1)
        assert r1.skipped is False

        # Second run: same file, hash unchanged -> skipped
        llm2 = FakeLLM([])  # no calls expected
        ing2 = Ingester(cfg)
        r2 = ing2.ingest(src_path, branch=None, yes=True, dry_run=False, llm_client=llm2)
        assert r2.skipped is True
        assert len(llm2.calls) == 0

    def test_ingest_dry_run_no_commit(self, tmp_path):
        cfg = _init_giki(tmp_path)
        sources_dir = tmp_path / "sources"
        sources_dir.mkdir(exist_ok=True)
        src_path = sources_dir / "src.md"
        src_path.write_text("content", encoding="utf-8")

        llm = FakeLLM([json.dumps({
            "suggested_pages": [{"filename": "x", "title": "X", "action": "create",
                                 "hints": [], "source_anchors": [], "aliases_suggested": []}]
        })])
        ing = Ingester(cfg)
        result = ing.ingest(src_path, branch=None, yes=False, dry_run=True, llm_client=llm)
        assert result.commit_sha is None
        assert result.created == []
        # No wiki file should be written
        assert not WikiStore(cfg.root).exists("x")
