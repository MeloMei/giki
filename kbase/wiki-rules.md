# Wiki Rules

_Rules for reviewing the giki knowledge base. Each rule is anchored by `## R-N`._

## R-1

**一致性 (consistency)** — severity: `blocker`

Facts asserted in different pages must not contradict each other. If a new
edit introduces a claim that conflicts with an existing page or with the same
page's prior content, flag it.

## R-2

**引用完整性 (citation integrity)** — severity: `blocker`

Every non-trivial factual claim should trace back to a source listed in the
page's `sources` frontmatter. Broken or missing citations are blockers.

## R-3

**命名规范 (naming convention)** — severity: `warn`

Page slugs must match `^[a-z0-9-]+$` and stay under 80 characters. Prefer
nouns over verb phrases; avoid dates in slugs.

## R-4

**双链优先 (bidirectional links)** — severity: `warn`

When a page mentions another wiki topic, prefer an explicit `[[wiki-link]]`
over a bare paragraph reference. Related sections should reciprocate where
the topics are genuinely related.

## R-5

**技术准确性 (technical accuracy)** — severity: `blocker`

Code examples, CLI flags, config keys, and API endpoints must match the
actual implementation. Stale or fabricated technical details are blockers.
