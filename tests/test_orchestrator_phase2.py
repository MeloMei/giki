import json
from pathlib import Path

import pytest
import git

from giki.config import load_config
from giki.llm.base import LLMAdapter, LLMError, LLMResponse, Message
from giki.orchestrator import Ingester, SuggestedPage
from giki.sources.loader import LoadedSource
from giki.wiki.store import WikiStore


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
ingest:
  chunk_size: 100
  chunk_overlap: 20
"""


def _init_giki(tmp_path):
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.co").release()
    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(VALID_CFG_YAML, encoding="utf-8")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    repo.index.add([".giki/config.yaml", "README.md"])
    repo.index.commit("initial")
    return load_config(tmp_path)


class FakeLLM(LLMAdapter):
    """Deterministic fake LLM that returns pre-scripted responses per call."""

    provider = "fake"
    model = "fake-m"
    name = "fake:fake-m"

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[list[Message]] = []

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        self.calls.append(list(messages))
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return LLMResponse(text=r, finish_reason="stop")


def _loaded_source(tmp_path, text: str, ext: str = ".md") -> LoadedSource:
    p = tmp_path / f"src{ext}"
    p.write_text(text, encoding="utf-8")
    from giki.sources.loader import load_source
    return load_source(p)


class TestAnalyzeSingleChunk:
    def test_single_page_suggestion(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded_source(tmp_path, "short content")
        llm = FakeLLM([json.dumps({
            "suggested_pages": [
                {"filename": "observer-pattern", "title": "Observer Pattern",
                 "action": "create", "hints": ["h1"],
                 "source_anchors": ["page 1"], "aliases_suggested": ["Observer"]}
            ]
        })])
        ing = Ingester(cfg)
        result = ing.analyze(src, llm_client=llm)
        assert len(result) == 1
        p = result[0]
        assert p.filename == "observer-pattern"
        assert p.action == "create"
        assert p.hints == ["h1"]
        assert p.aliases_suggested == ["Observer"]

    def test_multiple_pages_from_one_chunk(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded_source(tmp_path, "x")
        llm = FakeLLM([json.dumps({
            "suggested_pages": [
                {"filename": "a", "title": "A", "action": "create", "hints": [], "source_anchors": [], "aliases_suggested": []},
                {"filename": "b", "title": "B", "action": "create", "hints": [], "source_anchors": [], "aliases_suggested": []},
            ]
        })])
        ing = Ingester(cfg)
        result = ing.analyze(src, llm_client=llm)
        assert {p.filename for p in result} == {"a", "b"}


class TestAnalyzeChunking:
    def test_multiple_chunks_when_content_exceeds_chunk_size(self, tmp_path):
        cfg = _init_giki(tmp_path)  # chunk_size=100, overlap=20
        # 400 chars => multiple chunks
        text = ("Paragraph one. " * 20).strip() + "\n\n" + ("Paragraph two. " * 20).strip()
        src = _loaded_source(tmp_path, text)

        empty_resp = json.dumps({"suggested_pages": []})
        llm = FakeLLM([empty_resp] * 20)

        ing = Ingester(cfg)
        result = ing.analyze(src, llm_client=llm)
        assert result == []
        # More than one chunk means more than one call:
        assert len(llm.calls) >= 2

    def test_merge_dedupes_by_slug(self, tmp_path):
        cfg = _init_giki(tmp_path)
        text = "x" * 500
        src = _loaded_source(tmp_path, text)

        resp = json.dumps({
            "suggested_pages": [
                {"filename": "topic", "title": "Topic", "action": "create",
                 "hints": [], "source_anchors": [], "aliases_suggested": []}
            ]
        })
        llm = FakeLLM([resp] * 20)

        ing = Ingester(cfg)
        result = ing.analyze(src, llm_client=llm)
        assert len(result) == 1
        assert result[0].filename == "topic"

    def test_merge_aggregates_hints(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded_source(tmp_path, "x" * 500)
        chunk1 = json.dumps({
            "suggested_pages": [
                {"filename": "topic", "title": "Topic", "action": "create",
                 "hints": ["chunk-1 hint"], "source_anchors": ["p1"], "aliases_suggested": ["A1"]}
            ]
        })
        chunk2 = json.dumps({
            "suggested_pages": [
                {"filename": "topic", "title": "Topic", "action": "create",
                 "hints": ["chunk-2 hint"], "source_anchors": ["p2"], "aliases_suggested": ["A2"]}
            ]
        })
        llm = FakeLLM([chunk1, chunk2] * 10)

        ing = Ingester(cfg)
        result = ing.analyze(src, llm_client=llm)
        assert len(result) == 1
        p = result[0]
        assert "chunk-1 hint" in p.hints
        assert "chunk-2 hint" in p.hints
        assert set(p.source_anchors) == {"p1", "p2"}
        assert set(p.aliases_suggested) == {"A1", "A2"}


class TestUpdateAction:
    def test_existing_slug_forced_to_update(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        store.write("existing", """---
title: Existing
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---

# Existing
""")

        src = _loaded_source(tmp_path, "x")
        llm = FakeLLM([json.dumps({
            "suggested_pages": [
                {"filename": "existing", "title": "Existing", "action": "create",
                 "hints": [], "source_anchors": [], "aliases_suggested": []}
            ]
        })])
        ing = Ingester(cfg)
        result = ing.analyze(src, llm_client=llm)
        assert result[0].action == "update"


class TestJsonRetry:
    def test_retry_on_malformed_json(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded_source(tmp_path, "x")
        good = json.dumps({"suggested_pages": []})
        llm = FakeLLM(["not json at all", good])
        ing = Ingester(cfg)
        result = ing.analyze(src, llm_client=llm)
        assert result == []
        assert len(llm.calls) == 2

    def test_hard_fail_after_two_bad_responses(self, tmp_path):
        cfg = _init_giki(tmp_path)
        src = _loaded_source(tmp_path, "x")
        llm = FakeLLM(["garbage 1", "garbage 2"])
        ing = Ingester(cfg)
        with pytest.raises(LLMError):
            ing.analyze(src, llm_client=llm)


class TestIndexSummary:
    def test_existing_pages_summarized_in_prompt(self, tmp_path):
        cfg = _init_giki(tmp_path)
        store = WikiStore(cfg.root)
        store.write("existing-a", """---
title: Existing A
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---
# Existing A
""")

        src = _loaded_source(tmp_path, "x")
        llm = FakeLLM([json.dumps({"suggested_pages": []})])
        ing = Ingester(cfg)
        ing.analyze(src, llm_client=llm)

        user_msg = next(m for m in llm.calls[0] if m.role == "user")
        assert "existing-a" in user_msg.content
        assert "Existing A" in user_msg.content
