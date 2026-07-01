"""Ingest orchestration: source -> LLM analyze -> LLM synthesize -> LLM crosslink -> git commit.

Only Phase 0 (Bootstrap) and Phase 1 (Source loading) are implemented here.
Phases 2-7 arrive in Tasks 20-22.
"""

from __future__ import annotations

from pathlib import Path

import git

from .config import Config
from .git_utils import checkout_branch, open_repo, ensure_clean_worktree
from .sources.loader import LoadedSource, load_source
from .sources.state import SourceState


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
