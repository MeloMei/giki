---
title: giki Configuration
aliases:
- giki config
- config.yaml
- llm configuration
tags: []
created: '2026-07-02T11:46:21+08:00'
updated: '2026-07-02T11:46:21+08:00'
sources:
- path: kbase\sources\README.md
---

# giki Configuration

The `.giki/config.yaml` file is the central configuration for a giki knowledge base. It is automatically created when you run `giki init` and defines how giki interacts with LLMs, how source documents are ingested, and how PR review behaves. 

You can manage this file directly in your text editor, or use the built-in [[cli-commands|CLI commands]]: `giki config show`, `giki config set <key> <value>`, and `giki config tips`.

## Structure of `.giki/config.yaml`

The configuration file is divided into three main sections:

- **`llm`**: Configures the LLM providers and models used for both compilation and review.
- **`ingest`**: Controls how source documents are chunked and processed before being sent to the LLM.
- **`review`**: Tunes the mechanical and [[review-pipeline|semantic PR review]] thresholds and GitHub comment behavior.

## LLM Settings

The `llm` block defines the models used for the two-phase [[compilation-pipeline|compilation pipeline]] (`compile`) and the semantic PR review (`review`). You can configure them to use the same or different providers and models.

- **`provider`**: The API provider type (`claude` or `openai`).
- **`model`**: The specific model identifier (e.g., `claude-sonnet-4-5-20250929`, `llama3`).
- **`base_url`**: The API endpoint URL.
- **`api_key_env`**: The name of the environment variable that holds your API key (e.g., `ANTHROPIC_API_KEY`).

### Anthropic Example

```yaml
llm:
  compile:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
  review:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
```

### OpenAI-compatible (Ollama) Example

giki can be pointed at local models via Ollama or any other OpenAI-compatible endpoint by setting the provider to `openai` and updating the `base_url`.

```yaml
llm:
  compile:
    provider: openai
    model: llama3
    base_url: http://localhost:11434/v1
    api_key_env: OLLAMA_API_KEY
  review:
    provider: openai
    model: llama3
    base_url: http://localhost:11434/v1
    api_key_env: OLLAMA_API_KEY
```

## Ingest Settings

The `ingest` block configures how raw documents are split before being processed by the LLM during the Analyze phase. Proper chunking ensures the LLM can process documents effectively without exceeding context limits.

- **`chunk_size`**: The maximum size of each document chunk (typically in characters or tokens).
- **`chunk_overlap`**: The number of characters or tokens that overlap between consecutive chunks. This ensures context continuity so concepts spanning across chunk boundaries are not lost.

Example configuration:
```yaml
ingest:
  chunk_size: 2000
  chunk_overlap: 200
```

## Review Settings

The `review` block tunes the behavior of the AI PR Review Bot, specifically adjusting how [[review-pipeline|mechanical checks]] and the LLM semantic reviewer evaluate changes and post comments to GitHub.

- **`unrelated_edit_threshold`**: The maximum allowed proportion or amount of edits that are considered unrelated to the main page topic before the review flags it. This helps catch scope creep or accidental commits.
- **`severity_blocking`**: Defines which severity levels of violations will trigger a `request-changes` verdict instead of just a `comment` (e.g., blocking on `error` but passing on `warning`).
- **`pr_comment_collapse`**: Boolean or threshold setting to collapse or group verbose review comments on GitHub, keeping the PR feed clean and readable while still providing detailed feedback.

Example configuration:
```yaml
review:
  unrelated_edit_threshold: 0.15
  severity_blocking: error
  pr_comment_collapse: true
```

---

## Related
- [[giki]]
- [[cli-commands]]
- [[compilation-pipeline]]
- [[review-pipeline]]
- [[github-action-integration]]
