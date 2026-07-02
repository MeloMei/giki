# giki

<h4 align="center">

📚 Git-Native LLM Wiki — Compile knowledge like code, review like a PR

</h4>

<p align="center">
<a href="#-why-giki">Why</a> •
<a href="#-features">Features</a> •
<a href="#-quick-start">Quick Start</a> •
<a href="#-how-it-works">How It Works</a> •
<a href="#-comparison">Comparison</a> •
<a href="#-roadmap">Roadmap</a>
</p>

<p align="center">
<a href="https://github.com/MeloMei/giki/actions/workflows/ci.yml"><img src="https://github.com/MeloMei/giki/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://pypi.org/project/giki-gitwiki/"><img src="https://img.shields.io/pypi/v/giki-gitwiki" alt="PyPI"></a>
<img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python">
<img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

<p align="center">
<a href="docs/README-CN.md">中文 README</a> · <a href="docs/superpowers/specs/2026-06-30-giki-v0.1-design.md">Design Spec</a>
</p>

---

## 🤔 Why giki?

Andrej Karpathy's **LLM Wiki** pattern is changing knowledge management — instead of retrieving and stitch together answers at query time (traditional rag) (the "interpreter" approach), LLMs *compile* raw documents into structured, interlinked wiki pages at ingest time (the "compiler" approach).

But existing implementations are almost all **single-player local tools**, missing two critical pieces:

1. **Team collaboration** — no way for a team to safely co-author the same "living encyclopedia"
2. **Quality gates** — AI generates knowledge fast, but who checks if it's correct? Unchecked compilation can have failure rates of 53%–60% (WiCER, 2026)

**giki** brings software engineering practices to LLM Wikis:

- Every AI modification is an auditable, revertable `git commit`
- Teams compile on branches, review through Pull Requests, and merge into main
- An **LLM Review Bot** acts as the first line of quality defense, automatically checking for semantic contradictions and rule compliance on PRs

> Knowledge CI/CD — treat knowledge like code.

<!-- TODO: screenshot of terminal showing giki ingest output -->
<!-- <p align="center"><img src="docs/screenshots/ingest-demo.png" alt="giki ingest demo" width="700"></p> -->

---

## ✨ Features

**🧠 Three-Phase Compilation Pipeline**
Analyze (extract candidate concepts from source chunks) → Synthesize (generate/rewrite wiki pages) → Crosslink (add `[[wikilinks]]` and `## Related` blocks). Sliding-window chunking handles full books without truncation.

**🛡️ AI PR Review Bot**
Mechanical checks run first (zero false positives): dead links, frontmatter schema, index sync, unrelated edit detection. Then per-page LLM semantic review cites your `wiki-rules.md` rules by anchor (e.g. `R-1 consistency`). Verdicts: `approve` / `comment` / `request-changes`.

**🔄 Git-Native Version Control**
Each ingest produces a clean commit (`ingest: observer.md — 3 of 3 pages`). Branch isolation with `--branch wiki/<topic>`. Full diff/revert/rebase support.

**📇 Smart Indexing**
`index.md` (categorized directory) and `log.md` (chronological timeline) are auto-maintained. No manual bookkeeping.

**🔗 Obsidian Compatible**
Standard YAML frontmatter + `[[wikilink]]` syntax. Point Obsidian at your `wiki/` directory and browse the knowledge graph immediately.

**🔌 Multi-Model Pluggable**
Supports Claude, GPT-4/OpenAI, Ollama, and any OpenAI-compatible endpoint. Compile and review LLMs are independently configurable for cross-validation.

---

## ⚡ Quick Start

### Install

```bash
pip install giki-gitwiki
```

### Initialize

```bash
mkdir my-kb && cd my-kb && git init
giki init
```

<!-- TODO: screenshot of giki init output -->
<!-- <p align="center"><img src="docs/screenshots/init-demo.png" alt="giki init" width="600"></p> -->

This creates `.giki/config.yaml`, `wiki-rules.md`, `wiki/`, `sources/`, `index.md`, and `log.md`.

### Configure your LLM

Edit `.giki/config.yaml`:

```yaml
llm:
  compile:
    provider: claude          # or "openai" for OpenAI/Ollama
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
  review:
    provider: openai          # use a different model for cross-validation
    model: gpt-4o
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
```

Then set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Ingest a document

```bash
cp ~/notes/design-patterns.md sources/
giki ingest sources/design-patterns.md --branch wiki/design-patterns --yes
```

<!-- TODO: screenshot of giki ingest showing candidate pages and commit -->
<!-- <p align="center"><img src="docs/screenshots/ingest-demo.png" alt="giki ingest" width="700"></p> -->

giki will analyze the source, propose wiki pages, generate them via LLM, add crosslinks, update `index.md` and `log.md`, and commit everything to the `wiki/design-patterns` branch.

### Review changes

```bash
# Local review (HEAD vs main)
giki review

# Review a GitHub PR and post as comment
giki review --pr 42 --post

# JSON output for CI
giki review --json
```

<!-- TODO: screenshot of giki review showing findings -->
<!-- <p align="center"><img src="docs/screenshots/review-demo.png" alt="giki review" width="700"></p> -->

### Browse in Obsidian

```bash
open -a Obsidian wiki/
```

<!-- TODO: screenshot of Obsidian graph view showing wiki pages and links -->
<!-- <p align="center"><img src="docs/screenshots/obsidian-graph.png" alt="Obsidian graph" width="700"></p> -->

---

## 🧠 How It Works

```
sources/  ──►  [LLM Compile Engine]  ──►  wiki/ (structured knowledge)
 raw docs      Analyze → Synthesize        auto-updates index.md + log.md
                 → Crosslink

└──────────────────── Git Management ──────────────────────┘
   Every change is a clean commit; branch collaboration via PRs

┌────────────── AI Review Bot (PR-triggered) ──────────────┐
│  Read wiki-rules.md → Get diff → Mechanical checks       │
│  → LLM semantic review → Post review comment             │
│  (approve / comment / request-changes)                   │
└──────────────────────────────────────────────────────────┘
```

1. **Ingest** — LLM reads source documents, extracts key concepts and entities
2. **Synthesize** — Generates or updates wiki pages with proper frontmatter, cross-referencing existing knowledge
3. **Crosslink** — Adds `[[wikilinks]]` between related pages and generates `## Related` blocks
4. **Index** — Updates `index.md` (categorized directory) and `log.md` (timeline)
5. **Commit** — All changes are committed as a clean git commit
6. **Review** — PR triggers the Review Bot: mechanical checks + per-page LLM semantic review
7. **Collaborate** — Team discusses review findings, refines, and merges

---

## 👥 Comparison

| Feature | **giki** | Traditional RAG (NotebookLM etc.) | Single-player LLM Wiki | Git Wiki (Gollum etc.) |
| :--- | :---: | :---: | :---: | :---: |
| Knowledge Compilation | ✅ Compile-time | ❌ Retrieval-time | ✅ | ❌ |
| Version Control | ✅ Git full pipeline | ❌ | ✅ Single-user | ✅ |
| Team Collaboration | ✅ Branch + PR | ❌ | ❌ | ✅ |
| AI Review | ✅ Mechanical + Semantic | ❌ | ❌ | ❌ |
| Obsidian Compatible | ✅ | ❌ | ✅ | ✅ |
| Smart Indexing | ✅ Auto index + log | ❌ | Partial | ❌ |
| GitHub Actions | ✅ Auto review on PR | ❌ | ❌ | ❌ |

---

## 📖 Commands

| Command | Description |
|---|---|
| `giki init [--with-action]` | Initialize a knowledge base. `--with-action` generates a GitHub Actions workflow. |
| `giki ingest <path...> [--branch NAME] [--yes] [--dry-run] [--retry-failed]` | Compile source documents into wiki pages. |
| `giki review [--pr N] [--post] [--json] [--base BRANCH]` | Two-phase review: mechanical checks + LLM semantic review. |
| `giki config show \| set <key> <value> \| tips` | Manage `.giki/config.yaml`. |

Exit codes for `review`: `0` = approve or comment, `1` = request-changes.

---

## 🗺️ Roadmap

- [x] **v0.1 Core** — Two-phase compilation, PR Review Bot, Git-native workflow, Obsidian compatibility
- [x] **v0.1 Dog-fooding** — `kbase/` directory: giki compiles its own documentation as a live demo
- [ ] **v0.2 Typed Wikilinks** — `[[requires::X]]`, `[[contradicts::Y]]` with 8 relation types
- [ ] **v0.2 Collaboration** — `giki branch` / `giki pr` commands, AI merge for conflict resolution
- [ ] **v0.3 Web UI** — `giki serve` with D3 knowledge graph visualization + full-text search
- [ ] **v0.3 Q&A** — `giki chat` with BM25 retrieval + RAG
- [ ] **v0.3 Knowledge Fusion** — Cross-domain wiki federation (`.wiki-fusion.yaml`)

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and contribution guidelines.

```bash
git clone https://github.com/MeloMei/giki.git
cd giki
pip install -e ".[dev]"
pytest -q
```

---

## 📄 License

[MIT License](LICENSE)

<p align="center"><sub>For those who believe knowledge should compound over time.</sub></p>
