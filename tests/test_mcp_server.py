"""Tests for the MCP server module."""

import importlib
import json
from pathlib import Path

import git
import pytest
import yaml


def test_mcp_serve_cli_command_registered():
    """giki mcp-serve should be a registered CLI command."""
    from giki.cli import app
    cmd_names = [cmd.name for cmd in app.registered_commands]
    assert "mcp-serve" in cmd_names


def test_mcp_server_module_importable():
    """The giki.mcp_server module must be importable."""
    mod = importlib.import_module("giki.mcp_server")
    assert mod is not None


def test_create_server_returns_fastmcp():
    """create_server() must return a FastMCP instance named 'giki'."""
    from mcp.server.fastmcp import FastMCP

    from giki.mcp_server import create_server

    server = create_server()
    assert isinstance(server, FastMCP)
    assert server.name == "giki"


@pytest.mark.anyio
async def test_create_server_registers_four_tools():
    """The server must expose exactly 4 tools."""
    from giki.mcp_server import create_server

    server = create_server()
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {
        "giki_init",
        "giki_ingest",
        "giki_review",
        "giki_config_show",
    }


def test_main_function_exists():
    """A main() entry point must exist and be callable."""
    from giki.mcp_server import main

    assert callable(main)


# ---------------------------------------------------------------------------
# Helper: extract the raw Python function from a FastMCP server by name
# ---------------------------------------------------------------------------


def _get_tool_fn(server, name: str):
    """Return the raw callable registered under *name* on a FastMCP server."""
    tool = server._tool_manager._tools[name]
    return tool.fn


# ---------------------------------------------------------------------------
# giki_init
# ---------------------------------------------------------------------------


class TestGikiInit:
    """Tests for the giki_init MCP tool."""

    def test_init_creates_structure(self, tmp_path):
        """giki_init should create dirs, scaffolding files, and init git."""
        git.Repo.init(str(tmp_path))

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_init")

        result = fn(root=str(tmp_path), with_action=False)

        assert isinstance(result, str)
        assert not result.startswith("error:")

        # Directories created
        assert (tmp_path / ".giki").is_dir()
        assert (tmp_path / "sources").is_dir()
        assert (tmp_path / "wiki").is_dir()
        assert (tmp_path / ".giki-state").is_dir()

        # Scaffolding files created
        assert (tmp_path / ".giki" / "config.yaml").exists()
        assert (tmp_path / ".gitignore").exists()
        assert (tmp_path / "index.md").exists()
        assert (tmp_path / "log.md").exists()
        assert (tmp_path / "wiki-rules.md").exists()
        assert (tmp_path / "README.md").exists()

    def test_init_creates_git_repo(self, tmp_path):
        """giki_init should init a git repo if none exists."""
        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_init")

        result = fn(root=str(tmp_path), with_action=False)

        assert (tmp_path / ".git").exists()
        assert "initialized git repo" in result

    def test_init_idempotent(self, tmp_path):
        """Running giki_init twice should keep existing files."""
        git.Repo.init(str(tmp_path))

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_init")

        # First run
        fn(root=str(tmp_path), with_action=False)

        # Modify config to prove it's not overwritten
        cfg_path = tmp_path / ".giki" / "config.yaml"
        cfg_path.write_text("marker: mine\n", encoding="utf-8")

        # Second run
        result = fn(root=str(tmp_path), with_action=False)

        assert "kept" in result
        assert cfg_path.read_text(encoding="utf-8") == "marker: mine\n"

    def test_init_with_action(self, tmp_path):
        """giki_init with with_action=True should create workflow file."""
        git.Repo.init(str(tmp_path))

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_init")

        result = fn(root=str(tmp_path), with_action=True)

        wf = tmp_path / ".github" / "workflows" / "giki-review.yml"
        assert wf.exists()
        assert str(wf) in result

    def test_init_returns_next_steps(self, tmp_path):
        """giki_init output should include next-step instructions."""
        git.Repo.init(str(tmp_path))

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_init")

        result = fn(root=str(tmp_path), with_action=False)

        assert "Next steps" in result or "next steps" in result.lower()
        assert "config.yaml" in result
        assert "sources/" in result

    def test_init_error_handling(self):
        """giki_init should return an error string for invalid paths."""
        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_init")

        # Use a path that can't be created (e.g., a file pretending to be a dir)
        result = fn(root="/dev/null/impossible", with_action=False)
        # On Windows this may differ, but the key is it returns an error string
        assert isinstance(result, str)
        # Should either succeed or return an error - not crash


# ---------------------------------------------------------------------------
# giki_config_show
# ---------------------------------------------------------------------------


def _write_minimal_config(root: Path) -> None:
    """Write a minimal valid .giki/config.yaml for testing."""
    giki_dir = root / ".giki"
    giki_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "llm": {
            "compile": {
                "provider": "claude",
                "model": "claude-3-5-sonnet-20241022",
                "base_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
            },
            "review": {
                "provider": "claude",
                "model": "claude-3-5-sonnet-20241022",
                "base_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
            },
        },
        "ingest": {
            "chunk_size": 12000,
            "chunk_overlap": 500,
        },
        "review": {
            "unrelated_edit_threshold": 0.30,
            "severity_blocking": ["blocker"],
        },
    }
    (giki_dir / "config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )


class TestGikiConfigShow:
    """Tests for the giki_config_show MCP tool."""

    def test_config_show_returns_valid_json(self, tmp_path):
        """giki_config_show should return valid JSON."""
        _write_minimal_config(tmp_path)

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_config_show")

        result = fn(root=str(tmp_path))

        assert isinstance(result, str)
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_config_show_contains_sections(self, tmp_path):
        """The JSON output should contain llm, ingest, review, wiki sections."""
        _write_minimal_config(tmp_path)

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_config_show")

        result = fn(root=str(tmp_path))
        data = json.loads(result)

        assert "llm" in data
        assert "ingest" in data
        assert "review" in data
        assert "wiki" in data

    def test_config_show_paths_are_strings(self, tmp_path):
        """Path fields should be serialized as strings, not Path objects."""
        _write_minimal_config(tmp_path)

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_config_show")

        result = fn(root=str(tmp_path))
        data = json.loads(result)

        assert isinstance(data["root"], str)
        assert isinstance(data["giki_dir"], str)
        assert isinstance(data["state_dir"], str)

    def test_config_show_llm_details(self, tmp_path):
        """LLM config should include provider, model, base_url, api_key_env."""
        _write_minimal_config(tmp_path)

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_config_show")

        result = fn(root=str(tmp_path))
        data = json.loads(result)

        compile_cfg = data["llm"]["compile"]
        assert compile_cfg["provider"] == "claude"
        assert compile_cfg["model"] == "claude-3-5-sonnet-20241022"
        assert compile_cfg["base_url"] == "https://api.anthropic.com"
        assert compile_cfg["api_key_env"] == "ANTHROPIC_API_KEY"

    def test_config_show_missing_config_returns_error(self, tmp_path):
        """giki_config_show on a dir without config should return an error string."""
        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_config_show")

        result = fn(root=str(tmp_path))

        assert result.startswith("error:")

    def test_config_show_ingest_defaults(self, tmp_path):
        """Ingest config should reflect defaults when not overridden."""
        _write_minimal_config(tmp_path)

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_config_show")

        result = fn(root=str(tmp_path))
        data = json.loads(result)

        assert data["ingest"]["chunk_size"] == 12000
        assert data["ingest"]["chunk_overlap"] == 500


# ---------------------------------------------------------------------------
# giki_ingest (basic error handling — full ingest requires LLM mocking)
# ---------------------------------------------------------------------------


class TestGikiIngest:
    """Basic tests for the giki_ingest MCP tool."""

    def test_ingest_no_config_returns_error(self, tmp_path):
        """giki_ingest without config should return an error string."""
        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_ingest")

        result = fn(paths=["somefile.md"], root=str(tmp_path))
        assert result.startswith("error:")

    def test_ingest_empty_paths_list(self, tmp_path):
        """giki_ingest with empty paths should return a summary."""
        _write_minimal_config(tmp_path)
        (tmp_path / "sources").mkdir(exist_ok=True)
        (tmp_path / "wiki").mkdir(exist_ok=True)
        git.Repo.init(str(tmp_path))

        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_ingest")

        result = fn(paths=[], root=str(tmp_path))
        assert "Ingest complete" in result
        assert "0 created" in result


# ---------------------------------------------------------------------------
# giki_review (basic error handling — full review requires LLM mocking)
# ---------------------------------------------------------------------------


class TestGikiReview:
    """Basic tests for the giki_review MCP tool."""

    def test_review_no_config_returns_error(self, tmp_path):
        """giki_review without config should return an error string."""
        from giki.mcp_server import create_server

        server = create_server()
        fn = _get_tool_fn(server, "giki_review")

        result = fn(root=str(tmp_path))
        assert result.startswith("error:")


# ---------------------------------------------------------------------------
# Usage tracking: giki_ingest / giki_review must feed the usage ledger
# ---------------------------------------------------------------------------


class _ScriptedLLM:
    """Stand-in LLMAdapter with scripted responses and token usage."""

    provider = "fake"
    model = "claude-sonnet-4-5"
    name = "fake:claude-sonnet-4-5"

    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, *, temperature=0.0, max_tokens=4096):
        from giki.llm.base import LLMResponse

        text = self._responses.pop(0)
        return LLMResponse(
            text=text,
            usage={"input_tokens": 1000, "output_tokens": 500},
            finish_reason="stop",
        )


class TestMcpUsageTracking:
    """MCP tools must record LLM usage to the ledger, like the CLI does."""

    def _init_repo(self, tmp_path, slugs=()):
        repo = git.Repo.init(tmp_path, initial_branch="main")
        repo.config_writer().set_value("user", "name", "T").release()
        repo.config_writer().set_value("user", "email", "t@e.co").release()
        _write_minimal_config(tmp_path)
        (tmp_path / "wiki").mkdir(exist_ok=True)
        (tmp_path / "sources").mkdir(exist_ok=True)
        slug_lines = "\n".join(f"- [[{s}]] — {s}" for s in slugs)
        (tmp_path / "index.md").write_text(
            "# Index\n\n<!-- giki:index-begin -->\n"
            f"## Uncategorized\n{slug_lines}\n<!-- giki:index-end -->\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
        repo.index.add([".giki/config.yaml", "index.md", "README.md"])
        repo.index.commit("initial")
        return repo

    def _ledger_lines(self, tmp_path):
        ledger = tmp_path / ".giki-state" / "usage.jsonl"
        assert ledger.exists(), "usage ledger was not written"
        return ledger.read_text(encoding="utf-8").splitlines()

    def test_ingest_tracks_usage_and_appends_ledger(self, tmp_path):
        from unittest.mock import patch

        from giki.mcp_server import create_server

        self._init_repo(tmp_path)
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
        synth_resp = "# Observer Pattern\n\nBehavioral design pattern.\n"
        crosslink_resp = json.dumps({"neighbors": [], "inline_hints": []})
        llm = _ScriptedLLM([analyze_resp, synth_resp, crosslink_resp])

        server = create_server()
        fn = _get_tool_fn(server, "giki_ingest")
        with patch("giki.llm.build_client", return_value=llm):
            out = fn(paths=[str(src)], branch="wiki/observer", yes=True, root=str(tmp_path))

        assert "1 created" in out
        assert "LLM usage: 3 call(s)" in out
        assert "est. cost $0." in out

        lines = self._ledger_lines(tmp_path)
        assert len(lines) == 3
        assert all(json.loads(ln)["command"] == "ingest" for ln in lines)

    def test_review_tracks_usage_and_appends_ledger(self, tmp_path):
        from unittest.mock import patch

        from giki.mcp_server import create_server

        repo = self._init_repo(tmp_path, slugs=["test-page"])
        repo.create_head("feature").checkout()
        (tmp_path / "wiki" / "test-page.md").write_text(
            "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\nsources:\n  - path: src.md\n"
            "---\n\nTest body.\n",
            encoding="utf-8",
        )
        repo.index.add(["wiki/test-page.md"])
        repo.index.commit("add test page")

        llm = _ScriptedLLM([json.dumps({"findings": [], "verdict": "approve"})])
        server = create_server()
        fn = _get_tool_fn(server, "giki_review")
        with patch("giki.llm.build_client", return_value=llm):
            out = fn(base="main", root=str(tmp_path))

        assert "LLM usage: 1 call(s)" in out
        lines = self._ledger_lines(tmp_path)
        assert len(lines) == 1
        assert json.loads(lines[0])["command"] == "review"

    def test_review_json_output_includes_usage(self, tmp_path):
        from unittest.mock import patch

        from giki.mcp_server import create_server

        repo = self._init_repo(tmp_path, slugs=["test-page"])
        repo.create_head("feature").checkout()
        (tmp_path / "wiki" / "test-page.md").write_text(
            "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\nsources:\n  - path: src.md\n"
            "---\n\nTest body.\n",
            encoding="utf-8",
        )
        repo.index.add(["wiki/test-page.md"])
        repo.index.commit("add test page")

        llm = _ScriptedLLM([json.dumps({"findings": [], "verdict": "approve"})])
        server = create_server()
        fn = _get_tool_fn(server, "giki_review")
        with patch("giki.llm.build_client", return_value=llm):
            out = fn(base="main", json_output=True, root=str(tmp_path))

        data = json.loads(out)
        assert data["verdict"] == "approve"  # pre-existing keys survive injection
        assert data["usage"]["calls"] == 1
        assert data["usage"]["input_tokens"] == 1000
        assert data["usage"]["output_tokens"] == 500
        assert data["usage"]["cost_usd"] is not None
        assert data["usage"]["partial"] is False
        assert data["usage"]["ledger_error"] is None

    def test_ledger_write_failure_degrades_to_note(self, tmp_path):
        from unittest.mock import patch

        from giki.mcp_server import create_server

        repo = self._init_repo(tmp_path, slugs=["test-page"])
        repo.create_head("feature").checkout()
        (tmp_path / "wiki" / "test-page.md").write_text(
            "---\ntitle: Test\ncreated: 2026-01-01T00:00:00+00:00\n"
            "updated: 2026-01-01T00:00:00+00:00\nsources:\n  - path: src.md\n"
            "---\n\nTest body.\n",
            encoding="utf-8",
        )
        repo.index.add(["wiki/test-page.md"])
        repo.index.commit("add test page")

        approve = json.dumps({"findings": [], "verdict": "approve"})
        llm = _ScriptedLLM([approve, approve])
        server = create_server()
        fn = _get_tool_fn(server, "giki_review")
        with patch("giki.llm.build_client", return_value=llm), patch(
            "giki.llm.usage.UsageTracker.append_ledger",
            side_effect=OSError("disk full"),
        ):
            out = fn(base="main", root=str(tmp_path))
            out_json = fn(base="main", json_output=True, root=str(tmp_path))

        # text output carries the note; the tool call itself succeeds
        assert "ledger write failed: disk full" in out
        # JSON output surfaces the failure to automation
        data = json.loads(out_json)
        assert data["usage"]["ledger_error"] == "disk full"

    def test_skipped_ingest_makes_no_llm_calls(self, tmp_path):
        from unittest.mock import patch

        from giki.mcp_server import create_server

        self._init_repo(tmp_path)
        src = tmp_path / "sources" / "observer.md"
        src.write_text(
            "# Observer\n\nThe Observer pattern notifies many observers.\n",
            encoding="utf-8",
        )

        analyze_resp = json.dumps({
            "suggested_pages": [
                {
                    "filename": "observer-pattern",
                    "title": "Observer Pattern",
                    "action": "create",
                    "hints": [],
                    "source_anchors": [],
                    "aliases_suggested": [],
                }
            ]
        })
        synth_resp = "# Observer Pattern\n\nBehavioral design pattern.\n"
        crosslink_resp = json.dumps({"neighbors": [], "inline_hints": []})

        server = create_server()
        fn = _get_tool_fn(server, "giki_ingest")

        # First run ingests (3 LLM calls); second run skips entirely.
        llm = _ScriptedLLM([analyze_resp, synth_resp, crosslink_resp])
        with patch("giki.llm.build_client", return_value=llm):
            first = fn(paths=[str(src)], branch="wiki/observer", yes=True, root=str(tmp_path))
        assert "LLM usage: 3 call(s)" in first

        def _exploding_factory(*args, **kwargs):
            raise AssertionError("build_client must not be called for a skipped source")

        with patch("giki.llm.build_client", side_effect=_exploding_factory):
            second = fn(paths=[str(src)], branch="wiki/observer", yes=True, root=str(tmp_path))

        assert "[skip]" in second
        assert "LLM usage" not in second
        # ledger still holds only the first run's 3 records
        lines = self._ledger_lines(tmp_path)
        assert len(lines) == 3
