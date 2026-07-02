"""Parse wiki/*.md pages into structured WikiPage objects.

Frontmatter format (YAML between `---` fences):
    title: str        (required)
    aliases: list     (optional, default [])
    tags: list        (optional, default [])
    created: str      (required, ISO 8601 with tz)
    updated: str      (required, ISO 8601 with tz)
    sources: list     (optional; absence marks page as hand-written)

Wikilink syntax:
    [[target]] or [[target|display]] or [[target#heading]] (# ignored in v0.1)
    [[type::target]] or [[type::target|display]]  (typed wikilinks, v0.2)
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any

import yaml


def _as_iso_str(value: Any) -> str:
    """Render a frontmatter timestamp value as an ISO 8601 string.

    PyYAML parses ISO timestamps into ``datetime`` objects; ``str(dt)`` uses
    a space separator instead of ``T``. Force ``isoformat`` for datetimes so
    round-tripping preserves the original textual form.
    """
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    return str(value)


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[(?:([a-z][a-z_-]*)::)?([^\[\]\|]+?)(?:\|([^\[\]]+?))?\]\]")


class ParseError(Exception):
    """Wiki page cannot be parsed."""


@dataclass(frozen=True)
class WikiLink:
    target: str
    display: str | None
    link_type: str | None = None


@dataclass
class WikiPage:
    title: str
    aliases: list[str]
    tags: list[str]
    created: str
    updated: str
    sources: list[dict[str, Any]]
    body: str
    links: list[WikiLink] = field(default_factory=list)

    @property
    def is_hand_written(self) -> bool:
        return not self.sources


def parse_page(text: str) -> WikiPage:
    """Parse a full wiki page (frontmatter + body). Raises ParseError."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ParseError("missing YAML frontmatter (must start with '---\n')")

    fm_raw, body = m.group(1), m.group(2)
    try:
        fm = yaml.safe_load(fm_raw)
    except yaml.YAMLError as e:
        raise ParseError(f"malformed YAML frontmatter: {e}") from e

    if not isinstance(fm, dict):
        raise ParseError("frontmatter must be a YAML mapping (key: value)")

    for req in ("title", "created", "updated"):
        if req not in fm:
            raise ParseError(f"frontmatter missing required field {req!r}")

    return WikiPage(
        title=str(fm["title"]),
        aliases=list(fm.get("aliases") or []),
        tags=list(fm.get("tags") or []),
        created=_as_iso_str(fm["created"]),
        updated=_as_iso_str(fm["updated"]),
        sources=list(fm.get("sources") or []),
        body=body,
        links=_extract_links(body),
    )


def _extract_links(body: str) -> list[WikiLink]:
    links: list[WikiLink] = []
    for match in _WIKILINK_RE.finditer(body):
        link_type = match.group(1)  # None when no ``type::`` prefix
        target = match.group(2).strip()
        display = match.group(3).strip() if match.group(3) else None
        # v0.1: strip #heading suffix if present
        if "#" in target:
            target = target.split("#", 1)[0].strip()
        if target:
            links.append(WikiLink(target=target, display=display, link_type=link_type))
    return links
