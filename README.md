# giki

Software-engineering approach to LLM Wikis. **Status: v0.1 (alpha).**

## Install
```
pip install -e ".[dev]"
```

## Quick start
```
giki init
export ANTHROPIC_API_KEY=sk-ant-...
cp ~/notes.md sources/
giki ingest sources/notes.md --branch wiki/first
```
