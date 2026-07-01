{{ mode_block }}

Slug: {{ slug }}
Title: {{ title }}
Source: {{ source_path }}
Aliases: {{ aliases_block }}

Hints:
{{ hints_block }}

Source excerpt:
---
{{ source_excerpt }}
---

Output ONLY the Markdown body (no YAML frontmatter — that will be added by giki).
Start with a single `# {{ title }}` heading.
