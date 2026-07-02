"""BM25 full-text search index over wiki pages."""

from __future__ import annotations

import json
from pathlib import Path

from rank_bm25 import BM25Okapi

from .wiki.parser import parse_page
from .wiki.store import WikiStore


def _tokenize(text: str) -> list[str]:
    """Whitespace-split and lowercase."""
    return text.lower().split()


class SearchIndex:
    """BM25 search index over all wiki pages.

    The index is persisted as JSON under ``.giki-state/index.json`` so it
    survives across process invocations without a rebuild.
    """

    def __init__(self, root: Path):
        self._state_path = Path(root) / ".giki-state" / "index.json"
        self._slugs: list[str] = []
        self._corpus: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

    # ------------------------------------------------------------------ build

    def build(self, wiki_dir: Path) -> None:
        """Build BM25 index from all wiki pages.

        ``wiki_dir`` is the ``wiki/`` directory; its parent is treated as the
        project root for constructing :class:`WikiStore`.
        """
        root = Path(wiki_dir).parent
        store = WikiStore(root)

        self._slugs = []
        self._corpus = []

        for slug, page in store.all_pages():
            tokens = _tokenize(page.title) + _tokenize(page.body)
            self._slugs.append(slug)
            self._corpus.append(tokens)

        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
        else:
            self._bm25 = None

    # ------------------------------------------------------------------ save

    def save(self) -> None:
        """Persist index to ``.giki-state/index.json``."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "slugs": self._slugs,
            "corpus": self._corpus,
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ load

    def load(self) -> bool:
        """Load index from disk. Returns True if loaded successfully."""
        if not self._state_path.exists():
            return False
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._slugs = list(raw["slugs"])
            self._corpus = [list(doc) for doc in raw["corpus"]]
        except (json.JSONDecodeError, KeyError, TypeError):
            return False

        if self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
        else:
            self._bm25 = None
        return True

    # ---------------------------------------------------------------- search

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Search the index. Returns ``(slug, score)`` tuples, highest first.

        Returns an empty list when the index has not been built or loaded.
        """
        if self._bm25 is None or not self._slugs:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        # Pair each slug with its score, sort descending, take top_k.
        ranked = sorted(
            zip(self._slugs, scores),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [(slug, float(score)) for slug, score in ranked[:top_k] if score > 0]
