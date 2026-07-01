"""Persistent state: `.giki-state/sources.json` tracks ingested-source hashes.

Stored as JSON keyed by POSIX-normalized source path (relative or absolute
depending on caller). This file is regeneratable — `.gitignore` excludes it
by default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceState:
    root: Path
    entries: dict[str, dict] = field(default_factory=dict)
    # entries: { "sources/a.md": {"sha256": "...", "pages": [...]} }

    @classmethod
    def load(cls, root: Path) -> "SourceState":
        root = Path(root).resolve()
        p = root / ".giki-state" / "sources.json"
        if not p.exists():
            return cls(root=root, entries={})
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return cls(root=root, entries={})
        if not isinstance(data, dict):
            return cls(root=root, entries={})
        entries = data.get("sources", {})
        if not isinstance(entries, dict):
            entries = {}
        return cls(root=root, entries=entries)

    def save(self) -> None:
        state_dir = self.root / ".giki-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        payload = {"sources": self.entries}
        p = state_dir / "sources.json"
        p.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def needs_ingest(self, source_path: Path, sha256: str) -> bool:
        key = _norm(source_path)
        entry = self.entries.get(key)
        return entry is None or entry.get("sha256") != sha256

    def mark(self, source_path: Path, sha256: str, *, pages: list[str]) -> None:
        key = _norm(source_path)
        self.entries[key] = {"sha256": sha256, "pages": list(pages)}

    def pages_for(self, source_path: Path) -> list[str]:
        key = _norm(source_path)
        return list(self.entries.get(key, {}).get("pages", []))


def _norm(p: Path) -> str:
    """Normalize a Path to a POSIX-style string for cross-platform stability."""
    return str(p).replace("\\", "/")
