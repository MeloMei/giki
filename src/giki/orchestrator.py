"""Ingest orchestration: source -> LLM analyze -> LLM synthesize -> LLM crosslink -> git commit.

Phases 0-2 implemented here. Phases 3-7 arrive in Tasks 21-22.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import git

from .config import Config
from .git_utils import checkout_branch, open_repo, ensure_clean_worktree
from .llm import build_client
from .llm.base import LLMAdapter, LLMError, Message
from .sources.loader import LoadedSource, load_source
from .sources.state import SourceState
from .utils import extract_json, to_slug
from .wiki.linker import Linker
from .wiki.store import WikiStore


@dataclass
class SuggestedPage:
    filename: str
    title: str
    action: Literal["create", "update"]
    hints: list[str] = field(default_factory=list)
    source_anchors: list[str] = field(default_factory=list)
    aliases_suggested: list[str] = field(default_factory=list)


class Ingester:
    """End-to-end ingest orchestrator.

    Cheap to construct - LLM clients are built lazily by later phases.
    """

    def __init__(self, config: Config):
        self.config = config
        self._state: SourceState | None = None

    # -------- Phase 0: Bootstrap --------

    def bootstrap(self, branch: str | None) -> git.Repo:
        """Open repo, ensure clean, optionally switch to `branch`."""
        repo = open_repo(self.config.root)
        ensure_clean_worktree(repo)
        if branch:
            checkout_branch(repo, branch, create=True)
        return repo

    # -------- Phase 1: Source Loading --------

    @property
    def state(self) -> SourceState:
        if self._state is None:
            self._state = SourceState.load(self.config.root)
        return self._state

    def load_source(self, path: Path) -> tuple[LoadedSource, bool]:
        """Load a source file and report whether it needs re-ingest.

        needs_ingest is True if:
          * The source has never been ingested, OR
          * The source's SHA-256 hash has changed since the last ingest.
        """
        loaded = load_source(
            path,
            pdf_page_separator=self.config.ingest.pdf.page_separator,
            pdf_reject_scanned=self.config.ingest.pdf.reject_scanned,
        )
        needs = self.state.needs_ingest(path, loaded.sha256)
        return loaded, needs

    # -------- Phase 2: Analyze --------

    def analyze(
        self,
        source: LoadedSource,
        *,
        llm_client: LLMAdapter | None = None,
    ) -> list[SuggestedPage]:
        """Split source into chunks, ask LLM for suggested pages, merge results."""
        client = llm_client or build_client(self.config.llm.compile)
        chunks = _chunk_text(
            source.text,
            size=self.config.ingest.chunk_size,
            overlap=self.config.ingest.chunk_overlap,
        )
        if not chunks:
            # Empty source: still make one call so the prompt path runs once.
            chunks = [""]

        store = WikiStore(
            self.config.root,
            slug_pattern=self.config.wiki.enforce_slug_pattern,
            max_slug_length=self.config.wiki.max_slug_length,
        )
        linker = Linker(store)
        index_summary = _build_index_summary(store)

        merged: dict[str, SuggestedPage] = {}
        for i, chunk in enumerate(chunks, start=1):
            page_list = self._analyze_chunk(
                client=client,
                chunk=chunk,
                chunk_i=i,
                chunk_n=len(chunks),
                source_path=str(source.path),
                source_kind=source.kind,
                index_summary=index_summary,
            )
            for raw in page_list:
                _merge_into(merged, raw)

        # Force `update` action on any slug that already exists in the wiki
        # (direct filename or via alias).
        for slug, sp in merged.items():
            resolved = linker.resolve(sp.filename)
            if resolved is not None:
                sp.action = "update"

        return list(merged.values())

    def _analyze_chunk(
        self,
        *,
        client: LLMAdapter,
        chunk: str,
        chunk_i: int,
        chunk_n: int,
        source_path: str,
        source_kind: str,
        index_summary: str,
    ) -> list[dict]:
        prompt = _render_analyze_prompt(
            chunk=chunk, chunk_i=chunk_i, chunk_n=chunk_n,
            source_path=source_path, source_kind=source_kind,
            index_summary=index_summary,
        )
        messages = [Message(role="user", content=prompt)]

        try:
            response = client.chat(messages)
            data = extract_json(response.text)
        except ValueError:
            correction = Message(
                role="system",
                content=(
                    "Your previous response was not valid JSON. "
                    "Return ONLY a JSON object matching the schema, "
                    "no prose, no markdown fences."
                ),
            )
            response = client.chat([correction] + messages)
            try:
                data = extract_json(response.text)
            except ValueError as e:
                raise LLMError(
                    f"analyze: failed to parse JSON after retry: {e}"
                ) from e

        pages = data.get("suggested_pages", []) if isinstance(data, dict) else []
        return list(pages)


def _render_analyze_prompt(
    *, chunk: str, chunk_i: int, chunk_n: int,
    source_path: str, source_kind: str, index_summary: str,
) -> str:
    return f"""You are giki's knowledge compiler.
Analyze the content below and propose which wiki pages should be created or updated.

Source: {source_path} ({source_kind})
Chunk {chunk_i}/{chunk_n}

Existing pages:
{index_summary or "(none)"}

Content:
---
{chunk}
---

Output JSON only:
{{
  "suggested_pages": [
    {{
      "filename": "kebab-case-slug",
      "title": "Human readable",
      "action": "create" or "update",
      "hints": ["..."],
      "source_anchors": ["..."],
      "aliases_suggested": ["..."]
    }}
  ]
}}
"""


def _build_index_summary(store: WikiStore) -> str:
    lines: list[str] = []
    for slug, page in store.all_pages():
        lines.append(f"- {slug} \u2014 {page.title}")
    return "\n".join(lines)


def _chunk_text(text: str, *, size: int, overlap: int) -> list[str]:
    """Slide-window chunk. Break on paragraph boundaries when possible."""
    if not text:
        return []
    if size <= 0 or len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Try to break on nearest '\n\n' before `end` (within last 20% of the window)
        if end < len(text):
            window_start = max(start, end - size // 5)
            para_break = text.rfind("\n\n", window_start, end)
            if para_break != -1 and para_break > start:
                end = para_break + 2  # include the newlines
        chunks.append(text[start:end])
        if end >= len(text):
            break
        next_start = end - overlap
        if next_start <= start:
            # Guarantee forward progress if overlap >= size
            next_start = start + 1
        start = next_start
    return chunks


def _merge_into(merged: dict[str, SuggestedPage], raw: dict) -> None:
    """Merge one raw dict into the accumulator, deduping by slug."""
    if not isinstance(raw, dict):
        return
    filename = str(raw.get("filename") or "").strip()
    if not filename:
        return
    try:
        slug = to_slug(filename)
    except ValueError:
        return

    title = str(raw.get("title") or slug)
    action = raw.get("action", "create")
    if action not in ("create", "update"):
        action = "create"
    hints = [str(h) for h in (raw.get("hints") or [])]
    anchors = [str(a) for a in (raw.get("source_anchors") or [])]
    aliases = [str(a) for a in (raw.get("aliases_suggested") or [])]

    if slug in merged:
        sp = merged[slug]
        for h in hints:
            if h not in sp.hints:
                sp.hints.append(h)
        for a in anchors:
            if a not in sp.source_anchors:
                sp.source_anchors.append(a)
        for a in aliases:
            if a not in sp.aliases_suggested:
                sp.aliases_suggested.append(a)
        # Prefer update over create if any chunk marked update
        if action == "update":
            sp.action = "update"
    else:
        merged[slug] = SuggestedPage(
            filename=slug,
            title=title,
            action=action,
            hints=hints,
            source_anchors=anchors,
            aliases_suggested=aliases,
        )
