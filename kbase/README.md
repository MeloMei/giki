# kbase — giki's own knowledge base

This directory is a **dog-fooding** knowledge base: giki compiles its own
project documentation into structured wiki pages, demonstrating the tool
working on itself.

## How it works

The `sources/` directory contains raw project documents (README, design spec,
contributing guide). Running `giki ingest` compiles these into the structured
pages you see in `wiki/`.

```bash
# From the repository root:
giki ingest --root kbase --branch wiki/<topic> kbase/sources/<file>
```

Each ingest produces a clean git commit on the specified branch. Open a PR
and `giki review` (via the GitHub Action in `.github/workflows/wiki-review.yml`)
will review the wiki changes against `wiki-rules.md`.

## Directory layout

```
kbase/
├── .giki/config.yaml   # LLM config (evomap API)
├── sources/             # Raw input documents
├── wiki/                # Compiled wiki pages (browse with Obsidian!)
├── index.md             # Auto-maintained category index
├── log.md               # Chronological ingest log
├── wiki-rules.md        # Review rules for the AI PR Review Bot
└── README.md            # This file
```

## Browsing

Point [Obsidian](https://obsidian.md) at this `kbase/` directory to browse
the wiki with graph view, backlinks, and full-text search.
