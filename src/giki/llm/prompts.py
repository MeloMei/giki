"""Prompt template rendering: `{{ var }}` substitution in .md files.

Kept intentionally minimal -- no Jinja2 dependency. Templates are LLM
prompts, not user-facing content, so we don't need conditionals or loops.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptError(Exception):
    """Missing required variable when rendering a prompt."""


class PromptTemplate:
    def __init__(self, source: str, name: str = "<inline>"):
        self.source = source
        self.name = name
        # Preserve order of first appearance for stable error messages
        seen: dict[str, None] = {}
        for var in _VAR_RE.findall(source):
            seen.setdefault(var, None)
        self._vars: tuple[str, ...] = tuple(seen)

    @classmethod
    def from_file(cls, path: Path) -> "PromptTemplate":
        p = Path(path)
        return cls(p.read_text(encoding="utf-8"), name=str(p))

    @classmethod
    def from_package(cls, filename: str) -> "PromptTemplate":
        """Load a template from the giki.templates package."""
        try:
            text = (
                resources.files("giki.templates").joinpath(filename).read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError, IsADirectoryError) as e:
            raise PromptError(
                f"template {filename!r} not found in giki.templates package"
            ) from e
        return cls(text, name=f"giki.templates/{filename}")

    def render(self, **kwargs) -> str:
        missing = [v for v in self._vars if v not in kwargs]
        if missing:
            raise PromptError(
                f"template {self.name}: missing variables {missing}"
            )

        def replace(match: re.Match) -> str:
            return str(kwargs[match.group(1)])

        return _VAR_RE.sub(replace, self.source)
