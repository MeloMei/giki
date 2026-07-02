"""MCP server scaffold for giki.

Exposes giki CLI commands as MCP tools so platforms like QoderWork,
Claude Code, and Codex can invoke giki via stdio transport.
"""

from mcp.server.fastmcp import FastMCP


def create_server() -> FastMCP:
    """Create and return a FastMCP server with giki tool definitions."""
    server = FastMCP("giki")

    @server.tool(name="giki_init")
    async def giki_init() -> str:
        """Initialize a new giki wiki repository (placeholder)."""
        return "giki_init: not yet implemented"

    @server.tool(name="giki_ingest")
    async def giki_ingest() -> str:
        """Ingest sources into the wiki (placeholder)."""
        return "giki_ingest: not yet implemented"

    @server.tool(name="giki_review")
    async def giki_review() -> str:
        """Run the review pipeline (placeholder)."""
        return "giki_review: not yet implemented"

    @server.tool(name="giki_config_show")
    async def giki_config_show() -> str:
        """Show current giki configuration (placeholder)."""
        return "giki_config_show: not yet implemented"

    return server


def main() -> None:
    """Entry point that runs the MCP server over stdio transport."""
    server = create_server()
    server.run(transport="stdio")
