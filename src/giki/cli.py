"""giki CLI entry point.

Registers v0.1 commands: ``init``, ``ingest``, ``config``, ``review``.
Future command modules (``lint``, ``merge``, ``collab``, ``serve``,
``chat``, ``fusion``) exist as scaffolding but are not wired up.
"""

from __future__ import annotations

import typer

from .commands.config_cmd import config_app
from .commands.ingest import ingest_command
from .commands.init import init_app
from .commands.review import review_command


app = typer.Typer(
    no_args_is_help=True,
    help="giki — LLM Wiki with software-engineering discipline.",
)

# `init_app` is a Typer sub-app whose callback IS the init command.
app.add_typer(init_app, name="init")
app.command("ingest")(ingest_command)
app.add_typer(config_app, name="config")
app.command("review")(review_command)


def _version_callback(value: bool) -> None:
    if value:
        try:
            from importlib.metadata import version

            v = version("giki")
        except Exception:
            from . import __version__ as v
        typer.echo(f"giki {v}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the giki version and exit.",
    ),
) -> None:
    """giki — LLM Wiki with software-engineering discipline."""
    # No-op; kept so Typer attaches the --version eager option.


if __name__ == "__main__":
    app()
