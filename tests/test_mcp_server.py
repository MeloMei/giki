"""Tests for the MCP server module."""

import importlib

import pytest


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
    """The server must expose exactly 4 placeholder tools."""
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
