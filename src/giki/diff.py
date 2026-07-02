"""Git diff extraction and file-change classification for review."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .review_models import ChangeType, FileChange

_STATUS_MAP = {
    "A": ChangeType.NEW,
    "M": ChangeType.UPDATED,
    "D": ChangeType.DELETED,
}


def parse_name_status(output: str) -> list[FileChange]:
    """Parse ``git diff --name-status`` output into FileChange list."""
    changes: list[FileChange] = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0].strip()
        if status.startswith("R"):
            if len(parts) >= 3:
                changes.append(
                    FileChange(
                        path=parts[2],
                        change_type=ChangeType.RENAMED,
                        old_path=parts[1],
                    )
                )
        else:
            ct = _STATUS_MAP.get(status)
            if ct and len(parts) >= 2:
                changes.append(FileChange(path=parts[1], change_type=ct))
    return changes


def get_diff_changes(
    repo_root: Path, *, base: str = "main"
) -> list[FileChange]:
    """Get file changes between ``base`` and HEAD using three-dot diff."""
    result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--name-status"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return parse_name_status(result.stdout)


def get_pr_diff_changes(pr_id: int, *, repo_root: Path) -> list[FileChange]:
    """Get file changes for a PR. Uses local diff (PR branch checked out)."""
    return get_diff_changes(repo_root)


def read_file_at_commit(
    repo_root: Path, path: str, commit: str
) -> str | None:
    """Read file content at a specific commit. None if file didn't exist."""
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    return result.stdout if result.returncode == 0 else None


def classify_changes(
    changes: list[FileChange],
) -> dict[str, list[FileChange]]:
    """Partition changes into wiki / index / rules / other buckets."""
    classified: dict[str, list[FileChange]] = {
        "wiki": [],
        "index": [],
        "rules": [],
        "other": [],
    }
    for change in changes:
        p = change.path
        if p.startswith("wiki/") and p.endswith(".md"):
            classified["wiki"].append(change)
        elif p == "index.md":
            classified["index"].append(change)
        elif p == "wiki-rules.md":
            classified["rules"].append(change)
        else:
            classified["other"].append(change)
    return classified
