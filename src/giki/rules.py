"""Parse wiki-rules.md into structured Rule objects."""

from __future__ import annotations

import re
from pathlib import Path

from .review_models import Rule

_ANCHOR_RE = re.compile(r"^##\s+(R-\d+)\s*(.*)?$", re.MULTILINE)
_SEVERITY_RE = re.compile(r"severity:\s*`(blocker|warn|nit)`")


def parse_rules(path: Path) -> list[Rule]:
    """Parse wiki-rules.md, splitting by ## R-N anchors.

    Raises FileNotFoundError if file missing.
    Raises ValueError if no R-N anchors found.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"wiki-rules.md not found: {path}")

    text = path.read_text(encoding="utf-8")
    matches = list(_ANCHOR_RE.finditer(text))
    if not matches:
        raise ValueError(f"no ## R-N anchors found in {path}")

    rules: list[Rule] = []
    for i, match in enumerate(matches):
        anchor = match.group(1)
        name = (match.group(2) or "").strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        sev_match = _SEVERITY_RE.search(body)
        severity = sev_match.group(1) if sev_match else "warn"

        rules.append(Rule(anchor=anchor, name=name, severity=severity, body=body))

    return rules
