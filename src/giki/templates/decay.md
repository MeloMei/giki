You are auditing a wiki page for knowledge decay — claims that may have
become stale over time (outdated versions, deprecated APIs, superseded
best practices, dead links to external resources).

## Page: {{ page_slug }} (title: {{ page_title }})

Today's date: {{ today }}
Page age: {{ age_days }} days since last update
Time-sensitive signals detected: {{ signals }}
{{ truncated_note }}

## Content

{{ page_content }}

## Task

Identify claims in this page that are LIKELY to be outdated today. Focus on:
- Version numbers that may have been superseded
- APIs, commands, or libraries that may have changed or been deprecated
- Time-relative statements ("latest", "currently", "recently") that age badly
- Best practices that may have evolved

Do NOT flag:
- Timeless concepts, design patterns, or definitions
- Claims you cannot reasonably judge

Output ONLY valid JSON (no markdown fences):
{
  "risk": "high" | "medium" | "low",
  "stale_claims": [
    {
      "claim": "the specific claim that may be stale",
      "reason": "why it is likely outdated",
      "suggestion": "how to verify or update it"
    }
  ]
}

Risk levels: high = multiple likely-stale claims or a critical one;
medium = one or two plausible stale claims; low = nothing clearly stale.
If nothing looks stale, return {"risk": "low", "stale_claims": []}.
