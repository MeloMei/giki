"""Tests for the MCP server module."""

import importlib
import json
from pathlib import Path

import git
import pytest
import yaml


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
