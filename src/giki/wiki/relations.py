"""Canonical relation types for typed wikilinks ([[type::target]]).

Eight relation types are supported (spec §9.5):

    requires       — A depends on understanding B first
    contradicts    — A and B make conflicting claims (bidirectional)
    implements     — A is a concrete realization of B
    extends        — A builds upon or specializes B
    example-of     — A is an example of B
    related        — A is related to B (generic, bidirectional)
    prerequisite   — A must be understood before B
    alternative    — A is an alternative to B (bidirectional)
"""

from __future__ import annotations

RELATION_TYPES: frozenset[str] = frozenset(
    {
        "requires",
        "contradicts",
        "implements",
        "extends",
        "example-of",
        "related",
        "prerequisite",
        "alternative",
    }
)

_RELATION_META: dict[str, dict[str, str]] = {
    "requires": {
        "direction": "forward",
        "description": "A depends on understanding B first",
    },
    "contradicts": {
        "direction": "bidirectional",
        "description": "A and B make conflicting claims",
    },
    "implements": {
        "direction": "forward",
        "description": "A is a concrete realization of B",
    },
    "extends": {
        "direction": "forward",
        "description": "A builds upon or specializes B",
    },
    "example-of": {
        "direction": "forward",
        "description": "A is an example of B",
    },
    "related": {
        "direction": "bidirectional",
        "description": "A is related to B (generic)",
    },
    "prerequisite": {
        "direction": "forward",
        "description": "A must be understood before B",
    },
    "alternative": {
        "direction": "bidirectional",
        "description": "A is an alternative to B",
    },
}


def is_valid_relation_type(link_type: str) -> bool:
    """Return True if *link_type* is one of the 8 canonical relation types."""
    return link_type in RELATION_TYPES


def get_relation_info(link_type: str) -> dict[str, str]:
    """Return ``{"direction": ..., "description": ...}`` for *link_type*.

    Raises ``KeyError`` if *link_type* is not a valid relation type.
    """
    if link_type not in _RELATION_META:
        raise KeyError(f"unknown relation type: {link_type!r}")
    return dict(_RELATION_META[link_type])
