import io
import json
from pathlib import Path

import pytest
import git

from giki.config import load_config
from giki.llm.base import LLMAdapter, LLMError, LLMResponse, Message
from giki.orchestrator import Ingester, SuggestedPage
from giki.sources.loader import LoadedSource, load_source
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

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        self.calls.append(list(messages))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return LLMResponse(text=r, finish_reason="stop")


def _loaded(tmp_path, text="Some source content"):
    p = tmp_path / "src.md"
    p.write_text(text, encoding="utf-8")
    return load_source(p)


BODY_FROM_LLM = """# Observer Pattern

This is the body from the LLM.

It has multiple paragraphs.
"""


class TestConfirmPages:
    def test_dry_run_prints_and_returns_empty(self, tmp_path, capsys):
        cfg = _init_giki(tmp_path)
        cands = [
            SuggestedPage("a", "Alpha", "create"),
            SuggestedPage("b", "Beta", "create"),
        ]
        ing = Ingester(cfg)
        result = ing.confirm_pages(cands, yes=False, dry_run=True, tty=True)
        assert result == []
        out = capsys.readouterr().out
        assert "Alpha" in out and "Beta" in out

    def test_yes_returns_all(self, tmp_path):
        cfg = _init_giki(tmp_path)
        cands = [SuggestedPage("a", "A", "create"), SuggestedPage("b", "B", "create")]
        ing = Ingester(cfg)
        result = ing.confirm_pages(cands, yes=True, dry_run=False, tty=True)
        assert result == cands

    def test_non_tty_returns_all(self, tmp_path):
        cfg = _init_giki(tmp_path)
        cands = [SuggestedPage("a", "A", "create")]
        ing = Ingester(cfg)
        result = ing.confirm_pages(cands, yes=False, dry_run=False, tty=False)
        assert result == cands

    def test_interactive_filters(self, tmp_path, monkeypatch):
        cfg = _init_giki(tmp_path)
        cands = [
            SuggestedPage("keep-1", "K1", "create"),
            SuggestedPage("skip-1", "S1", "create"),
            SuggestedPage("keep-2", "K2", "create"),
        ]
        # Simulate y / n / y answers
        answers = iter(["y", "n", "y"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
        ing = Ingester(cfg)
        result = ing.confirm_pages(cands, yes=False, dry_run=False, tty=True)
        assert [p.filename for p in result] == ["keep-1", "keep-2"]


class TestSynthesizeCreate:
    def test_creates_file_with_frontmatter(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded(tmp_path, "some content about observers")
        sp = SuggestedPage(
            filename="observer",
            title="Observer Pattern",
            action="create",
            hints=["describe roles"],
            aliases_suggested=["Observer"],
        )
        llm = FakeLLM([BODY_FROM_LLM])
        ing = Ingester(cfg)
        filename, ok = ing.synthesize(src, sp, llm_client=llm)
        assert ok is True
        assert filename == "observer"

        store = WikiStore(cfg.root)
        assert store.exists("observer")
        content = store.read("observer")
        page = parse_page(content)
        assert page.title == "Observer Pattern"
        assert page.aliases == ["Observer"]
        assert "This is the body from the LLM." in page.body
        # sources frontmatter should record the source path
        assert len(page.sources) == 1
        assert "src.md" in str(page.sources[0].get("path", ""))

    def test_frontmatter_created_and_updated_iso(self, tmp_path):
        import re
        cfg = _init_giki(tmp_path)
        src = _loaded(tmp_path)
        sp = SuggestedPage("x", "X", "create")
        llm = FakeLLM(["# X\n\nbody"])
        ing = Ingester(cfg)
        ing.synthesize(src, sp, llm_client=llm)

        page = parse_page(WikiStore(cfg.root).read("x"))
        iso_re = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"
        assert re.match(iso_re, page.created)
        assert re.match(iso_re, page.updated)


class TestSynthesizeUpdate:
    def test_update_preserves_created_and_aliases(self, tmp_path):
        cfg = _init_giki(tmp_path)
        # Pre-populate a page
        store = WikiStore(cfg.root)
        existing_body = """---
title: Existing
aliases: [OldAlias]
created: 2020-01-01T00:00:00+00:00
updated: 2020-01-01T00:00:00+00:00
sources:
  - path: sources/old.md
---

# Existing

Original content.
"""
        store.write("existing", existing_body)

        src = _loaded(tmp_path, "new source content")
        sp = SuggestedPage(
            filename="existing",
            title="Existing",
            action="update",
            hints=["merge new material"],
            aliases_suggested=["OldAlias", "NewAlias"],
        )
        llm = FakeLLM(["# Existing\n\nRewritten body with new material."])
        ing = Ingester(cfg)
        filename, ok = ing.synthesize(src, sp, llm_client=llm)
        assert ok is True

        page = parse_page(store.read("existing"))
        # created preserved
        assert page.created == "2020-01-01T00:00:00+00:00"
        # updated bumped (differs from created)
        assert page.updated != page.created
        # OldAlias retained
        assert "OldAlias" in page.aliases
        # sources appended (old + new both present)
        source_paths = [s.get("path", "") for s in page.sources]
        assert any("old.md" in p for p in source_paths)
        assert any("src.md" in p for p in source_paths)


class TestSynthesizeFailure:
    def test_llm_error_returns_failure_not_raise(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded(tmp_path)
        sp = SuggestedPage("boom", "Boom", "create")
        llm = FakeLLM([LLMError("blown", retryable=False)])
        ing = Ingester(cfg)
        filename, ok = ing.synthesize(src, sp, llm_client=llm)
        assert filename == "boom"
        assert ok is False
        # No file written
        assert not WikiStore(cfg.root).exists("boom")


class TestSynthesizeAll:
    def test_returns_succeeded_and_failed(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded(tmp_path)
        pages = [
            SuggestedPage("a", "A", "create"),
            SuggestedPage("b", "B", "create"),
            SuggestedPage("c", "C", "create"),
        ]
        llm = FakeLLM([
            "# A\n\nbody-a",
            LLMError("blown", retryable=False),  # b fails
            "# C\n\nbody-c",
        ])
        ing = Ingester(cfg)
        succeeded, failed = ing.synthesize_all(src, pages, llm_client=llm)
        assert succeeded == ["a", "c"]
        assert failed == ["b"]
        # a and c present, b absent
        store = WikiStore(cfg.root)
        assert store.exists("a") and store.exists("c") and not store.exists("b")

    def test_all_success(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded(tmp_path)
        pages = [SuggestedPage("x", "X", "create")]
        llm = FakeLLM(["# X\n\nbody"])
        ing = Ingester(cfg)
        succeeded, failed = ing.synthesize_all(src, pages, llm_client=llm)
        assert succeeded == ["x"]
        assert failed == []

    def test_all_failure(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded(tmp_path)
        pages = [SuggestedPage("x", "X", "create"), SuggestedPage("y", "Y", "create")]
        llm = FakeLLM([
            LLMError("boom", retryable=False),
            LLMError("boom", retryable=False),
        ])
        ing = Ingester(cfg)
        succeeded, failed = ing.synthesize_all(src, pages, llm_client=llm)
        assert succeeded == []
        assert failed == ["x", "y"]
