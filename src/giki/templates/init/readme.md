# Knowledge Base

This repository is a **giki knowledge base** — a wiki that grows by ingesting
source documents through an LLM, with mechanical + LLM review guarding every
change.

## Layout

- [`wiki/`](wiki/) — compiled wiki pages, one topic per file
- [`sources/`](sources/) — raw source documents (Markdown, PDF, text) that
  feed the compiler
- [`index.md`](index.md) — auto-maintained table of pages
- [`log.md`](log.md) — chronological ingest log
- [`wiki-rules.md`](wiki-rules.md) — user-defined review rules (`## R-N`)
- `.giki/config.yaml` — LLM provider, chunking, and review thresholds
- `.giki-state/` — regeneratable state (gitignored)

## How to compile new sources

Drop a document into `sources/`, then run:

```
giki ingest sources/foo.md --branch wiki/foo
```

`giki` will analyze the document, synthesize wiki pages on a working branch,
update `index.md` and `log.md`, and commit — leaving you to review, tweak,
and merge.

Run `giki review` on a PR to get mechanical + LLM feedback against the rules
in `wiki-rules.md`.
