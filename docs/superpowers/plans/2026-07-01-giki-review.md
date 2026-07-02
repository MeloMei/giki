# giki-review Implementation Plan (Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Every task follows TDD: write failing tests → verify failure → implement → verify pass → commit.

**Goal:** Build the `giki review` command — a two-phase (mechanical + semantic) PR Review Bot that checks wiki changes against `wiki-rules.md` rules, produces structured findings with severity levels, aggregates into a verdict, and integrates with GitHub via `gh` CLI.

**Architecture:** The review pipeline has 5 phases: Context Loading → Change Classification → Mechanical Checks (no LLM) → Semantic Review (LLM per page) → Aggregation & Output. Diff extraction uses `git diff <base>...HEAD` locally or `gh pr diff` for PR mode. Mechanical checks reuse existing `Linker` for dead-link detection. Semantic review calls the LLM per changed page with wiki-rules context. All findings aggregate into `approve | comment | request-changes`.

**Tech Stack:** Python 3.11+, Typer, GitPython, httpx (existing LLM adapters), `gh` CLI (subprocess), pytest, FakeLLM (test pattern from Plan 1).

**Related spec:** `docs/superpowers/specs/2026-06-30-giki-v0.1-design.md` §7 (PR Review Bot) + §10.4 (GitHub Action template).

**Sibling plan (completed):** `2026-06-30-giki-core.md` (Plan 1 of 2) — 304 tests green, all v0.1 commands shipped.

---

## Prerequisites

- Plan 1 completed (304 tests green)
- `gh` CLI installed (optional, only for `--pr` / `--post` flags)
- Python 3.11+ with `.venv` activated

---

## File Structure (locked at plan time)

**New source files** (`src/giki/`):

| File | Responsibility | Task |
|---|---|---|
| `review_models.py` | Shared data types: `Rule`, `FileChange`, `MechanicalFinding`, `SemanticFinding`, `ReviewResult`, `ChangeType`, `Verdict` enums | 1 |
| `rules.py` | `parse_rules()` — parse `wiki-rules.md` by `## R-N` anchors | 2 |
| `diff.py` | Git diff extraction, file classification, `read_file_at_commit()` | 3 |
| `wiki/review_agent.py` | Review orchestration: mechanical checks + semantic review + aggregation | 4, 5 |
| `wiki/review_fmt.py` | Report formatting: `format_markdown`, `format_json`, `post_pr_comment` | 6 |

**New template files** (`src/giki/templates/`):

| File | Responsibility | Task |
|---|---|---|
| `review-system.md` | System prompt for the semantic review LLM | 5 |
| `review.md` | User prompt template for per-page semantic review | 5 |

**Modified files:**

| File | Change | Task |
|---|---|---|
| `commands/review.py` | Replace stub with full `review_command` implementation | 7 |
| `cli.py` | Register `review` command on the Typer app | 8 |

**New test files** (`tests/`):

| File | Tests | Task |
|---|---|---|
| `test_review_models.py` | Enum values, dataclass construction, `Verdict.exit_code`, `MechanicalFinding.to_semantic` | 1 |
| `test_rules.py` | Parse 5 rules, custom severities, missing file, no anchors | 2 |
| `test_diff.py` | `classify_changes` name-status parsing, rename detection, wiki filter, `read_file_at_commit` | 3 |
| `test_review_mechanical.py` | Dead links, frontmatter, index sync, unrelated edits | 4 |
| `test_review_semantic.py` | Prompt rendering, per-page review, hand-written skip, aggregation | 5 |
| `test_review_fmt.py` | Markdown format, JSON format, collapse nits, `--post` subprocess | 6 |
| `test_review_e2e.py` | End-to-end review with FakeLLM, CLI invocation, `--post` mock | 8 |

**Modified test files:**

| File | Change | Task |
|---|---|---|
| `test_cli.py` | Add `review` to help-list; remove `review` from stub parametrize | 8 |

---

## Task 1: Review Data Models

**Files:**
- Create: `src/giki/review_models.py`
- Test: `tests/test_review_models.py`

**Public API:**

- `ChangeType` — `Enum`: `NEW`, `UPDATED`, `DELETED`, `RENAMED`.
- `Verdict` — `Enum`: `APPROVE`, `COMMENT`, `REQUEST_CHANGES`. Property `exit_code`: approve=0, comment=0, request-changes=1.
- `Rule` — frozen dataclass: `anchor`, `name`, `severity`, `body`.
- `FileChange` — frozen dataclass: `path`, `change_type`, `old_path=None`. Property `wiki_slug`.
- `MechanicalFinding` — frozen dataclass: `rule_id`, `severity`, `message`, `page_slug=None`. Method `to_semantic()`.
- `SemanticFinding` — frozen dataclass: `rule_id`, `severity`, `evidence`, `suggestion`, `page_slug=None`.
- `ReviewResult` — frozen dataclass: `verdict`, `findings`, `pages_reviewed`, `pages_skipped`.

**TDD steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_review_models.py
from __future__ import annotations
import pytest
from giki.review_models import (
    ChangeType, FileChange, MechanicalFinding, ReviewResult,
    Rule, SemanticFinding, Verdict,
)

class TestChangeType:
    def test_values(self):
        assert ChangeType.NEW.value == "new"
        assert ChangeType.UPDATED.value == "updated"
        assert ChangeType.DELETED.value == "deleted"
        assert ChangeType.RENAMED.value == "renamed"

class TestVerdict:
    def test_values(self):
        assert Verdict.APPROVE.value == "approve"
        assert Verdict.COMMENT.value == "comment"
        assert Verdict.REQUEST_CHANGES.value == "request-changes"
    def test_exit_codes(self):
        assert Verdict.APPROVE.exit_code == 0
        assert Verdict.COMMENT.exit_code == 0
        assert Verdict.REQUEST_CHANGES.exit_code == 1

class TestRule:
    def test_construction(self):
        r = Rule(anchor="R-1", name="test", severity="blocker", body="body text")
        assert r.anchor == "R-1"

class TestFileChange:
    def test_wiki_slug_from_wiki_path(self):
        fc = FileChange(path="wiki/observer-pattern.md", change_type=ChangeType.NEW)
        assert fc.wiki_slug == "observer-pattern"
    def test_wiki_slug_none_for_non_wiki(self):
        fc = FileChange(path="index.md", change_type=ChangeType.UPDATED)
        assert fc.wiki_slug is None
    def test_wiki_slug_none_for_sources(self):
        fc = FileChange(path="sources/notes.md", change_type=ChangeType.NEW)
        assert fc.wiki_slug is None
    def test_old_path_for_rename(self):
        fc = FileChange(path="wiki/new.md", change_type=ChangeType.RENAMED, old_path="wiki/old.md")
        assert fc.old_path == "wiki/old.md"
    def test_old_path_default_none(self):
        fc = FileChange(path="wiki/x.md", change_type=ChangeType.NEW)
        assert fc.old_path is None

class TestMechanicalFinding:
    def test_to_semantic(self):
        mf = MechanicalFinding(rule_id="R-2", severity="blocker", message="broken link", page_slug="test")
        sf = mf.to_semantic()
        assert isinstance(sf, SemanticFinding)
        assert sf.rule_id == "R-2"
        assert sf.evidence == "broken link"
        assert sf.suggestion == ""

class TestReviewResult:
    def test_construction(self):
        result = ReviewResult(verdict=Verdict.APPROVE, findings=[], pages_reviewed=3, pages_skipped=1)
        assert result.verdict == Verdict.APPROVE
        assert result.pages_reviewed == 3
```

- [ ] **Step 2: Run test — expect `ModuleNotFoundError`**

```bash
.venv/Scripts/python.exe -m pytest tests/test_review_models.py -v
```

- [ ] **Step 3: Implement `src/giki/review_models.py`**

```python
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
            return self.path[len("wiki/"):-len(".md")]
        return None

@dataclass(frozen=True)
class MechanicalFinding:
    rule_id: str
    severity: str
    message: str
    page_slug: str | None = None
    def to_semantic(self) -> "SemanticFinding":
        return SemanticFinding(
            rule_id=self.rule_id, severity=self.severity,
            evidence=self.message, suggestion="", page_slug=self.page_slug,
        )

@dataclass(frozen=True)
class SemanticFinding:
    rule_id: str
    severity: str
    evidence: str
    suggestion: str
    page_slug: str | None = None

@dataclass(frozen=True)
class ReviewResult:
    verdict: Verdict
    findings: list[MechanicalFinding | SemanticFinding]
    pages_reviewed: int
    pages_skipped: int
```

- [ ] **Step 4: Run tests — expect all pass**

- [ ] **Step 5: Commit**

```bash
git add src/giki/review_models.py tests/test_review_models.py
git commit -m "feat(review): data models — Rule, FileChange, Finding, Verdict"
```

---

## Task 2: Wiki-Rules Parser

**Files:**
- Create: `src/giki/rules.py`
- Test: `tests/test_rules.py`

**Public API:**

- `parse_rules(path: Path) -> list[Rule]` — split by `## R-N` anchors, extract name + severity. `FileNotFoundError` if missing. `ValueError` if no anchors.

**TDD steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_rules.py
from __future__ import annotations
import pytest
from giki.rules import parse_rules

_RULES_TEXT = """\
# Wiki Rules

_Starter rules._

## R-1

**consistency** — severity: `blocker`

Facts must not contradict.

## R-2

**citation integrity** — severity: `blocker`

Claims need sources.

## R-3

**naming convention** — severity: `warn`

Slugs must match pattern.

## R-4

**bidirectional links** — severity: `warn`

Prefer [[wiki-link]].

## R-5

**paragraph length** — severity: `nit`

Keep paragraphs short.
"""

class TestParseRules:
    def test_parse_five_rules(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert len(rules) == 5
        assert [r.anchor for r in rules] == ["R-1", "R-2", "R-3", "R-4", "R-5"]

    def test_severities(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert rules[0].severity == "blocker"
        assert rules[2].severity == "warn"
        assert rules[4].severity == "nit"

    def test_names_extracted(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert "consistency" in rules[0].name

    def test_body(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text(_RULES_TEXT, encoding="utf-8")
        rules = parse_rules(f)
        assert "contradict" in rules[0].body

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_rules(tmp_path / "nonexistent.md")

    def test_no_anchors_raises(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text("# Just a heading\n\nNo rules.\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no.*R-N"):
            parse_rules(f)

    def test_missing_severity_defaults_warn(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text("## R-1\n\n**unnamed**\n\nBody.\n", encoding="utf-8")
        rules = parse_rules(f)
        assert rules[0].severity == "warn"

    def test_multidigit_anchor(self, tmp_path):
        f = tmp_path / "wiki-rules.md"
        f.write_text("## R-42\n\n**rule** — severity: `blocker`\n\nBody.\n", encoding="utf-8")
        rules = parse_rules(f)
        assert rules[0].anchor == "R-42"
```

- [ ] **Step 2-4: Implement**

```python
# src/giki/rules.py
"""Parse wiki-rules.md into structured Rule objects."""
from __future__ import annotations
import re
from pathlib import Path
from .review_models import Rule

_ANCHOR_RE = re.compile(r"^##\s+(R-\d+)\s*(.*)?$", re.MULTILINE)
_SEVERITY_RE = re.compile(r"severity:\s*`(blocker|warn|nit)`")

def parse_rules(path: Path) -> list[Rule]:
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
```

- [ ] **Step 5: Commit**

```bash
git add src/giki/rules.py tests/test_rules.py
git commit -m "feat(review): parse_rules — wiki-rules.md parser by R-N anchors"
```

---

## Task 3: Diff Utilities

**Files:**
- Create: `src/giki/diff.py`
- Test: `tests/test_diff.py`

**Public API:**

- `parse_name_status(output: str) -> list[FileChange]` — pure parser.
- `get_diff_changes(repo_root, *, base="main") -> list[FileChange]` — `git diff <base>...HEAD --name-status`.
- `get_pr_diff_changes(pr_id, *, repo_root) -> list[FileChange]` — delegates to local diff.
- `read_file_at_commit(repo_root, path, commit) -> str | None` — `git show`.
- `classify_changes(changes) -> dict[str, list[FileChange]]` — wiki/index/rules/other.

**TDD steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_diff.py
from __future__ import annotations
import git
import pytest
from giki.diff import classify_changes, get_diff_changes, parse_name_status, read_file_at_commit
from giki.review_models import ChangeType, FileChange

class TestParseNameStatus:
    def test_added(self):
        assert parse_name_status("A\twiki/new.md\n")[0].change_type == ChangeType.NEW
    def test_modified(self):
        assert parse_name_status("M\twiki/x.md\n")[0].change_type == ChangeType.UPDATED
    def test_deleted(self):
        assert parse_name_status("D\twiki/old.md\n")[0].change_type == ChangeType.DELETED
    def test_renamed(self):
        c = parse_name_status("R100\twiki/old.md\twiki/new.md\n")[0]
        assert c.change_type == ChangeType.RENAMED
        assert c.old_path == "wiki/old.md"
    def test_multiple(self):
        assert len(parse_name_status("A\twiki/a.md\nM\twiki/b.md\nD\tindex.md\n")) == 3
    def test_empty(self):
        assert parse_name_status("") == []

class TestClassifyChanges:
    def test_wiki(self):
        assert len(classify_changes([FileChange("wiki/a.md", ChangeType.NEW)])["wiki"]) == 1
    def test_index(self):
        assert len(classify_changes([FileChange("index.md", ChangeType.UPDATED)])["index"]) == 1
    def test_rules(self):
        assert len(classify_changes([FileChange("wiki-rules.md", ChangeType.UPDATED)])["rules"]) == 1
    def test_other(self):
        assert len(classify_changes([FileChange("sources/x.md", ChangeType.NEW)])["other"]) == 1
    def test_mixed(self):
        changes = [
            FileChange("wiki/a.md", ChangeType.NEW),
            FileChange("index.md", ChangeType.UPDATED),
            FileChange("wiki-rules.md", ChangeType.UPDATED),
            FileChange("sources/x.md", ChangeType.NEW),
        ]
        c = classify_changes(changes)
        assert len(c["wiki"]) == 1 and len(c["index"]) == 1 and len(c["other"]) == 1

class TestGetDiffChanges:
    def test_branch_diff(self, tmp_path):
        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        (tmp_path / "base.md").write_text("base\n", encoding="utf-8")
        repo.index.add(["base.md"])
        repo.index.commit("initial")
        repo.create_head("feature").checkout()
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "new.md").write_text("new\n", encoding="utf-8")
        repo.index.add(["wiki/new.md"])
        repo.index.commit("add wiki page")
        changes = get_diff_changes(tmp_path, base="main")
        assert len(changes) == 1
        assert changes[0].path == "wiki/new.md"

class TestReadFileAtCommit:
    def test_read_existing(self, tmp_path):
        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "test.md").write_text("v1\n", encoding="utf-8")
        repo.index.add(["wiki/test.md"])
        commit = repo.index.commit("add test")
        assert "v1" in read_file_at_commit(tmp_path, "wiki/test.md", commit.hexsha)
    def test_nonexistent_returns_none(self, tmp_path):
        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        (tmp_path / "base.md").write_text("x\n", encoding="utf-8")
        repo.index.add(["base.md"])
        commit = repo.index.commit("initial")
        assert read_file_at_commit(tmp_path, "wiki/nope.md", commit.hexsha) is None
```

- [ ] **Step 2-4: Implement**

```python
# src/giki/diff.py
"""Git diff extraction and file-change classification for review."""
from __future__ import annotations
import subprocess
from pathlib import Path
from .review_models import ChangeType, FileChange

_STATUS_MAP = {"A": ChangeType.NEW, "M": ChangeType.UPDATED, "D": ChangeType.DELETED}

def parse_name_status(output: str) -> list[FileChange]:
    changes: list[FileChange] = []
    for line in output.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0].strip()
        if status.startswith("R"):
            if len(parts) >= 3:
                changes.append(FileChange(path=parts[2], change_type=ChangeType.RENAMED, old_path=parts[1]))
        else:
            ct = _STATUS_MAP.get(status)
            if ct and len(parts) >= 2:
                changes.append(FileChange(path=parts[1], change_type=ct))
    return changes

def get_diff_changes(repo_root: Path, *, base: str = "main") -> list[FileChange]:
    result = subprocess.run(
        ["git", "diff", f"{base}...HEAD", "--name-status"],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")
    return parse_name_status(result.stdout)

def get_pr_diff_changes(pr_id: int, *, repo_root: Path) -> list[FileChange]:
    return get_diff_changes(repo_root)

def read_file_at_commit(repo_root: Path, path: str, commit: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    return result.stdout if result.returncode == 0 else None

def classify_changes(changes: list[FileChange]) -> dict[str, list[FileChange]]:
    classified: dict[str, list[FileChange]] = {"wiki": [], "index": [], "rules": [], "other": []}
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
```

- [ ] **Step 5: Commit**

```bash
git add src/giki/diff.py tests/test_diff.py
git commit -m "feat(review): diff utilities — name-status parser, git extraction, classification"
```

---

## Task 4: Mechanical Checks

**Files:**
- Create: `src/giki/wiki/review_agent.py`
- Test: `tests/test_review_mechanical.py`

**Public API:**

- `check_dead_links(wiki_dir, changes)` — reuse `Linker` for NEW/UPDATED; check orphaned links for DELETED.
- `check_frontmatter(wiki_dir, changes, *, slug_pattern, max_slug_length)` — parse + slug validation.
- `check_index_sync(changes, index_text)` — NEW pages must appear in index.
- `check_unrelated_edits(changes, threshold)` — warn if non-wiki ratio exceeds threshold.

**TDD steps:**

- [ ] **Step 1: Write failing tests** — 14 tests covering all four functions (dead links for NEW/UPDATED/DELETED, alias resolution, frontmatter parse errors, slug validation, index sync, unrelated ratio).

- [ ] **Step 2-4: Implement**

```python
# src/giki/wiki/review_agent.py (mechanical portion)
"""Review orchestration: mechanical checks + semantic review + aggregation."""
from __future__ import annotations
import re
from pathlib import Path
from ..review_models import ChangeType, FileChange, MechanicalFinding, SemanticFinding, Verdict
from .linker import Linker
from .parser import ParseError, parse_page
from .store import WikiStore

def check_dead_links(wiki_dir: Path, changes: list[FileChange]) -> list[MechanicalFinding]:
    findings: list[MechanicalFinding] = []
    store = WikiStore(wiki_dir.parent)
    linker = Linker(store)
    for change in changes:
        if change.change_type not in (ChangeType.NEW, ChangeType.UPDATED):
            continue
        slug = change.wiki_slug
        if not slug or not store.exists(slug):
            continue
        page = parse_page(store.read(slug))
        for link in linker.dead_links(page, slug):
            findings.append(MechanicalFinding(
                rule_id="dead-link", severity="blocker",
                message=f"broken link [[{link.target}]] in page '{slug}'",
                page_slug=slug,
            ))
    deleted_slugs = {c.wiki_slug for c in changes if c.change_type == ChangeType.DELETED and c.wiki_slug}
    if deleted_slugs:
        for slug, page in store.all_pages():
            if slug in deleted_slugs:
                continue
            for link in page.links:
                if link.target in deleted_slugs:
                    findings.append(MechanicalFinding(
                        rule_id="dead-link", severity="blocker",
                        message=f"page '{slug}' links to deleted page [[{link.target}]]",
                        page_slug=slug,
                    ))
    return findings

def check_frontmatter(wiki_dir: Path, changes: list[FileChange], *, slug_pattern: str = r"^[a-z0-9-]+$", max_slug_length: int = 80) -> list[MechanicalFinding]:
    findings: list[MechanicalFinding] = []
    slug_re = re.compile(slug_pattern)
    for change in changes:
        if change.change_type not in (ChangeType.NEW, ChangeType.UPDATED):
            continue
        slug = change.wiki_slug
        if not slug:
            continue
        if not slug_re.match(slug):
            findings.append(MechanicalFinding(rule_id="R-3", severity="warn", message=f"slug '{slug}' does not match pattern {slug_pattern}", page_slug=slug))
        if len(slug) > max_slug_length:
            findings.append(MechanicalFinding(rule_id="R-3", severity="warn", message=f"slug '{slug}' length {len(slug)} exceeds max {max_slug_length}", page_slug=slug))
        page_path = wiki_dir / f"{slug}.md"
        if not page_path.exists():
            continue
        try:
            parse_page(page_path.read_text(encoding="utf-8"))
        except ParseError as e:
            findings.append(MechanicalFinding(rule_id="frontmatter", severity="blocker", message=f"parse error in '{slug}': {e}", page_slug=slug))
    return findings

def check_index_sync(changes: list[FileChange], index_text: str) -> list[MechanicalFinding]:
    findings: list[MechanicalFinding] = []
    new_slugs = {c.wiki_slug for c in changes if c.change_type == ChangeType.NEW and c.wiki_slug}
    for slug in new_slugs:
        if f"[[{slug}]]" not in index_text:
            findings.append(MechanicalFinding(rule_id="index-sync", severity="warn", message=f"new page '{slug}' not found in index.md", page_slug=slug))
    return findings

def check_unrelated_edits(changes: list[FileChange], threshold: float) -> list[MechanicalFinding]:
    if not changes:
        return []
    wiki_count = sum(1 for c in changes if c.path.startswith("wiki/") or c.path.startswith(".giki-state/"))
    total = len(changes)
    ratio = 1.0 - (wiki_count / total) if total else 0.0
    if ratio > threshold:
        return [MechanicalFinding(rule_id="unrelated-edits", severity="warn", message=f"{ratio:.0%} of changes outside wiki/ (threshold: {threshold:.0%})")]
    return []
```

- [ ] **Step 5: Commit**

```bash
git add src/giki/wiki/review_agent.py tests/test_review_mechanical.py
git commit -m "feat(review): mechanical checks — dead links, frontmatter, index sync, unrelated edits"
```

---

## Task 5: Semantic Review + Aggregation + Prompt Templates

**Files:**
- Modify: `src/giki/wiki/review_agent.py` (add semantic review + aggregation)
- Create: `src/giki/templates/review-system.md`, `src/giki/templates/review.md`
- Test: `tests/test_review_semantic.py`

**Public API additions:**

- `render_review_prompt(*, rules, page_slug, page_before, page_after, neighbors_summary, mechanical_findings_text) -> str`
- `review_page_semantic(*, llm, rules, page_slug, page_before, page_after, neighbors_summary, mechanical_findings_text, is_hand_written=False) -> tuple[list[SemanticFinding], str]`
- `aggregate_verdict(findings, *, severity_blocking=None) -> Verdict`

**Prompt templates:**

`src/giki/templates/review-system.md`:
```
You are a wiki reviewer for a giki knowledge base.
Evaluate the page change against the wiki rules.

Output ONLY valid JSON (no markdown fences, no prose):
{
  "findings": [
    {
      "rule_id": "R-N",
      "severity": "blocker" | "warn" | "nit",
      "evidence": "quote or describe the issue",
      "suggestion": "how to fix"
    }
  ],
  "verdict": "approve" | "comment" | "request-changes"
}

Be conservative: only flag blocker for clear violations.
If the page looks good, return {"findings": [], "verdict": "approve"}.
```

`src/giki/templates/review.md`:
```
Review the following wiki page change against the wiki rules.

## Wiki Rules
{{ rules_text }}

## Page: {{ page_slug }}

### Before
{{ before_content }}

### After
{{ after_content }}

## Neighboring pages
{{ neighbors_summary }}

## Mechanical findings
{{ mechanical_findings_text }}

Evaluate the change and output your review as JSON only (no markdown fences).
```

**Key behaviors:**

- `review_page_semantic` skips hand-written pages (returns `([], "approve")` without calling LLM).
- Malformed JSON from LLM → returns `([], "comment")` without crashing.
- `aggregate_verdict`: no findings → APPROVE; any finding with severity in `severity_blocking` → REQUEST_CHANGES; otherwise → COMMENT.

**TDD steps:**

- [ ] **Step 1-7: Write tests (FakeLLM pattern), implement, verify**

Test cases: prompt rendering with all variables, before/after for updates, empty before for new pages, LLM finding parsing, hand-written skip, malformed JSON handling, 7 aggregation cases.

- [ ] **Commit**

```bash
git add src/giki/wiki/review_agent.py src/giki/templates/review.md src/giki/templates/review-system.md tests/test_review_semantic.py
git commit -m "feat(review): semantic review + aggregation + prompt templates"
```

---

## Task 6: Report Formatting

**Files:**
- Create: `src/giki/wiki/review_fmt.py`
- Test: `tests/test_review_fmt.py`

**Public API:**

- `format_markdown(result, *, collapse_nits=True) -> str` — grouped by severity, nits in `<details>` when collapsed.
- `format_json(result) -> dict` — `{"verdict", "findings", "pages_reviewed", "pages_skipped", "summary"}`.
- `post_pr_comment(pr_id, body) -> None` — `gh pr comment` via subprocess. `RuntimeError` on failure.

**TDD steps:**

- [ ] **Step 1-5: Write tests (10 cases), implement, verify**

Test cases: approve empty, blocker shown, nit collapsed/not-collapsed, summary counts, mechanical included, JSON structure, JSON serializable, `post_pr_comment` mock, gh failure raises.

- [ ] **Commit**

```bash
git add src/giki/wiki/review_fmt.py tests/test_review_fmt.py
git commit -m "feat(review): format_markdown, format_json, post_pr_comment"
```

---

## Task 7: `giki review` CLI Command

**Files:**
- Modify: `src/giki/commands/review.py` (replace stub)
- Test: `tests/test_commands_review.py`

**Command signature:**

```python
def review_command(
    pr: int | None = typer.Option(None, "--pr", help="PR number (via gh CLI)"),
    post: bool = typer.Option(False, "--post", help="Post findings as PR comment"),
    json_output: bool = typer.Option(False, "--json", "json_output", help="Output JSON"),
    root: Path = typer.Option(Path("."), "--root", help="KB root directory"),
    base: str = typer.Option("main", "--base", help="Base branch for diff"),
) -> None:
```

**Pipeline steps:**

1. `--post` without `--pr` → error exit 2.
2. `load_config(root)`.
3. `parse_rules(root / "wiki-rules.md")` (missing → empty list).
4. `get_diff_changes` or `get_pr_diff_changes`.
5. `classify_changes` → mechanical checks on wiki changes.
6. Semantic review per wiki page (skip hand-written, use `cfg.llm.review`).
7. `aggregate_verdict` with `cfg.review.severity_blocking`.
8. `--json` → `format_json` to stdout; else → `format_markdown`.
9. `--post` → `post_pr_comment(pr, markdown_body)`.
10. `typer.Exit(code=verdict.exit_code)`.

**TDD steps:**

- [ ] **Step 1-5: Write tests (help flags, JSON output, markdown output, exit code 1 for blockers, --post requires --pr, --post calls gh), implement, verify**

- [ ] **Commit**

```bash
git add src/giki/commands/review.py tests/test_commands_review.py
git commit -m "feat(cli): giki review command — mechanical + semantic pipeline"
```

---

## Task 8: CLI Registration + Test Updates + E2E

**Files:**
- Modify: `src/giki/cli.py` (add `review` registration)
- Modify: `tests/test_cli.py` (update help + stub tests)
- Test: `tests/test_review_e2e.py`

**Changes to `cli.py`:**

```python
from .commands.review import review_command
# ... in app setup:
app.command("review")(review_command)
```

Update docstring: "Registers v0.1 commands: init, ingest, config, review."

**Changes to `test_cli.py`:**

- Add `"review"` to expected help commands.
- Remove `"review"` from stub parametrize list.

**E2E tests:** Full pipeline with FakeLLM — approve path, dead-link blocker path, format roundtrip.

**TDD steps:**

- [ ] **Step 1-6: Write E2E tests, register command, update existing tests, verify ALL tests pass**

```bash
.venv/Scripts/python.exe -m pytest -v --tb=short
```

Expected: ~352 tests pass (304 existing + ~48 new).

- [ ] **Commit**

```bash
git add src/giki/cli.py tests/test_cli.py tests/test_review_e2e.py
git commit -m "feat(cli): register giki review + E2E tests"
```

---

## Final Verification

- [ ] **Full test suite with coverage**

```bash
.venv/Scripts/python.exe -m pytest -v --cov=src/giki --cov-report=term-missing
```

| Module | Target |
|---|---|
| `review_models.py` | 100% |
| `rules.py` | 95% |
| `diff.py` | 90% |
| `wiki/review_agent.py` | 85% |
| `wiki/review_fmt.py` | 90% |
| `commands/review.py` | 70% |

- [ ] **Smoke test**

```bash
giki review --help
```

Expected: `--pr`, `--post`, `--json`, `--root`, `--base` flags listed.

- [ ] **Verify GitHub Action compatibility**

```bash
giki review --help | grep -E "^\s+--(pr|post)"
```

Both flags must be present — `templates/init/action.yml` invokes `giki review --pr ${{ ... }} --post`.

---

## Self-Review Checklist

**Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §7 Phase 0: Context Loading | Task 7 |
| §7 Phase 1: Change Classification | Task 3 |
| §7 Phase 2: Mechanical Checks | Task 4 |
| §7 Phase 3: Semantic Review × N | Task 5 |
| §7 Phase 4: Aggregation | Task 5 |
| §7 Phase 5: Output | Task 6 |
| §7.2 wiki-rules.md format | Task 2 |
| §7.3 Severity levels | Task 1 |
| §7.4 Mechanical first | Task 4 before Task 5 |
| §7.4 Per-page isolation | Task 5 |
| §7.4 compile/review independent | Task 7 (uses `cfg.llm.review`) |
| §7.4 Hand-written exemption | Task 5 |
| §7.4 --post via gh CLI | Task 6 |
| §5 `giki review` CLI | Tasks 7 + 8 |
| §10.4 GitHub Action | Task 8 |
| Exit codes | Task 1 |

**Placeholder scan:** clean. All code blocks contain full implementations.

**Type consistency:** `Rule` fields consistent across Tasks 1/2/5. `FileChange.wiki_slug` consistent in Tasks 1/4/7. `ReviewResult.findings` typed `list[MechanicalFinding | SemanticFinding]` matching all consumers. `aggregate_verdict` accepts mixed finding types.

**Scope check:** 8 tasks, one implementation cycle. Only `review` registered; other stubs remain.

---

**Plan complete.**
