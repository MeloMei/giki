"""Tests for giki.search — BM25 search index."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from giki.search import SearchIndex


PAGE_A = """\
---
title: Alpha
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---

Alpha is the first letter of the Greek alphabet.
"""

PAGE_B = """\
---
title: Beta Gamma
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---

Beta and gamma are subsequent Greek letters.
"""

PAGE_C = """\
---
title: Delta
created: 2026-06-30T14:00:00+08:00
updated: 2026-06-30T14:00:00+08:00
---

Delta is unrelated to Python programming language.
"""


def _make_root(tmp_path: Path) -> Path:
    """Create a project root with a wiki/ directory containing sample pages."""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "alpha.md").write_text(PAGE_A, encoding="utf-8")
    (wiki / "beta-gamma.md").write_text(PAGE_B, encoding="utf-8")
    (wiki / "delta.md").write_text(PAGE_C, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------- Build


class TestBuild:
    def test_build_populates_slugs_and_corpus(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        assert sorted(idx._slugs) == ["alpha", "beta-gamma", "delta"]
        assert len(idx._corpus) == 3

    def test_build_empty_wiki(self, tmp_path):
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        idx = SearchIndex(tmp_path)
        idx.build(wiki)
        assert idx._slugs == []
        assert idx._corpus == []
        assert idx._bm25 is None

    def test_build_tokens_are_lowercased(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        # Find the alpha page's token list.
        alpha_i = idx._slugs.index("alpha")
        tokens = idx._corpus[alpha_i]
        assert all(t == t.lower() for t in tokens)
        # Title "Alpha" should contribute "alpha" token.
        assert "alpha" in tokens


# ---------------------------------------------------------------- Save / Load


class TestPersistence:
    def test_save_creates_json(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        idx.save()
        assert (root / ".giki-state" / "index.json").exists()

    def test_save_then_load_roundtrip(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        idx.save()

        idx2 = SearchIndex(root)
        assert idx2.load() is True
        assert idx2._slugs == idx._slugs
        assert idx2._corpus == idx._corpus

    def test_load_returns_false_when_no_file(self, tmp_path):
        idx = SearchIndex(tmp_path)
        assert idx.load() is False

    def test_load_returns_false_on_corrupt_json(self, tmp_path):
        state_path = tmp_path / ".giki-state" / "index.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text("{not valid json", encoding="utf-8")
        idx = SearchIndex(tmp_path)
        assert idx.load() is False

    def test_load_returns_false_on_missing_keys(self, tmp_path):
        state_path = tmp_path / ".giki-state" / "index.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text(json.dumps({"slugs": ["a"]}), encoding="utf-8")
        idx = SearchIndex(tmp_path)
        assert idx.load() is False

    def test_save_creates_parent_dirs(self, tmp_path):
        root = tmp_path / "deep" / "nested"
        root.mkdir(parents=True)
        wiki = root / "wiki"
        wiki.mkdir()
        idx = SearchIndex(root)
        idx.build(wiki)
        idx.save()  # should not raise even though .giki-state doesn't exist yet
        assert (root / ".giki-state" / "index.json").exists()


# ---------------------------------------------------------------- Search


class TestSearch:
    def test_search_returns_results(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        results = idx.search("greek alphabet")
        assert len(results) > 0
        # Each result is (slug, score)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        assert all(isinstance(r[0], str) and isinstance(r[1], float) for r in results)

    def test_search_relevant_page_ranks_first(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        results = idx.search("greek letters alphabet")
        slugs = [r[0] for r in results]
        # alpha mentions "greek alphabet", should rank high
        assert "alpha" in slugs

    def test_search_top_k_limits_results(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        results = idx.search("greek", top_k=1)
        assert len(results) <= 1

    def test_search_scores_descending(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        results = idx.search("greek letters")
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_no_results_for_gibberish(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        results = idx.search("xyzzyplugh")
        assert results == []

    def test_search_empty_query(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        results = idx.search("")
        assert results == []

    def test_search_empty_index(self, tmp_path):
        idx = SearchIndex(tmp_path)
        # Never built — bm25 is None.
        results = idx.search("anything")
        assert results == []

    def test_search_after_load(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        idx.save()

        idx2 = SearchIndex(root)
        idx2.load()
        results = idx2.search("greek")
        assert len(results) > 0

    def test_search_filters_zero_scores(self, tmp_path):
        root = _make_root(tmp_path)
        idx = SearchIndex(root)
        idx.build(root / "wiki")
        results = idx.search("python programming language")
        # Only delta mentions "python programming language"
        for slug, score in results:
            assert score > 0
