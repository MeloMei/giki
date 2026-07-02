---
title: giki CLI Commands
aliases:
- giki commands
- giki cli
- giki usage
tags: []
created: '2026-07-02T11:45:27+08:00'
updated: '2026-07-02T11:45:27+08:00'
sources:
- path: kbase\sources\README.md
---

# giki CLI Commands

The **giki CLI** is the primary interface for compiling source documents into structured wiki pages and reviewing changes through a two-phase pipeline. It treats knowledge like code: every command maps to a familiar git-style workflow, with deterministic mechanical checks and LLM-powered semantic review.

## Overview

| Command | Description |
|---|---|
| `giki init` | Initialize a knowledge base (creates `.giki/config.yaml`, `wiki-rules.md`, `wiki/`, `sources/`, `index.md`, `log.md`). |
| `giki ingest <path...>` | Compile source documents into wiki pages via the [[compilation-pipeline|Analyze → Synthesize → Crosslink pipeline]]. |
| `giki review` | Two-phase review: mechanical checks + LLM semantic review. |
| `giki config` | Manage `.giki/config.yaml` (`show`, `set <key> <value>`, or `tips`). |

## `giki init`

Initializes a new [[giki|giki knowledge base]] in the current directory. Run this once per repository, typically right after `git init`.

```bash
mkdir my-kb && cd my-kb
git init
giki init
```

### Flags

| Flag | Description |
|---|---|
| `--with-action` | Generate a [[github-action-integration|GitHub Actions workflow]] so reviews run automatically on pull requests. |

This scaffolds the standard layout: `.giki/config.yaml` for [[configuration|LLM configuration]], `wiki-rules.md` for your team's semantic rules, and the `wiki/` and `sources/` directories. The auto-maintained `index.md` (categorized directory) and `log.md` (chronological timeline) are also created.

## `giki ingest`

Compiles one or more source documents (markdown, text, PDF) into structured wiki pages. The pipeline runs in three phases: **Analyze** (extract candidate concepts from source chunks), **Synthesize** (generate or rewrite wiki pages via LLM), and **Crosslink** (add `[[wikilinks]]` and `## Related` blocks). Each ingest produces a clean git commit such as `ingest: observer.md — 3 of 3 pages`.

```bash
giki ingest sources/notes.md --branch wiki/my-first-ingest --yes
```

### Flags

| Flag | Description |
|---|---|
| `--branch NAME` | Ingest on this branch (creates if missing). Strongly recommended for isolation. |
| `--yes` | Non-interactive mode; accept all candidate pages without prompting. |
| `--dry-run` | Print candidate pages without generating them. Useful for previewing what the LLM would produce. |
| `--retry-failed` | Bypass the hash check and re-run the full pipeline. Recovers from transient LLM failures. |

Branch isolation with `--branch wiki/<topic>` keeps ingests cleanly separated, enabling standard `git diff`, `git log`, and `git revert` workflows on knowledge changes.

## `giki review`

Runs the [[review-pipeline|two-phase review pipeline]]. **Mechanical checks** run first with zero false positives: dead links, frontmatter schema validation, index sync, and unrelated edit detection. Then a **per-page LLM semantic review** evaluates quality against your `wiki-rules.md`, citing rules by anchor (e.g. `R-1 consistency`). Verdicts are `approve`, `comment`, or `request-changes`.

```bash
# Local review (HEAD vs main)
giki review

# Review a PR and post as comment
giki review --pr 42 --post

# JSON output for CI
giki review --json
```

### Flags

| Flag | Description |
|---|---|
| `--pr N` | Label the review with PR number N. Required when using `--post`. |
| `--post` | Post the review as a PR comment via the GitHub API. |
| `--json` | Emit machine-readable JSON output, suitable for CI pipelines. |
| `--base BRANCH` | Set the base branch to diff against (defaults to `main`). |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Review verdict is `approve` or `comment` — changes are acceptable. |
| `1` | Review verdict is `request-changes` — blocking issues were found. |

These exit codes make `giki review` directly usable as a CI gate: a non-zero exit fails the check and blocks merge.

## `giki config`

Manages `.giki/config.yaml`, which holds LLM provider settings for both the compile and review stages.

```bash
giki config show
giki config set llm.compile.model claude-sonnet-4-5-20250929
giki config tips
```

Subcommands:

- **`show`** — Print the current configuration.
- **`set <key> <value>`** — Update a single config key.
- **`tips`** — Print helpful configuration hints.

The config file separates `llm.compile` (used by `giki ingest`) from `llm.review` (used by `giki review`), so you can run different models or providers for each stage. Both Anthropic and any OpenAI-compatible endpoint (including local Ollama) are supported via the `provider`, `base_url`, and `api_key_env` fields.

## Common workflows

### First-time setup

```bash
mkdir my-kb && cd my-kb
git init
giki init --with-action
# edit .giki/config.yaml to point at your LLM
export ANTHROPIC_API_KEY=sk-ant-...
```

### Iterative ingest

```bash
cp ~/notes.md sources/
giki ingest sources/notes.md --branch wiki/notes --dry-run   # preview
giki ingest sources/notes.md --branch wiki/notes --yes       # commit
```

### CI review gate

```bash
giki review --pr $PR_NUMBER --post --json
# exit 0 → approve/comment, exit 1 → request-changes (fails the check)
```

---

## Related
- [[giki]]
- [[compilation-pipeline]]
- [[review-pipeline]]
- [[configuration]]
- [[github-action-integration]]
