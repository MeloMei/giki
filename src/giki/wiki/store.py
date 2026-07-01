"""WikiStore — file-based CRUD for wiki/*.md with slug guards and atomic writes."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterator

from .parser import WikiPage, parse_page


class WikiStoreError(Exception):
    """Invalid slug, missing page, or path escape attempt."""


DEFAULT_SLUG_PATTERN = r"^[a-z0-9-]+$"


class WikiStore:
    def __init__(
        self,
        root: Path,
        *,
        slug_pattern: str = DEFAULT_SLUG_PATTERN,
        max_slug_length: int = 80,
    ):
        self.root = Path(root).resolve()
        self.wiki_dir = self.root / "wiki"
        self._slug_re = re.compile(slug_pattern)
        self._max_len = max_slug_length

    # ---------- slug validation ----------

    def _check_slug(self, slug: str) -> None:
        if not slug:
            raise WikiStoreError("invalid slug: empty")
        if "/" in slug or "\\" in slug:
            raise WikiStoreError(f"invalid slug {slug!r}: contains path separator")
        if slug.startswith("."):
            raise WikiStoreError(f"invalid slug {slug!r}: starts with '.'")
        if len(slug) > self._max_len:
            raise WikiStoreError(
                f"invalid slug {slug!r}: length {len(slug)} exceeds max {self._max_len}"
            )
        if not self._slug_re.match(slug):
            raise WikiStoreError(
                f"invalid slug {slug!r}: must match {self._slug_re.pattern}"
            )

    def _path_for(self, slug: str) -> Path:
        self._check_slug(slug)
        return self.wiki_dir / f"{slug}.md"

    # ---------- ops ----------

    def exists(self, slug: str) -> bool:
        return self._path_for(slug).exists()

    def read(self, slug: str) -> str:
        p = self._path_for(slug)
        if not p.exists():
            raise WikiStoreError(f"page not found: {slug}")
        return p.read_text(encoding="utf-8")

    def write(self, slug: str, content: str) -> None:
        final = self._path_for(slug)
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.with_suffix(final.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, final)

    def list_pages(self) -> list[str]:
        if not self.wiki_dir.exists():
            return []
        return [
            p.stem for p in self.wiki_dir.iterdir()
            if p.is_file() and p.suffix == ".md" and not p.name.startswith(".")
        ]

    def all_pages(self) -> Iterator[tuple[str, WikiPage]]:
        for slug in sorted(self.list_pages()):
            content = self.read(slug)
            yield slug, parse_page(content)
