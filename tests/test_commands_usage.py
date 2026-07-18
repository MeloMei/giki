# tests/test_commands_usage.py
"""Tests for the `giki usage` cumulative cost report command."""

from __future__ import annotations

import json
import re

import pytest
from typer.testing import CliRunner

from giki.cli import app
from giki.llm.usage import read_ledger

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def runner():
    return CliRunner()


def _write_ledger(state_dir, records: list[dict]) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    (state_dir / "usage.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rec(command="ingest", run_id="run1", provider="claude",
         model="claude-sonnet-4-5", tin=1000, tout=500, cost=0.0105,
         ts="2026-07-17T10:00:00+00:00"):
    return {
        "ts": ts,
        "command": command,
        "run_id": run_id,
        "provider": provider,
        "model": model,
        "input_tokens": tin,
        "output_tokens": tout,
        "cost_usd": cost,
    }


# --- read_ledger -----------------------------------------------------------


class TestReadLedger:
    def test_missing_ledger_returns_empty(self, tmp_path):
        assert read_ledger(tmp_path) == ([], 0)

    def test_reads_records(self, tmp_path):
        _write_ledger(tmp_path, [_rec(), _rec(command="review", run_id="run2")])
        records, skipped = read_ledger(tmp_path)
        assert len(records) == 2
        assert skipped == 0

    def test_malformed_lines_are_skipped(self, tmp_path):
        state = tmp_path
        state.mkdir(exist_ok=True)
        (state / "usage.jsonl").write_text(
            json.dumps(_rec()) + "\nnot json\n[1,2]\n\n" + json.dumps(_rec()) + "\n",
            encoding="utf-8",
        )
        records, skipped = read_ledger(tmp_path)
        assert len(records) == 2
        assert skipped == 2

    def test_bom_prefixed_ledger_is_read(self, tmp_path):
        # Windows editors often save with a UTF-8 BOM; the first record
        # must not be lost.
        (tmp_path / "usage.jsonl").write_text(
            "﻿" + json.dumps(_rec()) + "\n", encoding="utf-8"
        )
        records, skipped = read_ledger(tmp_path)
        assert len(records) == 1
        assert skipped == 0


# --- giki usage command ----------------------------------------------------


class TestUsageCommand:
    def test_no_ledger_friendly_message(self, runner, tmp_path):
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "No LLM usage recorded yet" in out

    def test_totals_panel(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(tin=1000, tout=500, cost=0.0105),
                _rec(command="review", run_id="run2", tin=2000, tout=1000, cost=0.0210),
            ],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "2 LLM call(s)" in out
        assert "3,000 tokens in" in out
        assert "1,500 tokens out" in out
        assert "$0.0315" in out

    def test_breakdown_by_command_and_model(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(command="ingest", run_id="run1"),
                _rec(command="review", run_id="run2", model="gpt-4o", provider="openai"),
            ],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "By command" in out
        assert "ingest" in out
        assert "review" in out
        assert "By model" in out
        assert "claude:claude-sonnet-4-5" in out
        assert "openai:gpt-4o" in out

    def test_partial_cost_marked(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(cost=0.0105), _rec(run_id="run2", model="mystery", cost=None)],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert ">= $0.0105" in out

    def test_all_unknown_cost_shows_na(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(model="mystery", cost=None)])
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "n/a" in out
        # a group with zero known costs must not render ">= $0.0000"
        assert "$0.0000" not in out

    def test_recent_runs_lists_latest(self, runner, tmp_path):
        records = [
            _rec(run_id=f"run{i}", ts=f"2026-07-{10 + i:02d}T10:00:00+00:00")
            for i in range(7)
        ]
        _write_ledger(tmp_path / ".giki-state", records)
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "Recent runs" in out
        # only the 5 most recent runs are shown
        assert "run6" in out
        assert "run2" in out
        assert "run0" not in out
        assert "run1" not in out

    def test_malformed_lines_warn_but_succeed(self, runner, tmp_path):
        state = tmp_path / ".giki-state"
        state.mkdir()
        (state / "usage.jsonl").write_text(
            json.dumps(_rec()) + "\ngarbage\n", encoding="utf-8"
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "skipped 1 malformed ledger line(s)" in out
        assert "1 LLM call(s)" in out

    def test_records_without_run_id_grouped(self, runner, tmp_path):
        # Ledgers written before run_id existed must still render.
        rec = _rec()
        del rec["run_id"]
        _write_ledger(tmp_path / ".giki-state", [rec])
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "(no run id)" in out

    def test_malformed_field_types_do_not_crash(self, runner, tmp_path):
        # Hand-edited ledgers may carry wrong types; reporting must survive.
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(model="mystery", tin="abc", tout=None, cost="not-a-number"),
                _rec(run_id=12345, command=None, cost="0.5"),
            ],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "2 LLM call(s)" in out
        assert "12345" in out          # numeric run_id renders as text
        assert "?" in out              # null command falls back to "?"
        assert ">= $0.5" in out        # numeric-string cost is parsed

    def test_all_malformed_ledger_warns_then_reports_empty(self, runner, tmp_path):
        state = tmp_path / ".giki-state"
        state.mkdir()
        (state / "usage.jsonl").write_text("garbage\n[1,2]\n", encoding="utf-8")
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "skipped 2 malformed ledger line(s)" in out
        assert "No LLM usage recorded yet" in out

    def test_breakdown_sorted_by_cost_desc(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(model="cheap-model", cost=0.001),
                _rec(run_id="run2", model="expensive-model", cost=0.5),
                _rec(run_id="run3", model="unknown-model", cost=None),
            ],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert out.index("expensive-model") < out.index("cheap-model")
        assert out.index("cheap-model") < out.index("unknown-model")

    def test_recent_runs_order_is_timezone_aware(self, runner, tmp_path):
        # run1 at 10:00+08:00 is 02:00Z — earlier than run2 at 03:00Z,
        # even though the local-time string looks later.
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(run_id="run-one", ts="2026-07-17T10:00:00+08:00"),
                _rec(run_id="run-two", ts="2026-07-17T03:00:00+00:00"),
            ],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert out.index("run-two") < out.index("run-one")

    def test_panel_shows_ledger_span(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(ts="2026-07-10T08:00:00+00:00"),
                _rec(run_id="run2", ts="2026-07-17T09:30:00+00:00"),
            ],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "ledger span: 2026-07-10 08:00" in out
        assert "2026-07-17 09:30" in out


# --- --since / --json ------------------------------------------------------


class TestSinceFilter:
    def test_since_date_filters_older_records(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(run_id="old-run", ts="2026-07-01T08:00:00+00:00"),
                _rec(run_id="new-run", ts="2026-07-16T08:00:00+00:00"),
            ],
        )
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--since", "2026-07-15"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "1 LLM call(s)" in out
        assert "since 2026-07-15" in out
        assert "new-run" in out
        assert "old-run" not in out

    def test_since_nd_days(self, runner, tmp_path):
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat(timespec="seconds")
        recent = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(run_id="old-run", ts=old), _rec(run_id="new-run", ts=recent)],
        )
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--since", "7d"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "1 LLM call(s)" in out
        assert "new-run" in out
        assert "old-run" not in out

    def test_since_no_matches(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(ts="2026-07-01T08:00:00+00:00")])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--since", "2026-07-15"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "No LLM usage recorded since 2026-07-15" in out

    def test_since_invalid_value_rejected(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec()])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--since", "next-friday"]
        )
        assert result.exit_code != 0
        out = _ANSI_RE.sub("", result.stdout + (result.stderr or ""))
        assert "invalid --since value" in out

    def test_since_zero_days_means_today(self, runner, tmp_path):
        from datetime import datetime, timedelta, timezone

        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(run_id="old-run", ts=yesterday), _rec(run_id="new-run", ts=now)],
        )
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--since", "0d"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "1 LLM call(s)" in out
        assert "new-run" in out

    def test_since_huge_nd_rejected_cleanly(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec()])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--since", "9999999d"]
        )
        assert result.exit_code != 0
        out = _ANSI_RE.sub("", result.stdout + (result.stderr or ""))
        assert "invalid --since value" in out


class TestJsonOutput:
    def test_json_totals_and_groups(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(tin=1000, tout=500, cost=0.0105),
                _rec(command="review", run_id="run2", model="mystery-model",
                     provider="openai", tin=2000, tout=1000, cost=None),
            ],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["version"] == 1
        assert data["total"]["calls"] == 2
        assert data["total"]["input_tokens"] == 3000
        assert data["total"]["output_tokens"] == 1500
        assert data["total"]["cost_usd"] == pytest.approx(0.0105)
        assert data["total"]["partial"] is True
        assert data["by_command"]["ingest"]["calls"] == 1
        assert data["by_model"]["openai:mystery-model"]["cost_usd"] is None
        assert data["skipped_lines"] == 0
        assert data["since"] is None
        assert data["since_resolved"] is None

    def test_json_composes_with_since(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(run_id="old", ts="2026-07-01T08:00:00+00:00"),
                _rec(run_id="new", ts="2026-07-16T08:00:00+00:00"),
            ],
        )
        result = runner.invoke(
            app,
            ["usage", "--root", str(tmp_path), "--since", "2026-07-15", "--json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["total"]["calls"] == 1
        assert data["since"] == "2026-07-15"
        assert data["since_resolved"] is not None
        assert data["since_resolved"].startswith("2026-07-15")

    def test_json_stays_pure_with_malformed_lines(self, runner, tmp_path):
        state = tmp_path / ".giki-state"
        state.mkdir()
        (state / "usage.jsonl").write_text(
            json.dumps(_rec()) + "\ngarbage\n", encoding="utf-8"
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)  # must remain parseable JSON
        assert data["total"]["calls"] == 1
        assert data["skipped_lines"] == 1

    def test_json_empty_ledger_is_valid(self, runner, tmp_path):
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["total"]["calls"] == 0
        assert data["total"]["cost_usd"] is None
        assert data["ledger_span"] is None


# --- --budget --------------------------------------------------------------


class TestBudget:
    def test_under_budget_exits_zero(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(cost=0.0105)])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "Budget: $0.0105 of $5.00 used (0%)" in out

    def test_over_budget_exits_one(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(cost=6.0)])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5"]
        )
        assert result.exit_code == 1, result.output
        out = _ANSI_RE.sub("", result.stdout + (result.stderr or ""))
        assert "Budget exceeded" in out

    def test_budget_partial_cost_warns(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(cost=1.0), _rec(run_id="run2", model="mystery", cost=None)],
        )
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "true cost may be higher" in out

    def test_budget_json_block_and_exit_code(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(cost=6.0)])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5", "--json"]
        )
        assert result.exit_code == 1, result.output
        data = json.loads(result.stdout)  # JSON stays parseable
        assert data["budget"]["limit"] == 5.0
        assert data["budget"]["cost"] == pytest.approx(6.0)
        assert data["budget"]["exceeded"] is True
        assert data["budget"]["remaining"] == pytest.approx(-1.0)

    def test_budget_json_under_budget(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(cost=1.0)])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5", "--json"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["budget"]["exceeded"] is False

    def test_budget_composes_with_since(self, runner, tmp_path):
        _write_ledger(
            tmp_path / ".giki-state",
            [
                _rec(run_id="old", cost=100.0, ts="2026-07-01T08:00:00+00:00"),
                _rec(run_id="new", cost=1.0, ts="2026-07-16T08:00:00+00:00"),
            ],
        )
        result = runner.invoke(
            app,
            ["usage", "--root", str(tmp_path), "--since", "2026-07-15", "--budget", "5"],
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "Budget: $1.0000 of $5.00 used (20%)" in out

    def test_negative_budget_rejected(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec()])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "-5"]
        )
        assert result.exit_code != 0
        out = _ANSI_RE.sub("", result.stdout + (result.stderr or ""))
        assert "--budget must be >= 0" in out

    def test_exactly_at_budget_does_not_exceed(self, runner, tmp_path):
        # 0.1 + 0.2 == 0.30000000000000004 in float — must not trip the gate.
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(cost=0.1), _rec(run_id="run2", cost=0.2)],
        )
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "0.3"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout + (result.stderr or ""))
        assert "Budget exceeded" not in out

    def test_zero_budget(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(cost=0.0)])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "0"]
        )
        assert result.exit_code == 0, result.output

        _write_ledger(tmp_path / ".giki-state", [_rec(cost=0.01)])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "0"]
        )
        assert result.exit_code == 1, result.output

    def test_all_unknown_cost_with_budget(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(model="mystery", cost=None)])
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "n/a of $5.00 used" in out
        assert "true cost may be higher" in out

    def test_empty_ledger_with_budget(self, runner, tmp_path):
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5"]
        )
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "Budget: $0.0000 of $5.00 used (0%)" in out

    def test_empty_ledger_with_budget_json(self, runner, tmp_path):
        result = runner.invoke(
            app, ["usage", "--root", str(tmp_path), "--budget", "5", "--json"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["budget"]["exceeded"] is False
        assert data["budget"]["cost"] is None


# --- historical re-pricing -------------------------------------------------


_CFG_WITH_PRICING = """
llm:
  compile:
    provider: claude
    model: m
    base_url: https://x
    api_key_env: K
  review:
    provider: claude
    model: m
    base_url: https://x
    api_key_env: K
pricing:
  my-gateway-model: [1.0, 4.0]
"""


class TestRepricing:
    def test_null_cost_repriced_with_config_pricing(self, runner, tmp_path):
        (tmp_path / ".giki").mkdir()
        (tmp_path / ".giki" / "config.yaml").write_text(
            _CFG_WITH_PRICING, encoding="utf-8"
        )
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(model="my-gateway-model", cost=None, tin=1_000_000, tout=0)],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert "1 historical record(s) re-priced" in out
        assert "$1.0000" in out
        assert "n/a" not in out

    def test_null_cost_repriced_via_loopback_base_url(self, runner, tmp_path):
        rec = _rec(model="llama3.1", cost=None)
        rec["base_url"] = "http://localhost:11434"
        _write_ledger(tmp_path / ".giki-state", [rec])
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["repriced"] == 1
        assert data["total"]["cost_usd"] == 0.0
        assert data["total"]["partial"] is False

    def test_unpriced_record_stays_na_without_config(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(model="mystery", cost=None)])
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["repriced"] == 0
        assert data["total"]["cost_usd"] is None
        assert data["total"]["partial"] is True

    def test_builtin_table_reprices_known_models(self, runner, tmp_path):
        # No config at all — records with built-in-known models are still
        # re-priced (e.g. model added to the built-in table after the fact).
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(model="gpt-4o", cost=None, tin=1_000_000, tout=0)],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["repriced"] == 1
        assert data["total"]["cost_usd"] == pytest.approx(2.5)
        assert data["total"]["partial"] is False

    def test_broken_config_warns_but_still_runs(self, runner, tmp_path):
        (tmp_path / ".giki").mkdir()
        (tmp_path / ".giki" / "config.yaml").write_text(
            "pricing:\n  my-model: [oops, 4.0]\n", encoding="utf-8"
        )
        _write_ledger(tmp_path / ".giki-state", [_rec(model="mystery", cost=None)])
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        err = _ANSI_RE.sub("", result.stderr or "")
        assert "could not load config for re-pricing" in err

    def test_broken_config_keeps_json_stdout_pure(self, runner, tmp_path):
        (tmp_path / ".giki").mkdir()
        (tmp_path / ".giki" / "config.yaml").write_text(
            "pricing:\n  my-model: [oops, 4.0]\n", encoding="utf-8"
        )
        _write_ledger(tmp_path / ".giki-state", [_rec(model="mystery", cost=None)])
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)  # stdout stays parseable
        assert data["repriced"] == 0

    def test_priced_records_are_not_reestimated(self, runner, tmp_path):
        (tmp_path / ".giki").mkdir()
        (tmp_path / ".giki" / "config.yaml").write_text(
            _CFG_WITH_PRICING, encoding="utf-8"
        )
        # ledger snapshot says 0.5; config would price it at 1.0 — snapshot wins
        _write_ledger(
            tmp_path / ".giki-state",
            [_rec(model="my-gateway-model", cost=0.5, tin=1_000_000, tout=0)],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["repriced"] == 0
        assert data["total"]["cost_usd"] == pytest.approx(0.5)
