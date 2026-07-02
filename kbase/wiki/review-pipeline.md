---
title: Review Pipeline
aliases:
- giki review
- pr review
- semantic review
- mechanical checks
tags: []
created: '2026-07-02T11:44:59+08:00'
updated: '2026-07-02T11:44:59+08:00'
sources:
- path: kbase\sources\README.md
---

# Review Pipeline

The **Review Pipeline** is [[giki|giki]]'s core quality control mechanism, treating knowledge base updates with the same rigor as software engineering code reviews. Running as a [[github-action-integration|GitHub Action]] on [[github-action-integration|pull requests]], it ensures that every AI-generated or human-edited wiki page meets structural and semantic standards before merging.

The pipeline is divided into a 5-phase process, blending deterministic checks with LLM-powered semantic evaluation.

## The 5-Phase Review Process

1. **Context**: The pipeline gathers the pull request diff, identifies the base branch, and extracts the list of modified, added, and deleted files.
2. **Classify**: Changed files are categorized. The pipeline distinguishes between [[compilation-pipeline|AI-generated wiki pages]], hand-written pages, source documents, and index files to apply the appropriate validation rules.
3. **Mechanical**: Deterministic, zero-false-positive checks are executed against the changed wiki pages to catch structural and formatting bugs.
4. **Semantic**: An LLM reviewer evaluates the content quality of each AI-generated page, checking it against the project's custom rules.
5. **Aggregate & Output**: Findings from both the mechanical and semantic phases are combined. The pipeline calculates a final verdict and outputs the results (e.g., as a PR comment or JSON payload).

## Mechanical Checks

Mechanical checks are deterministic validations that run first. They are designed to catch objective errors without LLM hallucination. The mechanical phase includes:

- **Dead links**: Verifies that all `[[wikilinks]]` point to an existing wiki page within the repository.
- **Frontmatter schema**: Validates that YAML frontmatter contains required fields (like `title`, `slug`, and `aliases`) and that they conform to expected data types.
- **Slug check**: Ensures that the markdown filename matches the designated slug in the frontmatter (e.g., `review-pipeline.md` must have `slug: review-pipeline`).
- **Index sync**: Confirms that `index.md` (categorized directory) and `log.md` (chronological timeline) have been correctly updated to reflect the added, modified, or removed pages.
- **Unrelated edit detection**: Flags changes that fall outside the expected scope of a wiki ingest (e.g., accidental modifications to [[configuration|configuration files]] or unrelated directories).

## Semantic Review

After mechanical checks pass, the pipeline initiates a semantic review. 

- **LLM per page**: An LLM is invoked to review each AI-generated or modified wiki page individually, evaluating for clarity, accuracy, and structural quality.
- **Cites `wiki-rules.md`**: The LLM is prompted with the project's specific writing and formatting rules. When it identifies an issue, it cites the exact rule using its anchor (e.g., `R-1 consistency`).
- **Skips hand-written pages**: To respect human authorship and avoid noisy reviews, the semantic review phase skips pages classified as hand-written, focusing only on [[compilation-pipeline|compiled/AI-generated content]].

## Verdicts

Based on the aggregated results of the mechanical and semantic phases, the pipeline outputs one of three verdicts:

- `approve`: All mechanical checks passed, and no blocking semantic issues were found.
- `comment`: The PR is safe to merge, but the LLM reviewer left suggestions or non-blocking feedback (e.g., style improvements).
- `request-changes`: A mechanical check failed, or the LLM reviewer found severe semantic violations that must be fixed before merging.

## Writing Rules in `wiki-rules.md`

You can customize the semantic review by defining rules in your repository's `wiki-rules.md` file. Rules are written as standard markdown headers, allowing the LLM to easily reference them by anchor.

To write a rule:

1. Create a level-two header using the `## R-N` format, where `N` is a unique number or identifier (e.g., `## R-1 consistency`).
2. Describe the rule clearly beneath the header.
3. Include a **severity level** to instruct the pipeline on how to handle violations. 

### Example

```markdown
## R-1 consistency
All pages must use consistent terminology. Do not mix "AI" and "Artificial Intelligence" in the same document.
Severity: error

## R-2 related-blocks
Every generated page must include a `## Related` block with at least two `[[wikilinks]]`.
Severity: warning
```

Rules with a severity of `error` will trigger a `request-changes` verdict if violated, while `warning` severities will result in a `comment` verdict.

---

## Related
- [[github-action-integration]]
- [[compilation-pipeline]]
- [[configuration]]
- [[giki]]
- [[limitations-and-roadmap]]
