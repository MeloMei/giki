"""Knowledge decay detection: find pages whose claims may have gone stale.

Two layers, mirroring the review pipeline's mechanical/semantic split:

1. Mechanical signal extraction — version references, time-sensitive
   phrases, and page age give a zero-cost anchor for "this page CAN decay".
2. LLM assessment — for each anchored page, the LLM reads the content and
   judges which specific claims are likely stale, with reasons.

The output is a report, not a gate: decay detection never blocks a merge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..llm.base import LLMAdapter, Message
from ..llm.prompts import PromptTemplate
from ..utils import extract_json

# --- Mechanical signals ----------------------------------------------------

_VERSION_RE = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")

# Dates in dotted form (2026.07.19) are not version references.
_DATE_DOTTED_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")

_TIME_PHRASES_EN = (
    "latest",
    "currently",
    "current",
    "newest",
    "recently",
    "recent",
    "today",
    "nowadays",
    "up-to-date",
    "deprecated",
    "stable",
    "lts",
    "beta",
    "nightly",
)

_TIME_PHRASES_ZH = (
    "目前",
    "最新",
    "当前",
    "现在",
    "近期",
    "最近",
    "稳定版",
    "已废弃",
)

_MAX_SIGNALS = 12


def extract_signals(body: str) -> list[str]:
    """Extract time-sensitive signals from page body text.

    Returns a de-duplicated, order-preserving list capped at
    ``_MAX_SIGNALS`` entries. An empty list means the page has no
    mechanical anchor for decay — it is skipped by default (unless the
    page is old enough to be suspicious on its own; see the command).
    """
    signals: list[str] = []
    seen: set[str] = set()

    def _add(s: str) -> None:
        if s not in seen and len(signals) < _MAX_SIGNALS:
            seen.add(s)
            signals.append(s)

    for m in _VERSION_RE.finditer(body):
        if not _DATE_DOTTED_RE.match(m.group(0)):
            _add(m.group(0))

    # English phrases use word boundaries: "results" must not match "lts",
    # "unstable" must not match "stable". When both a phrase and its
    # substring hit (currently/current), keep only the longer one.
    lowered = body.lower()
    for phrase in _TIME_PHRASES_EN:
        if re.search(rf"\b{re.escape(phrase)}\b", lowered):
            if any(phrase in s for s in signals):
                continue
            _add(phrase)
    for phrase in _TIME_PHRASES_ZH:
        if phrase in body:
            _add(phrase)

    return signals


def page_age_days(updated: str, *, now: datetime | None = None) -> int | None:
    """Days since the page's ``updated`` timestamp. None when unparseable."""
    try:
        dt = datetime.fromisoformat(str(updated))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return max(0, (now - dt).days)


# --- LLM assessment --------------------------------------------------------


@dataclass(frozen=True)
class StaleClaim:
    claim: str
    reason: str
    suggestion: str


@dataclass(frozen=True)
class DecayAssessment:
    slug: str
    risk: str  # "high" | "medium" | "low" | "unknown"
    stale_claims: list[StaleClaim] = field(default_factory=list)
    age_days: int | None = None
    signals: list[str] = field(default_factory=list)


_RISK_ORDER = {"high": 0, "medium": 1, "low": 2, "unknown": 3}


def risk_sort_key(a: DecayAssessment) -> tuple:
    """Sort high-risk first, then oldest pages first."""
    return (_RISK_ORDER.get(a.risk, 3), -(a.age_days or 0))


def assess_page_decay(
    *,
    llm: LLMAdapter,
    slug: str,
    title: str,
    body: str,
    age_days: int | None,
    signals: list[str],
) -> DecayAssessment:
    """Ask the LLM to judge which claims on one page may be stale.

    LLM or parse failures degrade to ``risk="unknown"`` — a report must
    never crash on one bad page.
    """
    content = body[:6000]
    if len(body) > 6000:
        truncated_note = (
            f"NOTE: only the first 6000 of {len(body)} characters are shown; "
            f"claims later in the page are not covered."
        )
    else:
        truncated_note = ""
    tmpl = PromptTemplate.from_package("decay.md")
    prompt = tmpl.render(
        page_slug=slug,
        page_title=title,
        age_days=str(age_days) if age_days is not None else "unknown",
        today=datetime.now().astimezone().date().isoformat(),
        signals=", ".join(signals) if signals else "(none)",
        truncated_note=truncated_note,
        page_content=content,
    )
    messages = [Message(role="user", content=prompt)]

    try:
        response = llm.chat(messages)
        data = extract_json(response.text)
    except Exception:
        return DecayAssessment(
            slug=slug, risk="unknown", age_days=age_days, signals=signals
        )

    if not isinstance(data, dict):
        return DecayAssessment(
            slug=slug, risk="unknown", age_days=age_days, signals=signals
        )

    risk = str(data.get("risk", "unknown")).lower()
    if risk not in ("high", "medium", "low"):
        risk = "unknown"

    claims: list[StaleClaim] = []
    for c in data.get("stale_claims", []):
        if not isinstance(c, dict):
            continue
        claims.append(
            StaleClaim(
                claim=str(c.get("claim", "")),
                reason=str(c.get("reason", "")),
                suggestion=str(c.get("suggestion", "")),
            )
        )

    return DecayAssessment(
        slug=slug,
        risk=risk,
        stale_claims=claims,
        age_days=age_days,
        signals=signals,
    )
