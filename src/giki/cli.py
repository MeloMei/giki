"""giki CLI entry point.

Registers commands: ``init``, ``ingest``, ``config``, ``review``, ``mcp-serve``,
``branch``, ``pr``.
Future command modules (``lint``, ``merge``, ``collab``, ``serve``,
``chat``, ``fusion``) exist as scaffolding but are not wired up.
"""

from __future__ import annotations

import typer

from .commands.branch import branch_app
from .commands.config_cmd import config_app
from .commands.ingest import ingest_command
from .commands.init import init_app
from .commands.pr import pr_app
from .commands.review import review_command
from .commands.serve import serve_command
from .console import show_banner


app = typer.Typer(
    no_args_is_help=True,
    help="giki — LLM Wiki with software-engineering discipline.",
)

# `init_app` is a Typer sub-app whose callback IS the init command.
app.add_typer(init_app, name="init")
app.command("ingest")(ingest_command)
app.add_typer(config_app, name="config")
app.command("review")(review_command)
app.add_typer(branch_app, name="branch")
app.add_typer(pr_app, name="pr")
app.command("serve")(serve_command)


@app.command("mcp-serve")
def mcp_serve() -> None:
    """Start the giki MCP server (stdio transport).

    Use this to connect giki to QoderWork, Claude Code, or other
    MCP-compatible platforms. The platform's built-in LLM drives
    giki's compilation and review pipeline.
    """
    from .mcp_server import main
    main()


def _version_callback(value: bool) -> None:
    if value:
        try:
            from importlib.metadata import version

            v = version("giki")
        except Exception:
            from . import __version__ as v
        from .console import console
        console.print(f"[bold]giki[/bold] [dim]{v}[/dim]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def _main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the giki version and exit.",
    ),
) -> None:
    """giki — LLM Wiki with software-engineering discipline."""
    if ctx.invoked_subcommand is None:
        show_banner()
        from .console import console
        console.print("\n[dim]Run [bold]giki --help[/bold] for available commands.[/dim]")


if __name__ == "__main__":
    app()
