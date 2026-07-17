"""LLM usage tracking and cost estimation.

Adapters already return per-call token usage in ``LLMResponse.usage``, but
nothing consumed it. :class:`UsageTracker` wraps an adapter (lazily, so the
real client is only built when a phase actually needs it) and records every
call: tokens in/out and an estimated USD cost. At the end of a run the
records feed a summary panel and an append-only JSONL ledger at
``.giki-state/usage.jsonl``.

Tracking is best-effort by design: a malformed usage dict or a failed ledger
write must never break the command the user actually ran.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..utils import iso_now
from .base import LLMAdapter, LLMResponse, Message

# List prices in USD per 1M tokens: model prefix -> (input, output).
# Matching is first-hit in declaration order, so longer prefixes MUST be
# declared before shorter ones (e.g. "gpt-4o-mini" before "gpt-4o").
# Estimates only — providers change prices over time. Models that match no
# prefix report cost=None and are surfaced as "unknown pricing".
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (1.0, 5.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.0, 8.0),
    "o4-mini": (1.10, 4.40),
    "o3-mini": (1.10, 4.40),
    "o3": (2.0, 8.0),
}

LEDGER_NAME = "usage.jsonl"


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Return the estimated USD cost, or None if the model's pricing is unknown."""
    m = model.lower()
    for prefix, (price_in, price_out) in _PRICING.items():
        if m.startswith(prefix):
            return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return None


def _as_int(value) -> int:
    """Coerce a usage value to int; anything unexpected becomes 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def extract_tokens(usage: dict | None) -> tuple[int, int]:
    """Normalize a provider usage dict to ``(input_tokens, output_tokens)``.

    Claude returns ``input_tokens``/``output_tokens``; OpenAI-compatible
    endpoints return ``prompt_tokens``/``completion_tokens``. Third-party
    gateways sometimes emit malformed values — those degrade to 0 rather
    than raising, because tracking must never break the main flow.
    """
    if not isinstance(usage, dict):
        return 0, 0
    inp = usage.get("input_tokens")
    if inp is None:
        inp = usage.get("prompt_tokens")
    out = usage.get("output_tokens")
    if out is None:
        out = usage.get("completion_tokens")
    return _as_int(inp), _as_int(out)


@dataclass(frozen=True)
class UsageRecord:
    """One LLM call's usage, as appended to the JSONL ledger."""

    ts: str
    command: str
    run_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None

    def to_json(self) -> str:
        return json.dumps(
            {
                "ts": self.ts,
                "command": self.command,
                "run_id": self.run_id,
                "provider": self.provider,
                "model": self.model,
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "cost_usd": self.cost_usd,
            },
            ensure_ascii=False,
        )


class UsageTracker:
    """Accumulates usage records for a single CLI run."""

    def __init__(self, *, command: str):
        self.command = command
        self.run_id = uuid.uuid4().hex[:12]
        self.records: list[UsageRecord] = []

    def wrap(self, factory: Callable[[], LLMAdapter]) -> LLMAdapter:
        """Return an adapter that builds the real client on first use.

        Laziness preserves existing behavior: commands that end up making no
        LLM calls (e.g. all sources already ingested) never require an API key.
        """
        return _TrackingAdapter(factory, self)

    def record(self, *, provider: str, model: str, usage: dict | None) -> UsageRecord:
        inp, out = extract_tokens(usage)
        rec = UsageRecord(
            ts=iso_now(),
            command=self.command,
            run_id=self.run_id,
            provider=provider,
            model=model,
            input_tokens=inp,
            output_tokens=out,
            cost_usd=estimate_cost(model, inp, out),
        )
        self.records.append(rec)
        return rec

    @property
    def total_input(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def total_output(self) -> int:
        return sum(r.output_tokens for r in self.records)

    def cost_summary(self) -> tuple[float, bool]:
        """Return ``(total_known_cost, partial)``.

        ``partial`` is True when at least one call used a model with unknown
        pricing, meaning the true cost is higher than the reported total.
        """
        total = 0.0
        partial = False
        for r in self.records:
            if r.cost_usd is None:
                partial = True
            else:
                total += r.cost_usd
        return total, partial

    def summary_lines(self) -> list[str]:
        """Human-readable lines for the end-of-run usage panel."""
        n = len(self.records)
        models = ", ".join(sorted({f"{r.provider}:{r.model}" for r in self.records}))
        lines = [
            f"{n} LLM call(s) · {self.total_input:,} tokens in · "
            f"{self.total_output:,} tokens out",
            f"model: {models}",
        ]
        cost, partial = self.cost_summary()
        known = any(r.cost_usd is not None for r in self.records)
        if not known:
            lines.append("estimated cost: n/a (unknown model pricing)")
        elif partial:
            lines.append(f"estimated cost: >= ${cost:.4f} (some models have unknown pricing)")
        else:
            lines.append(f"estimated cost: ${cost:.4f}")
        return lines

    def append_ledger(self, state_dir: Path) -> Path | None:
        """Append all records to ``<state_dir>/usage.jsonl``. Returns the path.

        Raises OSError if the ledger cannot be written — callers are
        expected to degrade to a warning (the ledger is an audit aid, not
        something a successful run should crash on).
        """
        if not self.records:
            return None
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / LEDGER_NAME
        with path.open("a", encoding="utf-8") as f:
            for r in self.records:
                f.write(r.to_json() + "\n")
        return path


def _as_float(value) -> float | None:
    """Coerce a cost value to float; anything unexpected becomes None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _normalize_record(rec: dict) -> dict:
    """Coerce a raw ledger dict to canonical field types.

    ``read_ledger`` only guarantees a dict per line; hand-edited or
    externally produced ledgers may carry strings/numbers in the wrong
    shape. Normalizing here keeps every consumer simple and safe.
    """
    rec = dict(rec)
    rec["input_tokens"] = _as_int(rec.get("input_tokens"))
    rec["output_tokens"] = _as_int(rec.get("output_tokens"))
    rec["cost_usd"] = _as_float(rec.get("cost_usd"))
    return rec


def read_ledger(state_dir: Path) -> tuple[list[dict], int]:
    """Read the usage ledger at ``<state_dir>/usage.jsonl``.

    Returns ``(records, skipped)`` where ``skipped`` counts malformed
    lines — a partially written or hand-edited ledger must never break
    reporting. Records are normalized: ``input_tokens``/``output_tokens``
    are always ints and ``cost_usd`` is a float or None. Returns
    ``([], 0)`` when no ledger exists yet.
    """
    path = state_dir / LEDGER_NAME
    if not path.exists():
        return [], 0
    records: list[dict] = []
    skipped = 0
    # utf-8-sig tolerates a BOM (Windows editors often add one).
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(rec, dict):
            skipped += 1
            continue
        records.append(_normalize_record(rec))
    return records, skipped


class _TrackingAdapter(LLMAdapter):
    """Lazy proxy that records token usage for every chat call."""

    def __init__(self, factory: Callable[[], LLMAdapter], tracker: UsageTracker):
        self._factory = factory
        self._tracker = tracker
        self._inner: LLMAdapter | None = None

    def _get(self) -> LLMAdapter:
        if self._inner is None:
            self._inner = self._factory()
        return self._inner

    def __getattr__(self, item: str):
        # Only fires for attributes not found normally (name/provider/model).
        # Underscore/dunder probes (copy, pickle, hasattr checks) must NOT
        # trigger building the real client.
        if item.startswith("_"):
            raise AttributeError(item)
        return getattr(self._get(), item)

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        inner = self._get()
        resp = inner.chat(messages, temperature=temperature, max_tokens=max_tokens)
        try:
            self._tracker.record(
                provider=getattr(inner, "provider", "unknown"),
                model=getattr(inner, "model", "unknown"),
                usage=resp.usage,
            )
        except Exception:
            # Tracking is best-effort; never let it break a successful call.
            pass
        return resp
