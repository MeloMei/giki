# Wiki Rules

_Starter rules for `giki review`. Each rule is anchored by `## R-N` and may be
edited or removed freely. The review LLM will cite `rule_id` in its findings._

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

Page slugs must match `^[a-z0-9-]+$` and stay under the configured
`wiki.max_slug_length`. Prefer nouns over verb phrases; avoid dates in slugs.

## R-4

**双链优先 (bidirectional links)** — severity: `warn`

When a page mentions another wiki topic, prefer an explicit `[[wiki-link]]`
or `## Related` block over a bare paragraph reference. Related sections
should reciprocate where the topics are genuinely related.

## R-5

**段落长度 (paragraph length)** — severity: `nit`

Paragraphs longer than ~8 sentences or ~120 words are hard to scan. Split
into shorter paragraphs or a bulleted list unless the flow genuinely
requires prose.
