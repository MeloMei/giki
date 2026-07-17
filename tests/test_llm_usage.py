# tests/test_llm_usage.py
"""Tests for LLM usage tracking, cost estimation, and CLI wiring."""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import git
import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.llm.base import LLMAdapter, LLMResponse, Message
from giki.llm.usage import (
    UsageTracker,
    estimate_cost,
    extract_tokens,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# --- extract_tokens --------------------------------------------------------


class TestExtractTokens:
    def test_claude_format(self):
        assert extract_tokens({"input_tokens": 12, "output_tokens": 34}) == (12, 34)

    def test_openai_format(self):
        assert extract_tokens({"prompt_tokens": 12, "completion_tokens": 34}) == (12, 34)

    def test_none_and_empty(self):
        assert extract_tokens(None) == (0, 0)
        assert extract_tokens({}) == (0, 0)

    def test_missing_keys_default_zero(self):
        assert extract_tokens({"input_tokens": 5}) == (5, 0)

    def test_zero_values_stay_zero(self):
        assert extract_tokens({"input_tokens": 0, "output_tokens": 0}) == (0, 0)

    def test_malformed_values_degrade_to_zero(self):
        # Third-party gateways sometimes emit junk — tracking must not raise.
        assert extract_tokens({"input_tokens": "abc", "output_tokens": None}) == (0, 0)
        assert extract_tokens({"input_tokens": "12", "output_tokens": 3.9}) == (12, 3)
        assert extract_tokens({"input_tokens": True}) == (0, 0)
        assert extract_tokens(["not", "a", "dict"]) == (0, 0)
        assert extract_tokens("nope") == (0, 0)


# --- estimate_cost ---------------------------------------------------------


class TestEstimateCost:
    def test_known_model(self):
        # claude-sonnet-4: $3/M input, $15/M output
        cost = estimate_cost("claude-sonnet-4-5-20250929", 1_000_000, 100_000)
        assert cost == pytest.approx(3.0 + 1.5)

    def test_prefix_match_is_case_insensitive(self):
        assert estimate_cost("GPT-4o", 1_000_000, 0) == pytest.approx(2.5)

    def test_unknown_model_returns_none(self):
        assert estimate_cost("my-local-model", 1000, 1000) is None


# --- UsageTracker ----------------------------------------------------------


class _FakeLLM(LLMAdapter):
    provider = "fake"
    model = "claude-sonnet-4-5"
    name = "fake:claude-sonnet-4-5"

    def __init__(self, usage=None):
        self._usage = usage
        self.calls = 0

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        self.calls += 1
        return LLMResponse(text="ok", usage=self._usage, finish_reason="stop")


class TestUsageTracker:
    def test_record_accumulates_totals(self):
        t = UsageTracker(command="ingest")
        t.record(provider="claude", model="claude-sonnet-4-5",
                 usage={"input_tokens": 100, "output_tokens": 50})
        t.record(provider="claude", model="claude-sonnet-4-5",
                 usage={"input_tokens": 20, "output_tokens": 10})
        assert len(t.records) == 2
        assert t.total_input == 120
        assert t.total_output == 60

    def test_cost_summary_all_known(self):
        t = UsageTracker(command="ingest")
        t.record(provider="claude", model="claude-sonnet-4-5",
                 usage={"input_tokens": 1_000_000, "output_tokens": 0})
        cost, partial = t.cost_summary()
        assert cost == pytest.approx(3.0)
        assert partial is False

    def test_cost_summary_partial_when_model_unknown(self):
        t = UsageTracker(command="ingest")
        t.record(provider="claude", model="claude-sonnet-4-5",
                 usage={"input_tokens": 1_000_000, "output_tokens": 0})
        t.record(provider="other", model="mystery",
                 usage={"input_tokens": 999, "output_tokens": 999})
        cost, partial = t.cost_summary()
        assert cost == pytest.approx(3.0)
        assert partial is True

    def test_summary_lines_known_cost(self):
        t = UsageTracker(command="review")
        t.record(provider="claude", model="claude-sonnet-4-5",
                 usage={"input_tokens": 1000, "output_tokens": 500})
        text = "\n".join(t.summary_lines())
        assert "1 LLM call(s)" in text
        assert "1,000 tokens in" in text
        assert "estimated cost: $" in text

    def test_summary_lines_unknown_cost(self):
        t = UsageTracker(command="review")
        t.record(provider="fake", model="fake-m", usage=None)
        text = "\n".join(t.summary_lines())
        assert "estimated cost: n/a" in text


# --- lazy wrapping ---------------------------------------------------------


class TestTrackingAdapter:
    def test_factory_not_called_until_first_chat(self):
        built = []
        tracker = UsageTracker(command="ingest")

        def factory():
            built.append(1)
            return _FakeLLM()

        client = tracker.wrap(factory)
        assert built == []
        client.chat([Message(role="user", content="hi")])
        assert built == [1]

    def test_chat_delegates_and_records(self):
        tracker = UsageTracker(command="review")
        fake = _FakeLLM({"input_tokens": 100, "output_tokens": 50})
        client = tracker.wrap(lambda: fake)
        resp = client.chat([Message(role="user", content="a")])
        assert resp.text == "ok"
        assert fake.calls == 1
        assert len(tracker.records) == 1
        rec = tracker.records[0]
        assert rec.command == "review"
        assert rec.provider == "fake"
        assert rec.model == "claude-sonnet-4-5"
        assert rec.input_tokens == 100
        assert rec.output_tokens == 50

    def test_attributes_delegate_to_inner(self):
        tracker = UsageTracker(command="review")
        client = tracker.wrap(lambda: _FakeLLM())
        assert client.name == "fake:claude-sonnet-4-5"
        assert client.provider == "fake"
        assert client.model == "claude-sonnet-4-5"

    def test_underscore_probes_do_not_build_client(self):
        import copy

        built = []
        tracker = UsageTracker(command="review")

        def factory():
            built.append(1)
            return _FakeLLM()

        client = tracker.wrap(factory)
        with pytest.raises(AttributeError):
            client.__some_dunder__
        copy.deepcopy(client)  # must not trigger the factory either
        assert built == []

    def test_record_failure_does_not_break_chat(self):
        tracker = UsageTracker(command="review")
        client = tracker.wrap(lambda: _FakeLLM({"input_tokens": 1}))
        with patch.object(tracker, "record", side_effect=RuntimeError("boom")):
            resp = client.chat([Message(role="user", content="hi")])
        assert resp.text == "ok"


# --- ledger ----------------------------------------------------------------


class TestLedger:
    def test_append_creates_jsonl(self, tmp_path):
        t = UsageTracker(command="ingest")
        t.record(provider="claude", model="claude-sonnet-4-5",
                 usage={"input_tokens": 10, "output_tokens": 5})
        path = t.append_ledger(tmp_path)
        assert path == tmp_path / "usage.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["command"] == "ingest"
        assert rec["provider"] == "claude"
        assert rec["input_tokens"] == 10
        assert rec["output_tokens"] == 5
        assert rec["cost_usd"] is not None
        assert "ts" in rec
        assert rec["run_id"] == t.run_id

    def test_append_accumulates_across_runs(self, tmp_path):
        t1 = UsageTracker(command="ingest")
        t1.record(provider="claude", model="claude-sonnet-4-5", usage=None)
        t1.append_ledger(tmp_path)
        t2 = UsageTracker(command="review")
        t2.record(provider="openai", model="gpt-4o", usage=None)
        t2.append_ledger(tmp_path)
        lines = (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["command"] == "ingest"
        assert json.loads(lines[1])["command"] == "review"

    def test_no_records_returns_none_and_writes_nothing(self, tmp_path):
        t = UsageTracker(command="ingest")
        assert t.append_ledger(tmp_path) is None
        assert not (tmp_path / "usage.jsonl").exists()


# --- add_and_commit exclude ------------------------------------------------


class TestAddAndCommitExclude:
    def test_excluded_path_stays_out_of_commit(self, tmp_path):
        from giki.git_utils import add_and_commit

        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        (tmp_path / "wiki").mkdir()
        (tmp_path / "wiki" / "a.md").write_text("# a\n", encoding="utf-8")
        state = tmp_path / ".giki-state"
        state.mkdir()
        (state / "usage.jsonl").write_text("{}\n", encoding="utf-8")

        commit = add_and_commit(
            repo,
            ["wiki", ".giki-state"],
            "test commit",
            exclude=[".giki-state/usage.jsonl"],
        )
        committed = {item.path for item in commit.tree.traverse()}
        assert "wiki/a.md" in committed
        assert ".giki-state/usage.jsonl" not in committed


# --- CLI wiring ------------------------------------------------------------


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
ingest:
  chunk_size: 12000
  chunk_overlap: 500
  synthesize_context: 6000
wiki:
  related_min_neighbors: 1
"""


def _init_repo(tmp_path, slugs=()):
    repo = git.Repo.init(tmp_path, initial_branch="main")
    repo.config_writer().set_value("user", "name", "T").release()
    repo.config_writer().set_value("user", "email", "t@e.co").release()
    (tmp_path / ".giki").mkdir()
    (tmp_path / ".giki" / "config.yaml").write_text(_CFG_YAML, encoding="utf-8")
    (tmp_path / "wiki").mkdir()
    (tmp_path / "sources").mkdir()
    slug_lines = "\n".join(f"- [[{s}]] — {s}" for s in slugs)
    (tmp_path / "index.md").write_text(
        "# Index\n\n<!-- giki:index-begin -->\n"
        f"## Uncategorized\n{slug_lines}\n"
        "<!-- giki:index-end -->\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    repo.index.add([".giki/config.yaml", "index.md", "README.md"])
    repo.index.commit("initial")
    return repo


class _ScriptedLLM(LLMAdapter):
    """Fake LLM with a known-priced model and token usage per response."""

    provider = "fake"
    model = "claude-sonnet-4-5"
    name = "fake:claude-sonnet-4-5"

    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        text = self._responses.pop(0)
        return LLMResponse(
            text=text,
            usage={"input_tokens": 1000, "output_tokens": 500},
            finish_reason="stop",
        )


@pytest.fixture
def runner():
    return CliRunner()


def _add_page(tmp_path, repo, slug: str) -> None:
    """Commit a wiki page on the current branch (index entry must already
    exist on main — see ``_init_repo(slugs=...)``)."""
    page_content = (
        "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
        "updated: 2026-01-01T00:00:00+00:00\nsources:\n  - path: src.md\n"
        "---\n\nTest body.\n"
    )
    (tmp_path / "wiki" / f"{slug}.md").write_text(page_content, encoding="utf-8")
    repo.index.add([f"wiki/{slug}.md"])
    repo.index.commit(f"add {slug}")


class TestReviewCommandUsage:
    def test_usage_panel_and_ledger(self, runner, tmp_path):
        _init_repo(tmp_path, slugs=["test-page"])
        repo = git.Repo(tmp_path)
        repo.create_head("feature").checkout()
        _add_page(tmp_path, repo, "test-page")

        llm = _ScriptedLLM([json.dumps({"findings": [], "verdict": "approve"})])

        with patch("giki.commands.review.build_client", return_value=llm):
            result = runner.invoke(app, ["review", "--root", str(tmp_path)])

        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "LLM Usage" in out
        assert "1 LLM call(s)" in out
        assert "estimated cost: $" in out

        ledger = tmp_path / ".giki-state" / "usage.jsonl"
        assert ledger.exists()
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["command"] == "review"
        assert rec["input_tokens"] == 1000

    def test_json_mode_keeps_stdout_clean(self, runner, tmp_path):
        _init_repo(tmp_path, slugs=["test-page"])
        repo = git.Repo(tmp_path)
        repo.create_head("feature").checkout()
        _add_page(tmp_path, repo, "test-page")

        llm = _ScriptedLLM([json.dumps({"findings": [], "verdict": "approve"})])

        with patch("giki.commands.review.build_client", return_value=llm):
            result = runner.invoke(
                app, ["review", "--json", "--root", str(tmp_path)]
            )

        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)  # must remain parseable JSON
        assert data["verdict"] == "approve"
        # ledger is still written even in JSON mode
        assert (tmp_path / ".giki-state" / "usage.jsonl").exists()


class TestIngestCommandUsage:
    def test_usage_panel_and_ledger(self, runner, tmp_path):
        _init_repo(tmp_path)

        src = tmp_path / "sources" / "observer.md"
        src.write_text(
            "# Observer\n\nThe Observer pattern is a behavioral design pattern "
            "where one subject notifies many observers.\n",
            encoding="utf-8",
        )

        analyze_resp = json.dumps({
            "suggested_pages": [
                {
                    "filename": "observer-pattern",
                    "title": "Observer Pattern",
                    "action": "create",
                    "hints": ["describe subject and observers"],
                    "source_anchors": ["intro paragraph"],
                    "aliases_suggested": ["Observer"],
                }
            ]
        })
        synth_resp = (
            "# Observer Pattern\n\n"
            "Behavioral design pattern where a subject notifies observers.\n"
        )
        crosslink_resp = json.dumps({"neighbors": [], "inline_hints": []})

        llm = _ScriptedLLM([analyze_resp, synth_resp, crosslink_resp])

        with patch("giki.commands.ingest.build_client", return_value=llm):
            result = runner.invoke(
                app,
                [
                    "ingest",
                    str(src),
                    "--branch",
                    "wiki/observer",
                    "--yes",
                    "--root",
                    str(tmp_path),
                ],
            )

        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "LLM Usage" in out
        assert "3 LLM call(s)" in out
        assert "estimated cost: $" in out

        ledger = tmp_path / ".giki-state" / "usage.jsonl"
        assert ledger.exists()
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
        assert all(json.loads(ln)["command"] == "ingest" for ln in lines)

        # The ledger is local audit state — it must not enter user commits
        # even though this repo has no .gitignore covering *.jsonl.
        repo = git.Repo(tmp_path)
        committed = {item.path for item in repo.head.commit.tree.traverse()}
        assert ".giki-state/usage.jsonl" not in committed
