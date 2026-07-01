"""Pure utility functions. No I/O, no side effects (except iso_now reading system clock)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def extract_json(text: str) -> Any:
    """Extract the first JSON object/array from text.

    Handles:
      - Bare JSON: '{"a": 1}'
      - Fenced block: '```json\n{"a": 1}\n```' or '```\n{"a": 1}\n```'
      - Trailing/leading prose

    Raises ValueError if no valid JSON is found or the JSON is malformed.
    """
    if not isinstance(text, str):
        raise ValueError("extract_json requires a string input")

    stripped = text.strip()

    # Prefer a fenced code block if present.
    fence_match = _FENCE_RE.search(stripped)
    candidate = fence_match.group(1) if fence_match else stripped

    # Locate the first JSON opener (object or array).
    opener_pos = -1
    for i, ch in enumerate(candidate):
        if ch == "{" or ch == "[":
            opener_pos = i
            break
    if opener_pos == -1:
        raise ValueError("no JSON object or array found in input")

    open_ch = candidate[opener_pos]
    close_ch = "}" if open_ch == "{" else "]"

    depth = 0
    in_string = False
    escape = False
    end_pos = -1

    for i in range(opener_pos, len(candidate)):
        ch = candidate[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                end_pos = i
                break

    if end_pos == -1:
        raise ValueError("unterminated JSON: no matching closing bracket found")

    snippet = candidate[opener_pos:end_pos + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc.msg}") from exc


def to_slug(text: str, max_len: int = 80) -> str:
    """Convert text to a kebab-case slug matching ``[a-z0-9-]+``.

    NOTE: The primary slug source is the LLM (Analyze phase); this is a
    mechanical fallback for programmatic normalization/deduplication.

    Raises ValueError if the resulting slug is empty.
    """
    lowered = text.lower()
    slug = _SLUG_STRIP.sub("-", lowered).strip("-")
    if not slug:
        raise ValueError("slug is empty after normalization")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
        if not slug:
            raise ValueError("slug is empty after truncation")
    return slug


def iso_now() -> str:
    """Return current time as ISO 8601 with local timezone offset (seconds precision)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def safe_relpath(root: Path, target: Path) -> Path:
    """Return ``target`` as a path relative to ``root``.

    Resolves both paths first, so ``..`` segments are normalized before the
    containment check.

    Raises ValueError if the resolved target lies outside ``root``.
    """
    root_r = Path(root).resolve()
    target_r = Path(target).resolve()
    try:
        return target_r.relative_to(root_r)
    except ValueError as exc:
        raise ValueError(f"path {target} escapes root {root}") from exc
