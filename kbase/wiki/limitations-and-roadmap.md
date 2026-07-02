---
title: Known Limitations and Roadmap
aliases:
- giki roadmap
- giki limitations
tags: []
created: '2026-07-02T11:47:25+08:00'
updated: '2026-07-02T11:47:25+08:00'
sources:
- path: kbase\sources\README.md
---

# Known Limitations and Roadmap

## Current Limitations (v0.1)

As giki is in its early stages, the current version (v0.1) has several known limitations:
- **No PDF OCR:** Only text-based PDFs are supported; scanned documents cannot be parsed.
- **No remote sources:** You must manually copy remote documents into the `sources/` directory for ingestion.
- **No wikilink anchors:** Links can only point to whole pages, not specific headings or blocks within a page.
- **Flat wiki directory:** All wiki pages are stored directly in `wiki/`; nested subdirectories for organization are not yet supported.
- **Manual retry:** Transient LLM failures during the [[compilation-pipeline|compilation pipeline]] require manual intervention using the `--retry-failed` flag.
- **No token estimation:** The CLI does not currently provide estimates for token usage or associated LLM costs before running the pipeline.

## Roadmap

### v0.2
- **Typed wikilinks:** Introduce semantic typing for wikilinks to define relationships between concepts (e.g., `[[implements::slug]]`).
- **`giki branch` / `giki pr` commands:** Native git branch and pull request management directly within the [[cli-commands|giki CLI]].
- **AI merge:** LLM-assisted automatic merging and conflict resolution for knowledge branches.

### v0.3
- **Local web UI:** A built-in local web interface for browsing, searching, and editing the wiki without requiring Obsidian.
- **Q&A (RAG):** Retrieval-Augmented Generation capabilities to query your compiled knowledge graph directly via the CLI or UI.
- **Cross-domain knowledge fusion:** Advanced synthesis that automatically detects and merges overlapping concepts from disparate source domains.
- **`giki lint --fix`:** Automated linting that not only detects [[review-pipeline|mechanical issues]] but proposes and applies fixes using the LLM.

---

## Related
- [[giki]]
- [[compilation-pipeline]]
- [[cli-commands]]
- [[review-pipeline]]
- [[configuration]]
