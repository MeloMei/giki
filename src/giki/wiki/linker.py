"""Two-stage wikilink resolution + dead-link detection + ## Related block.

Resolution order (from spec §9.4):
  1. Filename match: wiki/<target>.md exists → resolve to <target>.
  2. Alias match: some page has <target> in its frontmatter.aliases.
  3. Otherwise → dead link.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .parser import WikiLink, WikiPage

if TYPE_CHECKING:
    from .store import WikiStore


class Linker:
    def __init__(self, store: "WikiStore"):
        self._store = store
        self._slugs: set[str] = set()
        self._alias_to_slug: dict[str, str] = {}
        self.reindex()

    def reindex(self) -> None:
        """Rebuild slug set and alias→slug map from the current store state."""
        self._slugs = set()
        self._alias_to_slug = {}
        for slug, page in self._store.all_pages():
            self._slugs.add(slug)
            for alias in page.aliases:
                # First-wins for alias collisions (deterministic across ingests).
                self._alias_to_slug.setdefault(alias, slug)

    def resolve(self, target: str) -> str | None:
        """Two-stage lookup: filename first, then alias. None on dead link."""
        if target in self._slugs:
            return target
        return self._alias_to_slug.get(target)

    def dead_links(self, page: WikiPage, page_slug: str) -> list[WikiLink]:
        """Return links from `page` that resolve to nothing (excluding self-links)."""
        dead: list[WikiLink] = []
        for link in page.links:
            resolved = self.resolve(link.target)
            if resolved is None:
                dead.append(link)
            # Self-links are not dead (they resolve to self)
        return dead
