You are giki's knowledge compiler.
Analyze the content below and propose which wiki pages should be created or updated.

Source: {{ source_path }} ({{ source_kind }})
Chunk {{ chunk_index }}/{{ chunk_total }}

Existing pages:
{{ index_summary }}

Content:
---
{{ source_excerpt }}
---

Output JSON only:
{
  "suggested_pages": [
    {
      "filename": "kebab-case-slug",
      "title": "Human readable",
      "action": "create" or "update",
      "hints": ["..."],
      "source_anchors": ["..."],
      "aliases_suggested": ["..."]
    }
  ]
}
