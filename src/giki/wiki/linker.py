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


import re

_RELATED_BLOCK_RE = re.compile(
    r"(?:\n{1,2}---\n{1,2})?\n?##\s+Related\s*\n(?:\s*-\s+\[\[[^\]]+\]\][^\n]*\n?)*",
    re.MULTILINE,
)


def apply_related_block(
    body: str,
    neighbors: list[str],
    *,
    min_neighbors: int = 1,
) -> str:
    """Append/replace/remove the `## Related` block based on neighbors.

    - len(neighbors) < min_neighbors:
        * If existing block present → remove it.
        * Otherwise → return body unchanged.
    - Otherwise:
        * Existing block → replace its bullet list.
        * No existing block → append `---\n\n## Related\n- [[slug]]\n...` at end.
    """
    # Detect an existing Related block
    match = _RELATED_BLOCK_RE.search(body)

    if len(neighbors) < min_neighbors:
        if match:
            # Remove existing block (and any leading `---` separator we injected)
            before = body[: match.start()].rstrip() + "\n"
            after = body[match.end():]
            return (before + after).rstrip() + "\n"
        return body

    new_block = _format_related_block(neighbors)

    if match:
        before = body[: match.start()].rstrip() + "\n"
        after = body[match.end():]
        # Strip any leading blank lines from after so we don't accumulate whitespace
        after = after.lstrip("\n")
        joiner = "\n" if after else ""
        return before + "\n---\n\n" + new_block + "\n" + (joiner + after if after else "")

    # First time: append with separator
    body_trimmed = body.rstrip() + "\n"
    return body_trimmed + "\n---\n\n" + new_block + "\n"


def _format_related_block(neighbors: list[str]) -> str:
    lines = ["## Related"]
    for slug in neighbors:
        lines.append(f"- [[{slug}]]")
    return "\n".join(lines)
