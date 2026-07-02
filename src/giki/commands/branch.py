"""`giki branch list / create / switch` command implementations.

Provides local git branch management helpers. These are thin wrappers
around GitPython — no remote operations.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..console import console, success, error
from ..git_utils import open_repo, GitError

branch_app = typer.Typer(
    help="Manage local git branches.",
    no_args_is_help=True,
)


@branch_app.command("list")
def list_branches(
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """List all local branches. The current branch is marked with `*`."""
    try:
        repo = open_repo(root)
    except GitError as e:
        error(str(e))
        raise typer.Exit(code=1)

    active = repo.active_branch.name if not repo.head.is_detached else None

    for head in sorted(repo.heads, key=lambda h: h.name):
        marker = "* " if head.name == active else "  "
        console.print(f"{marker}{head.name}")


@branch_app.command("create")
def create_branch(
    name: str = typer.Argument(..., help="Name of the new branch to create."),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """Create a new branch and switch to it."""
    try:
        repo = open_repo(root)
    except GitError as e:
        error(str(e))
        raise typer.Exit(code=1)

    existing = {h.name for h in repo.heads}
    if name in existing:
        error(f"branch {name!r} already exists")
        raise typer.Exit(code=1)

    try:
        repo.create_head(name).checkout()
    except Exception as e:
        error(f"failed to create branch {name!r}: {e}")
        raise typer.Exit(code=1)

    success(f"created and switched to branch [bold]{name}[/bold]")


@branch_app.command("switch")
def switch_branch(
    name: str = typer.Argument(..., help="Name of the branch to switch to."),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """Switch to an existing branch."""
    try:
        repo = open_repo(root)
    except GitError as e:
        error(str(e))
        raise typer.Exit(code=1)

    heads = {h.name: h for h in repo.heads}
    if name not in heads:
        error(f"branch {name!r} does not exist")
        raise typer.Exit(code=1)

    try:
        heads[name].checkout()
    except Exception as e:
        error(f"failed to switch to branch {name!r}: {e}")
        raise typer.Exit(code=1)

    success(f"switched to branch [bold]{name}[/bold]")
