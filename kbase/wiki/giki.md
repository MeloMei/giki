---
title: giki Overview
aliases:
- giki home
- what is giki
- giki introduction
tags: []
created: '2026-07-02T11:43:27+08:00'
updated: '2026-07-02T11:43:27+08:00'
sources:
- path: kbase\sources\README.md
---

# giki Overview

**giki** is a software-engineering approach to LLM Wikis. It treats knowledge like code—raw documents (markdown, text, PDF) are *compiled* into structured wiki pages by an LLM, then managed through Git with AI-powered pull request reviews. Think of it as **CI/CD for knowledge**.

## Core Philosophy

Most LLM knowledge tools either retrieve information at query time (like RAG) or generate content without quality control. giki takes a third path based on three core principles:

- **Compile, don't retrieve:** Instead of searching through raw documents every time you ask a question (the RAG approach), giki compiles sources into structured, interlinked wiki pages *once* at ingest time. The result is a navigable knowledge graph you can browse directly.
- **Review like code:** Every change goes through a two-phase [[review-pipeline|review pipeline]]: mechanical checks (dead links, schema validation) catch bugs deterministically, while an LLM reviewer evaluates semantic quality against your team's wiki rules. All of this runs as a [[github-action-integration|GitHub Action]] on pull requests.
- **Git-native:** Every AI-generated page is a normal Git commit. You can `git diff` to see exactly what the LLM changed, `git log` to trace knowledge evolution, and `git revert` to undo bad edits. No proprietary database, no vendor lock-in.

## Features

- **Two-phase [[compilation-pipeline|compilation pipeline]]:** Ingests sources through an Analyze phase (extracting candidate concepts from source chunks), a Synthesize phase (generating/rewriting wiki pages), and a Crosslink phase (adding `[[wikilinks]]` and `## Related` blocks).
- **AI PR Review Bot:** Mechanical checks run first with zero false positives (catching dead links, frontmatter schema issues, index sync gaps, and unrelated edits). Then, a per-page LLM semantic review cites your `wiki-rules.md` rules by anchor. Verdicts are issued as `approve`, `comment`, or `request-changes`.
- **Git-native version control:** Each ingest produces a clean commit (e.g., `ingest: observer.md — 3 of 3 pages`). Supports branch isolation with `--branch wiki/<topic>` and full diff, revert, and rebase support.
- **Obsidian-compatible output:** Generates standard YAML frontmatter and `[[wikilink]]` syntax. You can point Obsidian at your `wiki/` directory and browse immediately.
- **Smart indexing:** `index.md` (categorized directory) and `log.md` (chronological timeline) are auto-maintained. No manual bookkeeping required.

## Standard Repository Layout

When you initialize a giki knowledge base (using `[[cli-commands|giki init]]`), it creates a standard directory structure to separate raw sources from compiled knowledge:

```text
my-kb/
├── .giki/
│   └── [[configuration|config.yaml]]       # LLM provider, model, and endpoint configuration
├── sources/              # Raw documents (markdown, text, PDF) to be compiled
├── wiki/                 # Compiled, flat, slug-named wiki pages
├── index.md              # Auto-maintained categorized directory
├── log.md                # Auto-maintained chronological timeline
└── wiki-rules.md         # Team-specific rules used by the AI PR Review Bot
```

---

## Related
- [[compilation-pipeline]]
- [[review-pipeline]]
- [[configuration]]
- [[github-action-integration]]
- [[cli-commands]]
