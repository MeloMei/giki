# giki Project Setup Guide (for AI Agents)

> This document is designed for AI coding assistants. If a user asks you to set up the giki project, follow these steps exactly.

## Quick Summary

giki is a Git-native LLM Wiki CLI tool written in Python. It compiles documents into structured wiki pages using LLMs, with AI-powered review and team collaboration features.

## Prerequisites

- Python 3.11 or higher
- Git
- macOS, Linux, or Windows

## Setup Steps

### 1. Clone the repository

```bash
git clone https://github.com/MeloMei/giki.git
cd giki
```

### 2. Install dependencies

```bash
pip install -e .
```

This installs giki and all runtime dependencies (typer, GitPython, rich, mcp, rank-bm25, etc.).

### 3. Verify installation

```bash
giki --version
```

If `giki` is not found in PATH, locate the scripts directory:

```bash
# macOS/Linux
python3 -c "import sysconfig; print(sysconfig.get_path('scripts'))"

# Windows
python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
```

Add the output path to your shell's PATH (e.g., add to `~/.zshrc` or `~/.bashrc`):

```bash
# macOS example (adjust Python version)
echo 'export PATH="$HOME/Library/Python/3.13/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 4. Run tests to verify everything works

```bash
pip install -e ".[dev]"
pytest -q
```

Expected: 530 tests pass.

### 5. Configure an LLM provider

Before using `giki ingest` or `giki review`, configure an LLM provider. Edit `.giki/config.yaml` after running `giki init`, or use:

```bash
# Example with OpenAI
giki config set llm.compile.provider openai
giki config set llm.compile.model gpt-4o
giki config set llm.compile.base_url https://api.openai.com/v1
giki config set llm.compile.api_key_env OPENAI_API_KEY

export OPENAI_API_KEY="sk-..."
```

Other supported providers: Claude (Anthropic), Ollama, any OpenAI-compatible endpoint.

## Typical Workflow

```bash
# 1. Create a new knowledge base
mkdir my-kb && cd my-kb && git init
giki init

# 2. Add source documents
cp ~/notes/design-patterns.md sources/

# 3. Compile into wiki pages
giki ingest sources/design-patterns.md --branch wiki/design-patterns --yes

# 4. Review changes
giki review --base main

# 5. Browse in Obsidian
open -a Obsidian wiki/   # macOS

# 6. Start local web UI
giki serve --port 8080  # then open http://localhost:8080

# 7. Ask questions
giki chat "What is the observer pattern?"
```

## All Commands

| Command | Description |
|---|---|
| `giki init [--with-action]` | Initialize knowledge base |
| `giki ingest <paths> [--branch NAME] [--yes]` | Compile sources into wiki pages |
| `giki review [--pr N] [--post] [--json]` | Mechanical + semantic review |
| `giki branch list\|create\|switch` | Manage branches |
| `giki pr create\|list\|review\|merge` | Manage PRs (requires gh CLI) |
| `giki lint [--fix]` | Wiki health check |
| `giki serve [--port N]` | Local web UI with D3 graph |
| `giki chat ["question"]` | Q&A with BM25 + RAG |
| `giki config show\|set <k> <v>` | Manage config |
| `giki mcp-serve` | MCP server for platform integration |

## Project Architecture

```
src/giki/
  cli.py              # Typer CLI entry point
  config.py           # Config dataclass, YAML loader
  orchestrator.py     # 7-phase ingest pipeline
  git_utils.py        # GitPython facade
  search.py           # BM25 search index
  mcp_server.py       # MCP server (FastMCP)
  llm/                # LLM adapters (Claude, OpenAI)
  wiki/               # Parser, linker, store, review agent
  sources/            # Source file loaders (text, PDF)
  commands/           # CLI command modules
  templates/          # Init scaffolding templates
tests/                # pytest suite
```

## For Development

```bash
git clone https://github.com/MeloMei/giki.git
cd giki
pip install -e ".[dev]"
pytest -q          # 530 tests
```
