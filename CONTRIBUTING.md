# Contributing to giki

Thanks for your interest in contributing! giki is an early-stage project and we welcome ideas, bug reports, and code.

## Getting Started

### Prerequisites

- Python 3.11 or later
- Git

### Development Setup

```bash
# Clone and install in editable mode with dev dependencies
git clone https://github.com/MeloMei/giki.git
cd giki
pip install -e ".[dev]"

# Verify the installation
giki --help
pytest -q
```

The `[dev]` extra installs pytest, pytest-cov, vcrpy, respx, and reportlab — everything needed to run the full test suite.

## Running Tests

```bash
# Full suite (~390 tests, ~1 min)
pytest

# With coverage
pytest --cov=giki --cov-report=term-missing

# Run a specific module
pytest tests/test_config.py -v
```

CI runs the full suite on Python 3.11, 3.12, and 3.13 via GitHub Actions on every push and pull request to `main`. **All tests must pass before merging.**

## Project Structure

```
src/giki/
  cli.py              # Typer app entry point
  config.py           # YAML config loading + merge
  orchestrator.py     # Ingest pipeline (analyze → synthesize → crosslink)
  git_utils.py        # Git operations (commit, branch, diff)
  diff.py             # Diff extraction for review
  rules.py            # wiki-rules.md parser
  review_models.py    # Data types (Finding, Verdict, Rule, etc.)
  llm/                # Provider abstraction (OpenAI, Anthropic, factory)
  wiki/               # Wiki page parser, linker, store, review agent
  sources/            # Source readers (text, PDF)
  commands/           # CLI command modules (init, ingest, review, config)
  templates/          # Scaffolding templates for `giki init`
tests/                # pytest suite (flat structure, mirrors src modules)
```

## Code Style

giki does not currently enforce a linter or formatter, but please follow these conventions:

- Use type hints on function signatures.
- Keep imports grouped: stdlib → third-party → local.
- Write docstrings for public functions and classes.
- Match the existing code style — read a few modules before writing new ones.

## Making Changes

1. **Fork** the repository and create a feature branch from `main`.
2. **Write tests** for any new functionality or bug fixes. Untested code will not be accepted.
3. **Run the full test suite** (`pytest`) before committing.
4. **Commit** with a clear, descriptive message. We use conventional-style prefixes:
   - `feat:` new features
   - `fix:` bug fixes
   - `test:` test-only changes
   - `docs:` documentation
   - `refactor:` code restructuring
   - `chore:` maintenance tasks
5. **Push** to your fork and open a pull request against `main`.

## Pull Request Guidelines

- Keep PRs focused on a single concern. Avoid mixing unrelated changes.
- Describe **what** changed and **why** in the PR body.
- Reference any related issue (e.g., "Closes #42").
- Ensure CI passes (the GitHub Actions badge will update automatically).
- Be responsive to review feedback.

## Reporting Bugs

Open an issue with:

- What you expected vs. what actually happened.
- Steps to reproduce (include the exact `giki` command you ran).
- Your OS, Python version, and giki version (`pip show giki`).

## Feature Requests

Open an issue describing the use case and why it matters. We prefer to discuss design before implementation — please wait for feedback before writing code for large features.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
