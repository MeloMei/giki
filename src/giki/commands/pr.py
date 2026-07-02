"""`giki pr create / list / review / merge` command implementations.

Wraps the ``gh`` CLI for pull-request operations. The ``gh`` binary must
be installed and authenticated for ``create``, ``list``, and ``merge``.
The ``review`` sub-command delegates to ``giki review --pr <number>``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import typer

from ..console import console, success, error, info

pr_app = typer.Typer(
    help="Manage pull requests (requires gh CLI).",
    no_args_is_help=True,
)


def _require_gh() -> None:
    """Exit with a friendly error if the ``gh`` CLI is not installed."""
    if shutil.which("gh") is None:
        error(
            "the GitHub CLI (gh) is required but was not found.\n"
            "  Install it from https://cli.github.com/ and run `gh auth login`."
        )
        raise typer.Exit(code=1)


@pr_app.command("create")
def create_pr(
    title: str = typer.Option(..., "--title", help="Pull request title."),
    body: str = typer.Option("", "--body", help="Pull request body (markdown)."),
    base: str = typer.Option("main", "--base", help="Base branch for the PR."),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """Create a pull request via `gh pr create`."""
    _require_gh()

    cmd = [
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--base", base,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0:
        error(result.stderr.strip() or f"gh pr create failed (exit {result.returncode})")
        raise typer.Exit(code=result.returncode)

    # gh prints the PR URL on success
    url = result.stdout.strip()
    success(f"pull request created: {url}")


@pr_app.command("list")
def list_prs(
    state: str = typer.Option(
        "open",
        "--state",
        help="Filter by state: open, closed, merged, or all.",
    ),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """List pull requests via `gh pr list --json`."""
    _require_gh()

    cmd = [
        "gh", "pr", "list",
        "--state", state,
        "--json", "number,title,author,state,url",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0:
        error(result.stderr.strip() or f"gh pr list failed (exit {result.returncode})")
        raise typer.Exit(code=result.returncode)

    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        error("failed to parse gh output")
        raise typer.Exit(code=1)

    if not prs:
        info("no pull requests found")
        return

    for pr in prs:
        number = pr.get("number", "?")
        title = pr.get("title", "")
        author = pr.get("author", {}).get("login", "unknown")
        pr_state = pr.get("state", "")
        url = pr.get("url", "")
        console.print(f"#{number}  {title}  [dim]({pr_state} by {author})[/dim]  {url}")


@pr_app.command("review")
def review_pr(
    number: int = typer.Argument(..., help="Pull request number to review."),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """Run giki review on a pull request (delegates to `giki review --pr`)."""
    from .review import review_command

    review_command(pr=number, post=False, json_output=False, root=root, base="main")


@pr_app.command("merge")
def merge_pr(
    number: int = typer.Argument(..., help="Pull request number to merge."),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Repo root (defaults to current working directory).",
    ),
) -> None:
    """Merge a pull request via `gh pr merge --merge`."""
    _require_gh()

    cmd = ["gh", "pr", "merge", str(number), "--merge"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0:
        error(result.stderr.strip() or f"gh pr merge failed (exit {result.returncode})")
        raise typer.Exit(code=result.returncode)

    success(f"pull request #{number} merged")
