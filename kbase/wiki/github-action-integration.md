---
title: GitHub Action Integration
aliases:
- ci/cd
- github actions
- giki workflow
tags: []
created: '2026-07-02T11:46:56+08:00'
updated: '2026-07-02T11:46:56+08:00'
sources:
- path: kbase\sources\README.md
---

# GitHub Action Integration

giki treats knowledge like code, bringing the full power of CI/CD to your wiki. By integrating giki with GitHub Actions, every pull request targeting your wiki automatically undergoes a rigorous [[review-pipeline|two-phase review pipeline]]: [[review-pipeline|mechanical checks]] (dead links, schema validation, index sync) followed by an LLM-powered [[review-pipeline|semantic review]] that evaluates content against your `[[configuration|wiki-rules.md]]`.

## Generating the Workflow

To automatically configure GitHub Actions for your knowledge base, initialize giki with the action flag:

```bash
[[cli-commands|giki init]] --with-action
```

This generates a ready-to-use workflow file at `.github/workflows/giki-review.yml` in your repository.

## Workflow Configuration

If you are adding the workflow manually or want to inspect the generated configuration, here is the standard YAML snippet for `.github/workflows/giki-review.yml`:

```yaml
name: Giki Review

on:
  pull_request:
    paths:
      - 'wiki/**'
      - 'index.md'
      - 'wiki-rules.md'
      - '.giki/**'

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0 

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install giki
        run: pip install giki

      - name: Run [[cli-commands|giki review]]
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          giki review --pr ${{ github.event.pull_request.number }} --post
```

## Environment Variables

For the GitHub Action to successfully run the LLM semantic review and post the results back to the pull request, you must configure the following repository secrets:

- **`ANTHROPIC_API_KEY`**: Required for authenticating with the LLM provider (e.g., Anthropic) to perform the semantic page-by-page review. 
- **`GH_TOKEN`**: Required for the `giki review --post` command to authenticate with the GitHub API and publish the review verdict (`approve`, `comment`, or `request-changes`) directly on the pull request. *(Note: You can use the automatically generated `GITHUB_TOKEN`, but if your workflow requires elevated permissions, provide a Personal Access Token (PAT) instead).*

## Trigger Paths

To optimize CI minutes and ensure the review bot only runs when relevant knowledge is updated, the workflow is configured to trigger exclusively on changes to the following paths:

- **`wiki/**`**: Triggers when any wiki page is created, modified, or deleted.
- **`index.md`**: Triggers when the categorized directory is updated.
- **`wiki-rules.md`**: Triggers when your team's wiki rules change (ensuring reviews use the latest standards).
- **`.giki/**`**: Triggers when [[configuration|giki configuration]] or internal state is modified.

---

## Related
- [[review-pipeline]]
- [[cli-commands]]
- [[configuration]]
- [[giki]]
- [[compilation-pipeline]]
