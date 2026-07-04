"""Shared data types for the giki review pipeline."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ChangeType(enum.Enum):
    NEW = "new"
    UPDATED = "updated"
    DELETED = "deleted"
    RENAMED = "renamed"


class Verdict(enum.Enum):
    APPROVE = "approve"
    COMMENT = "comment"
    REQUEST_CHANGES = "request-changes"

    @property
    def exit_code(self) -> int:
        if self is Verdict.REQUEST_CHANGES:
            return 1
        return 0


@dataclass(frozen=True)
class Rule:
    anchor: str
    name: str
    severity: str
    body: str


@dataclass(frozen=True)
class FileChange:
    path: str
    change_type: ChangeType
    old_path: str | None = None

    @property
    def wiki_slug(self) -> str | None:
        if self.path.startswith("wiki/") and self.path.endswith(".md"):
            return self.path[len("wiki/") : -len(".md")]
        return None


@dataclass(frozen=True)
class MechanicalFinding:
    rule_id: str
    severity: str
    message: str
    page_slug: str | None = None

    @property
    def finding_type(self) -> str:
        return "mechanical"

    def to_semantic(self) -> "SemanticFinding":
        return SemanticFinding(
            rule_id=self.rule_id,
            severity=self.severity,
            evidence=self.message,
            suggestion="",
            page_slug=self.page_slug,
        )


@dataclass(frozen=True)
class SemanticFinding:
    rule_id: str
    severity: str
    evidence: str
    suggestion: str
    page_slug: str | None = None

    @property
    def finding_type(self) -> str:
        return "semantic"


@dataclass(frozen=True)
class ReviewResult:
    verdict: Verdict
    findings: list[MechanicalFinding | SemanticFinding]
    pages_reviewed: int
    pages_skipped: int
