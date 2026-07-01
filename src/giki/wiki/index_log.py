"""Auto-maintained index.md (categorized) and log.md (chronological)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


INDEX_BEGIN = "<!-- giki:index-begin -->"
INDEX_END = "<!-- giki:index-end -->"

_INDEX_HEADER = f"""# Index

_Auto-maintained by giki. Human edits above the marker are preserved._

{INDEX_BEGIN}
{INDEX_END}
"""

_INDEX_LINE_RE = re.compile(r"^-\s+\[\[([a-zA-Z0-9-]+)\]\]\s+\u2014\s+(.+)$")


@dataclass(frozen=True)
class IndexEntry:
    slug: str
    title: str
    tags: list[str] = field(default_factory=list)


def append_to_index(index_path: Path, entries: list[IndexEntry]) -> None:
    """Append entries to the auto-maintained block in index.md.

    Idempotent: entries already present under a category are not duplicated.
    Preserves anything above the `<!-- giki:index-begin -->` marker.
    """
    index_path = Path(index_path)
    if not index_path.exists():
        index_path.write_text(_INDEX_HEADER, encoding="utf-8")

    text = index_path.read_text(encoding="utf-8")
    before, current_block, after = _split_index(text)

    current: dict[str, dict[str, str]] = _parse_index_block(current_block)

    for entry in entries:
        cats = entry.tags if entry.tags else ["Uncategorized"]
        for cat in cats:
            current.setdefault(cat, {})[entry.slug] = entry.title

    new_block = _format_index_block(current)
    index_path.write_text(before + new_block + after, encoding="utf-8")


def _split_index(text: str) -> tuple[str, str, str]:
    """Return (before_marker, block_between_markers, after_end_marker)."""
    if INDEX_BEGIN not in text or INDEX_END not in text:
        preamble = text.rstrip() + "\n\n" if text.strip() else ""
        return (preamble + INDEX_BEGIN + "\n", "", "\n" + INDEX_END + "\n")

    begin_idx = text.index(INDEX_BEGIN) + len(INDEX_BEGIN)
    end_idx = text.index(INDEX_END)
    before = text[:begin_idx] + "\n"
    block = text[begin_idx:end_idx].strip("\n")
    after = "\n" + text[end_idx:]
    return before, block, after


def _parse_index_block(block: str) -> dict[str, dict[str, str]]:
    """Parse existing block into {category: {slug: title}}."""
    result: dict[str, dict[str, str]] = {}
    current_cat: str | None = None
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_cat = line[3:].strip()
            result.setdefault(current_cat, {})
        elif current_cat is not None:
            m = _INDEX_LINE_RE.match(line)
            if m:
                slug, title = m.group(1), m.group(2).strip()
                result[current_cat][slug] = title
    return result


def _format_index_block(categorized: dict[str, dict[str, str]]) -> str:
    if not categorized:
        return ""
    lines: list[str] = []
    for cat in sorted(categorized):
        entries = categorized[cat]
        if not entries:
            continue
        lines.append(f"## {cat}")
        for slug in sorted(entries):
            lines.append(f"- [[{slug}]] \u2014 {entries[slug]}")
        lines.append("")
    return "\n" + "\n".join(lines).rstrip() + "\n"


_LOG_HEADER = """# Log

_Chronological ingest log. Newest at top._

"""


@dataclass(frozen=True)
class LogEvent:
    timestamp_iso: str
    source_path: str
    pages_created: list[str]
    pages_updated: list[str]
    pages_failed: list[str]


def append_to_log(log_path: Path, event: LogEvent) -> None:
    """Prepend a new event to log.md (newest at top)."""
    log_path = Path(log_path)
    if not log_path.exists():
        log_path.write_text(_LOG_HEADER, encoding="utf-8")

    text = log_path.read_text(encoding="utf-8")
    if not text.startswith("# Log"):
        text = _LOG_HEADER + text

    entry = _format_log_entry(event)

    header_end = text.find("_\n\n")
    if header_end != -1:
        header_end += len("_\n\n")
    else:
        header_end = len(_LOG_HEADER)

    new_text = text[:header_end] + entry + text[header_end:]
    log_path.write_text(new_text, encoding="utf-8")


def _format_log_entry(event: LogEvent) -> str:
    def _format_list(items: list[str]) -> str:
        return ", ".join(f"[[{s}]]" for s in items) if items else "(none)"

    return (
        f"## {event.timestamp_iso}\n\n"
        f"**source:** `{event.source_path}`\n\n"
        f"- created: {_format_list(event.pages_created)}\n"
        f"- updated: {_format_list(event.pages_updated)}\n"
        f"- failed: {_format_list(event.pages_failed)}\n\n"
        f"---\n\n"
    )
