---
title: Compilation Pipeline
aliases:
- giki ingest pipeline
- analyze synthesize crosslink
tags: []
created: '2026-07-02T11:44:01+08:00'
updated: '2026-07-02T11:44:01+08:00'
sources:
- path: kbase\sources\README.md
---

# Compilation Pipeline

The **Compilation Pipeline** is the core process within [[giki]] where raw source documents (such as markdown, text, and PDF files) are transformed into a navigable knowledge graph. Following a "compile, don't retrieve" philosophy, giki compiles sources *once* at ingest time rather than searching through raw documents at query time. This results in structured, interlinked wiki pages that can be browsed directly in tools like Obsidian.

## The Three Stages of Compilation

The pipeline consists of three distinct LLM-driven stages:

1. **Analyze**: The LLM extracts candidate concepts from the source document chunks.
2. **Synthesize**: The LLM generates or rewrites the wiki pages based on the extracted concepts.
3. **Crosslink**: The LLM interlinks the newly created or updated pages by adding `[[wikilinks]]` and `## Related` blocks.

## Architecture

The flow of the compilation pipeline—from ingesting sources to storage and subsequent review—is illustrated in the architecture diagram below:

```mermaid
graph TD
    subgraph Input
        S[Sources: md/txt/pdf]
    end

    subgraph "giki ingest"
        A[Analyze<br/>LLM: extract concepts]
        B[Synthesize<br/>LLM: generate pages]
        C[Crosslink<br/>LLM: add wikilinks]
    end

    subgraph Storage
        W[wiki/*.md<br/>flat, slug-named]
        I[index.md + log.md]
        G[git commit]
    end

    subgraph "giki review"
        M[Mechanical checks<br/>dead links, schema, index sync]
        R[Semantic review<br/>LLM per page + wiki-rules.md]
        V[Verdict: approve / comment / request-changes]
    end

    S --> A --> B --> C --> W --> G
    W --> I
    W --> M --> R --> V
```

Once the Analyze, Synthesize, and Crosslink stages are complete, the resulting flat, slug-named markdown files are saved to the `wiki/` directory. Smart indexing files (`index.md` and `log.md`) are automatically maintained, and the entire ingestion is saved as a clean, git-native commit.
