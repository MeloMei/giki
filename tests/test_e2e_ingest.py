"""End-to-end integration tests for the full 8-phase ingest pipeline.

This module exercises the full 8-phase ingest pipeline using scripted
``FakeLLM`` responses. The original plan (Task 27) called for VCR
cassettes with real Anthropic recordings; since v0.1 development had no
live API credentials available, we substitute deterministic scripted
responses that cover the same Analyze / Synthesize / Crosslink call
sequence.

When credentials become available, a maintainer can extend this file with
``@pytest.mark.vcr``-decorated variants; the cassette directory
``tests/cassettes/`` can be populated at that time.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import git
import pytest

from giki.config import load_config
from giki.llm.base import LLMAdapter, LLMError, LLMResponse, Message
from giki.orchestrator import Ingester
from giki.sources.loader import load_source
from giki.wiki.parser import parse_page


# --- Fixtures / helpers ---------------------------------------------------

_CFG_YAML = """
llm:
  compile:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
  review:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
ingest:
  chunk_size: 12000
  chunk_overlap: 500
  synthesize_context: 6000
wiki:
  related_min_neighbors: 1
"""


def _init_giki(tmp_path: Path):
    """Initialize a giki knowledge base in ``tmp_path`` (mirrors the pattern
    from ``tests/test_orchestrator_phase2.py``)."""
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.co").release()
    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(_CFG_YAML, encoding="utf-8")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    repo.index.add([".giki/config.yaml", "README.md"])
    repo.index.commit("initial")
    return load_config(tmp_path)


class FakeLLM(LLMAdapter):
    """Deterministic fake LLM returning pre-scripted responses per call.

    Copied verbatim from ``tests/test_orchestrator_phase2.py`` so this test
    surface is independent of that module.
    """

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


# --- Test 1: markdown end-to-end -----------------------------------------

def test_ingest_markdown_end_to_end(tmp_path):
    cfg = _init_giki(tmp_path)

    src = tmp_path / "sources" / "observer.md"
    src.write_text(
        "# Observer\n\nThe Observer pattern is a behavioral design pattern "
        "where one subject notifies many observers.\n",
        encoding="utf-8",
    )

    analyze_resp = json.dumps({
        "suggested_pages": [
            {
                "filename": "observer-pattern",
                "title": "Observer Pattern",
                "action": "create",
                "hints": ["describe subject and observers"],
                "source_anchors": ["intro paragraph"],
                "aliases_suggested": ["Observer"],
            }
        ]
    })
    synth_resp = (
        "# Observer Pattern\n\n"
        "Behavioral design pattern where a subject notifies many observers.\n\n"
        "Related: [[subject]].\n"
    )
    crosslink_resp = json.dumps({"neighbors": [], "inline_hints": []})

    llm = FakeLLM([analyze_resp, synth_resp, crosslink_resp])
    ing = Ingester(cfg)
    result = ing.ingest(
        src,
        branch="wiki/observer",
        yes=True,
        dry_run=False,
        llm_client=llm,
    )

    assert result.skipped is False
    assert "observer-pattern" in result.created
    assert result.failed == []
    assert result.commit_sha is not None

    page_path = tmp_path / "wiki" / "observer-pattern.md"
    assert page_path.exists()

    index_text = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "observer-pattern" in index_text

    log_text = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert "observer-pattern" in log_text
    assert "created:" in log_text

    state_file = tmp_path / ".giki-state" / "sources.json"
    assert state_file.exists()
    assert "observer.md" in state_file.read_text(encoding="utf-8")

    repo = git.Repo(tmp_path)
    assert repo.active_branch.name == "wiki/observer"
    assert result.commit_sha == repo.head.commit.hexsha


# --- Test 2: PDF page-separator handling ---------------------------------

def test_ingest_pdf_uses_page_separator(tmp_path, tiny_pdf):
    cfg = _init_giki(tmp_path)

    src = tmp_path / "sources" / "hello.pdf"
    shutil.copyfile(tiny_pdf, src)

    # Sanity: the loader emits the configured page-separator markers.
    loaded = load_source(src)
    assert loaded.kind == "pdf"
    assert "<!-- giki:page 1 -->" in loaded.text
    assert "<!-- giki:page 2 -->" in loaded.text
    assert "<!-- giki:page 3 -->" in loaded.text

    analyze_resp = json.dumps({
        "suggested_pages": [
            {
                "filename": "hello-notes",
                "title": "Hello Notes",
                "action": "create",
                "hints": ["summarize the three pages"],
                "source_anchors": ["page 1", "page 2"],
                "aliases_suggested": [],
            }
        ]
    })
    synth_resp = (
        "# Hello Notes\n\n"
        "Combined summary of pages one, two, and three.\n"
    )
    crosslink_resp = json.dumps({"neighbors": [], "inline_hints": []})

    llm = FakeLLM([analyze_resp, synth_resp, crosslink_resp])
    ing = Ingester(cfg)
    result = ing.ingest(src, branch=None, yes=True, dry_run=False, llm_client=llm)

    assert result.skipped is False
    assert "hello-notes" in result.created

    # The resulting page records the pdf source path in frontmatter.
    # (v0.1 orchestrator does not embed per-page numbers into frontmatter
    # sources; ``source_anchors`` live only on the transient SuggestedPage.
    # See module docstring for the intended vcr-based expansion.)
    page = parse_page(
        (tmp_path / "wiki" / "hello-notes.md").read_text(encoding="utf-8")
    )
    source_paths = [str(s.get("path", "")) for s in page.sources]
    assert any("hello.pdf" in p for p in source_paths)


# --- Test 3: unchanged source is skipped ---------------------------------

def test_ingest_skips_unchanged_source(tmp_path):
    cfg = _init_giki(tmp_path)

    src = tmp_path / "sources" / "observer.md"
    src.write_text("Observer pattern content.\n", encoding="utf-8")

    llm1 = FakeLLM([
        json.dumps({
            "suggested_pages": [
                {
                    "filename": "observer",
                    "title": "Observer",
                    "action": "create",
                    "hints": [],
                    "source_anchors": [],
                    "aliases_suggested": [],
                }
            ]
        }),
        "# Observer\n\nbody",
        json.dumps({"neighbors": [], "inline_hints": []}),
    ])
    r1 = Ingester(cfg).ingest(
        src, branch=None, yes=True, dry_run=False, llm_client=llm1,
    )
    assert r1.skipped is False
    assert r1.commit_sha is not None

    repo = git.Repo(tmp_path)
    sha_before = repo.head.commit.hexsha

    # Second run: hash unchanged -> Phase 1 short-circuit BEFORE any LLM
    # call. An empty response list guarantees an IndexError if any call
    # were made, which would signal a regression.
    llm2 = FakeLLM([])
    r2 = Ingester(cfg).ingest(
        src, branch=None, yes=True, dry_run=False, llm_client=llm2,
    )
    assert r2.skipped is True
    assert r2.commit_sha is None
    assert len(llm2.calls) == 0

    # No new commit was created.
    assert repo.head.commit.hexsha == sha_before


# --- Test 4: retry-failed pages -------------------------------------------

def test_ingest_retry_failed(tmp_path):
    """First run fails during Synthesize; second run with
    ``retry_failed=True`` should re-invoke the full pipeline and succeed.

    The v0.1 orchestrator persists source-SHA state but not an explicit
    failed-pages list; ``retry_failed=True`` merely bypasses the
    hash-based short-circuit so the full pipeline re-runs. This is
    sufficient to recover from a transient LLM failure on the previous
    run, which is the semantics this test verifies. A richer
    implementation could persist per-page failure state in
    ``.giki-state/`` and re-select only failed pages during retry.
    """
    cfg = _init_giki(tmp_path)

    src = tmp_path / "sources" / "observer.md"
    src.write_text("Observer pattern content.\n", encoding="utf-8")

    analyze_resp = json.dumps({
        "suggested_pages": [
            {
                "filename": "observer-pattern",
                "title": "Observer Pattern",
                "action": "create",
                "hints": [],
                "source_anchors": [],
                "aliases_suggested": [],
            }
        ]
    })

    # First run: analyze OK, synth blows up -> page fails.
    # No crosslink call is made because succeeded_slugs is empty.
    llm1 = FakeLLM([analyze_resp, LLMError("synth boom", retryable=False)])
    r1 = Ingester(cfg).ingest(
        src, branch=None, yes=True, dry_run=False, llm_client=llm1,
    )
    assert r1.skipped is False
    assert r1.created == []
    assert "observer-pattern" in r1.failed
    assert not (tmp_path / "wiki" / "observer-pattern.md").exists()

    # Second run: hash is unchanged, so we need ``retry_failed=True`` to
    # bypass the Phase 1 short-circuit. Synth now succeeds.
    llm2 = FakeLLM([
        analyze_resp,
        "# Observer Pattern\n\nRecovered body.\n",
        json.dumps({"neighbors": [], "inline_hints": []}),
    ])
    r2 = Ingester(cfg).ingest(
        src, branch=None, yes=True, dry_run=False,
        retry_failed=True, llm_client=llm2,
    )
    assert r2.skipped is False
    assert "observer-pattern" in r2.created
    assert r2.failed == []
    assert (tmp_path / "wiki" / "observer-pattern.md").exists()
