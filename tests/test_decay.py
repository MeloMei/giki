# tests/test_decay.py
"""Tests for knowledge decay detection (giki decay)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import git
import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.llm.base import LLMAdapter, LLMResponse, Message
from giki.wiki.decay import (
    assess_page_decay,
    extract_signals,
    page_age_days,
    risk_sort_key,
    DecayAssessment,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# --- extract_signals -------------------------------------------------------


class TestExtractSignals:
    def test_version_numbers(self):
        signals = extract_signals("Use Python 3.11 with requests v2.31.0.")
        assert "3.11" in signals
        assert "v2.31.0" in signals

    def test_english_time_phrases(self):
        signals = extract_signals("The latest stable release is currently recommended.")
        assert "latest" in signals
        assert "stable" in signals
        assert "currently" in signals

    def test_chinese_time_phrases(self):
        signals = extract_signals("目前最新的稳定版是 2.0。")
        assert "目前" in signals
        assert "最新" in signals
        assert "稳定版" in signals

    def test_dedup_and_order(self):
        signals = extract_signals("3.11 then 3.11 again, latest latest")
        assert signals.count("3.11") == 1
        assert signals.count("latest") == 1
        assert signals[0] == "3.11"

    def test_no_signals_returns_empty(self):
        assert extract_signals("The observer pattern notifies many observers.") == []

    def test_word_boundaries_prevent_substring_false_positives(self):
        assert extract_signals("The benchmark results are convincing.") == []
        assert extract_signals("This build is unstable and may crash.") == []

    def test_substring_dedup_keeps_longer_phrase(self):
        signals = extract_signals("currently recommended")
        assert "currently" in signals
        assert "current" not in signals

    def test_dotted_dates_are_not_versions(self):
        assert "2026.07.19" not in extract_signals("today is 2026.07.19")

    def test_signal_cap(self):
        body = " ".join(f"1.{i}" for i in range(10, 40))
        assert len(extract_signals(body)) <= 12


# --- page_age_days ---------------------------------------------------------


class TestPageAgeDays:
    def test_age_in_days(self):
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        updated = (now - timedelta(days=30)).isoformat()
        assert page_age_days(updated, now=now) == 30

    def test_naive_timestamp_treated_as_utc(self):
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        assert page_age_days("2026-07-18T00:00:00", now=now) == 1

    def test_unparseable_returns_none(self):
        assert page_age_days("not-a-date") is None

    def test_future_timestamp_clamps_to_zero(self):
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        future = (now + timedelta(days=5)).isoformat()
        assert page_age_days(future, now=now) == 0


# --- risk_sort_key ---------------------------------------------------------


class TestRiskSortKey:
    def test_high_first_then_oldest(self):
        def a(risk, age):
            return DecayAssessment(slug="x", risk=risk, age_days=age)

        items = [a("low", 100), a("high", 10), a("medium", 50), a("high", 90), a("unknown", 1)]
        ordered = sorted(items, key=risk_sort_key)
        assert [(i.risk, i.age_days) for i in ordered] == [
            ("high", 90),
            ("high", 10),
            ("medium", 50),
            ("low", 100),
            ("unknown", 1),
        ]


# --- assess_page_decay -----------------------------------------------------


class _FakeLLM(LLMAdapter):
    provider = "fake"
    model = "fake-m"
    name = "fake:fake-m"

    def __init__(self, response):
        self._response = response
        self.calls: list[list[Message]] = []

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        self.calls.append(list(messages))
        if isinstance(self._response, Exception):
            raise self._response
        return LLMResponse(text=self._response, finish_reason="stop")


class TestAssessPageDecay:
    def _assess(self, response):
        return assess_page_decay(
            llm=_FakeLLM(response),
            slug="my-page",
            title="My Page",
            body="Python 3.8 is the latest version.",
            age_days=200,
            signals=["3.8", "latest"],
        )

    def test_high_risk_with_claims(self):
        resp = json.dumps({
            "risk": "high",
            "stale_claims": [
                {
                    "claim": "Python 3.8 is the latest",
                    "reason": "3.8 is EOL",
                    "suggestion": "update to 3.12",
                }
            ],
        })
        a = self._assess(resp)
        assert a.risk == "high"
        assert len(a.stale_claims) == 1
        assert a.stale_claims[0].claim == "Python 3.8 is the latest"
        assert a.age_days == 200
        assert a.signals == ["3.8", "latest"]

    def test_low_risk_no_claims(self):
        a = self._assess(json.dumps({"risk": "low", "stale_claims": []}))
        assert a.risk == "low"
        assert a.stale_claims == []

    def test_llm_failure_degrades_to_unknown(self):
        a = self._assess(RuntimeError("boom"))
        assert a.risk == "unknown"
        assert a.stale_claims == []

    def test_invalid_json_degrades_to_unknown(self):
        a = self._assess("not json at all")
        assert a.risk == "unknown"

    def test_invalid_risk_value_degrades(self):
        a = self._assess(json.dumps({"risk": "critical", "stale_claims": []}))
        assert a.risk == "unknown"

    def test_malformed_claims_skipped(self):
        resp = json.dumps({
            "risk": "medium",
            "stale_claims": ["just-a-string", {"claim": "ok", "reason": "r", "suggestion": "s"}],
        })
        a = self._assess(resp)
        assert a.risk == "medium"
        assert len(a.stale_claims) == 1

    def test_prompt_injects_today(self):
        llm = _FakeLLM(json.dumps({"risk": "low", "stale_claims": []}))
        assess_page_decay(
            llm=llm, slug="s", title="t", body="body", age_days=10, signals=[]
        )
        prompt = llm.calls[0][0].content
        assert "Today's date: 20" in prompt

    def test_prompt_marks_truncated_content(self):
        llm = _FakeLLM(json.dumps({"risk": "low", "stale_claims": []}))
        assess_page_decay(
            llm=llm, slug="s", title="t", body="x" * 7000, age_days=10, signals=[]
        )
        prompt = llm.calls[0][0].content
        assert "first 6000 of 7000 characters" in prompt

    def test_prompt_no_truncation_note_for_short_pages(self):
        llm = _FakeLLM(json.dumps({"risk": "low", "stale_claims": []}))
        assess_page_decay(
            llm=llm, slug="s", title="t", body="short", age_days=10, signals=[]
        )
        prompt = llm.calls[0][0].content
        assert "first 6000 of" not in prompt


# --- CLI end-to-end --------------------------------------------------------


_CFG_YAML = """
llm:
  compile:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
  review:
    provider: claude
    model: fake-m
    base_url: https://x
    api_key_env: TEST_KEY
"""


def _page(slug: str, body: str, updated: str = "2026-01-01T00:00:00+00:00") -> str:
    return (
        f"---\ntitle: {slug}\ncreated: 2025-01-01T00:00:00+00:00\n"
        f"updated: {updated}\nsources:\n  - path: src.md\n---\n\n{body}\n"
    )


def _init_kb(tmp_path, pages: dict[str, str]) -> None:
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.co").release()
    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(_CFG_YAML, encoding="utf-8")
    (tmp_path / "wiki").mkdir()
    for slug, body in pages.items():
        (tmp_path / "wiki" / f"{slug}.md").write_text(_page(slug, body), encoding="utf-8")
    repo.index.add([".giki/config.yaml"] + [f"wiki/{s}.md" for s in pages])
    repo.index.commit("initial")


class _ScriptedLLM(LLMAdapter):
    provider = "fake"
    model = "claude-sonnet-4-5"
    name = "fake:claude-sonnet-4-5"

    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        text = self._responses.pop(0)
        return LLMResponse(
            text=text,
            usage={"input_tokens": 800, "output_tokens": 200},
            finish_reason="stop",
        )


@pytest.fixture
def runner():
    return CliRunner()


_HIGH_RESP = json.dumps({
    "risk": "high",
    "stale_claims": [
        {"claim": "Python 3.8 is latest", "reason": "3.8 EOL", "suggestion": "bump to 3.12"}
    ],
})
_LOW_RESP = json.dumps({"risk": "low", "stale_claims": []})


def _make_recent(tmp_path, slug: str, body: str) -> None:
    """Rewrite a page with a fresh `updated` so age-anchoring skips it."""
    recent = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (tmp_path / "wiki" / f"{slug}.md").write_text(
        _page(slug, body, updated=recent), encoding="utf-8"
    )


class TestDecayCommand:
    def test_report_output_and_ledger(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "python-guide": "Python 3.8 is the latest stable version.",
            "design-patterns": "The observer pattern notifies many observers.",
        })
        # no signals AND young → truly skipped
        _make_recent(tmp_path, "design-patterns", "The observer pattern notifies many observers.")
        llm = _ScriptedLLM([_HIGH_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(app, ["decay", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "Knowledge Decay Report" in out
        assert "1 page(s) assessed" in out
        assert "1 high" in out
        assert "python-guide" in out
        assert "Python 3.8 is latest" in out
        # page without signals was skipped, not assessed
        assert "design-patterns" not in out
        assert "skipped (no time-sensitive signals)" in out
        # usage panel + ledger
        assert "LLM Usage" in out
        ledger = tmp_path / ".giki-state" / "usage.jsonl"
        assert ledger.exists()
        rec = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
        assert rec["command"] == "decay"

    def test_json_output(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "python-guide": "Python 3.8 is the latest stable version.",
            "design-patterns": "The observer pattern notifies many observers.",
        })
        _make_recent(tmp_path, "design-patterns", "The observer pattern notifies many observers.")
        llm = _ScriptedLLM([_HIGH_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(app, ["decay", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["pages_assessed"] == 1
        assert data["pages_skipped_no_signals"] == 1
        assert data["assessments"][0]["slug"] == "python-guide"
        assert data["assessments"][0]["risk"] == "high"
        assert data["usage"]["calls"] == 1

    def test_no_candidate_pages_friendly_message(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "design-patterns": "The observer pattern notifies many observers.",
        })
        _make_recent(tmp_path, "design-patterns", "The observer pattern notifies many observers.")
        result = runner.invoke(app, ["decay", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "nothing to assess" in out

    def test_all_flag_assesses_signalless_pages(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "design-patterns": "The observer pattern notifies many observers.",
        })
        # young + signalless → only assessed because of --all
        _make_recent(tmp_path, "design-patterns", "The observer pattern notifies many observers.")
        llm = _ScriptedLLM([_LOW_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(app, ["decay", "--root", str(tmp_path), "--all"])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "1 page(s) assessed" in out

    def test_max_pages_limits_llm_calls(self, runner, tmp_path):
        pages = {f"page-{i}": f"Version {i}.0 is the latest." for i in range(5)}
        _init_kb(tmp_path, pages)
        llm = _ScriptedLLM([_LOW_RESP, _LOW_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(
                app, ["decay", "--root", str(tmp_path), "--max-pages", "2"]
            )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "2 page(s) assessed" in out
        assert "not assessed (--max-pages)" in out

    def test_min_age_days_filters(self, runner, tmp_path):
        recent = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _init_kb(tmp_path, {
            "fresh-page": "Python 3.12 is the latest.",
        })
        # page updated just now → filtered by --min-age-days 30
        (tmp_path / "wiki" / "fresh-page.md").write_text(
            _page("fresh-page", "Python 3.12 is the latest.", updated=recent),
            encoding="utf-8",
        )
        result = runner.invoke(
            app, ["decay", "--root", str(tmp_path), "--min-age-days", "30"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "nothing to assess" in out

    def test_missing_wiki_dir_errors(self, runner, tmp_path):
        result = runner.invoke(app, ["decay", "--root", str(tmp_path)])
        assert result.exit_code == 1

    def test_invalid_filename_page_does_not_crash(self, runner, tmp_path):
        _init_kb(tmp_path, {"python-guide": "Python 3.8 is the latest."})
        # An Obsidian-style filename that violates the slug pattern.
        (tmp_path / "wiki" / "My Note.md").write_text("# hello\n", encoding="utf-8")
        llm = _ScriptedLLM([_LOW_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(app, ["decay", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["pages_assessed"] == 1
        assert data["pages_skipped_unparseable"] == 1

    def test_json_empty_candidates_is_valid_json(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "design-patterns": "The observer pattern notifies many observers.",
        })
        _make_recent(tmp_path, "design-patterns", "The observer pattern notifies many observers.")
        result = runner.invoke(app, ["decay", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["pages_assessed"] == 0
        assert data["assessments"] == []
        assert data["pages_skipped_no_signals"] == 1

    def test_oldest_page_gets_llm_budget_first(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "aaa-new": "Python 3.12 is the latest.",
            "zzz-old": "Python 3.8 is the latest.",
        })
        # aaa-new is young (updated now); zzz-old is ancient (updated 2026-01-01).
        recent = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (tmp_path / "wiki" / "aaa-new.md").write_text(
            _page("aaa-new", "Python 3.12 is the latest.", updated=recent),
            encoding="utf-8",
        )
        llm = _ScriptedLLM([_LOW_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(
                app, ["decay", "--root", str(tmp_path), "--max-pages", "1", "--json"]
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["pages_assessed"] == 1
        assert data["assessments"][0]["slug"] == "zzz-old"

    def test_fail_on_high_exits_one(self, runner, tmp_path):
        _init_kb(tmp_path, {"python-guide": "Python 3.8 is the latest."})
        llm = _ScriptedLLM([_HIGH_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(
                app, ["decay", "--root", str(tmp_path), "--fail-on", "high"]
            )
        assert result.exit_code == 1, result.output
        out = _ANSI_RE.sub("", result.stdout + (result.stderr or ""))
        assert "decay gate failed" in out

    def test_fail_on_high_passes_without_high_risk(self, runner, tmp_path):
        _init_kb(tmp_path, {"python-guide": "Python 3.12 is the latest."})
        llm = _ScriptedLLM([_LOW_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(
                app, ["decay", "--root", str(tmp_path), "--fail-on", "high"]
            )
        assert result.exit_code == 0, result.output

    def test_fail_on_high_json_keeps_payload(self, runner, tmp_path):
        _init_kb(tmp_path, {"python-guide": "Python 3.8 is the latest."})
        llm = _ScriptedLLM([_HIGH_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(
                app, ["decay", "--root", str(tmp_path), "--fail-on", "high", "--json"]
            )
        assert result.exit_code == 1, result.output
        data = json.loads(result.stdout)  # stdout stays parseable
        assert data["assessments"][0]["risk"] == "high"

    def test_fail_on_rejects_other_levels(self, runner, tmp_path):
        _init_kb(tmp_path, {"python-guide": "Python 3.8 is the latest."})
        result = runner.invoke(
            app, ["decay", "--root", str(tmp_path), "--fail-on", "medium"]
        )
        assert result.exit_code == 2
        out = _ANSI_RE.sub("", result.stdout + (result.stderr or ""))
        assert "only accepts 'high'" in out

    def test_fail_on_high_empty_candidates_exits_zero(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "design-patterns": "The observer pattern notifies many observers.",
        })
        _make_recent(tmp_path, "design-patterns", "The observer pattern notifies many observers.")
        result = runner.invoke(
            app, ["decay", "--root", str(tmp_path), "--fail-on", "high"]
        )
        assert result.exit_code == 0, result.output

    def test_unknown_risk_does_not_trip_gate(self, runner, tmp_path):
        _init_kb(tmp_path, {"python-guide": "Python 3.8 is the latest."})

        class _BrokenLLM(_ScriptedLLM):
            def chat(self, messages, *, temperature=0.0, max_tokens=4096):
                raise RuntimeError("API down")

        with patch("giki.commands.decay.build_client", return_value=_BrokenLLM([])):
            result = runner.invoke(
                app, ["decay", "--root", str(tmp_path), "--fail-on", "high", "--json"]
            )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["assessments"][0]["risk"] == "unknown"

    def test_old_page_without_signals_is_anchored_by_age(self, runner, tmp_path):
        _init_kb(tmp_path, {
            "design-patterns": "The observer pattern notifies many observers.",
        })
        # no signals, but updated 2026-01-01 — well over 180 days old
        llm = _ScriptedLLM([_LOW_RESP])
        with patch("giki.commands.decay.build_client", return_value=llm):
            result = runner.invoke(app, ["decay", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["pages_assessed"] == 1
        assert data["assessments"][0]["slug"] == "design-patterns"
