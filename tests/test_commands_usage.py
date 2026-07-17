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
            [_rec(cost=0.0105), _rec(run_id="run2", cost=None)],
        )
        result = runner.invoke(app, ["usage", "--root", str(tmp_path)])
        assert result.exit_code == 0, result.output
        out = _ANSI_RE.sub("", result.stdout)
        assert ">= $0.0105" in out

    def test_all_unknown_cost_shows_na(self, runner, tmp_path):
        _write_ledger(tmp_path / ".giki-state", [_rec(cost=None)])
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
                _rec(tin="abc", tout=None, cost="not-a-number"),
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
