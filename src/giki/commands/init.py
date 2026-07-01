"""`giki init` — scaffold a new knowledge base directory.

Creates the standard giki layout (`.giki/`, `sources/`, `wiki/`, `.giki-state/`)
and copies template files (config, README, index/log/rules, .gitignore) from the
packaged `giki.templates.init` resources.

Idempotent: existing files are preserved and reported as `· kept <path>`.
"""

from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path

import typer
import git


init_app = typer.Typer(
    help="Initialize a giki knowledge base in the target directory.",
    invoke_without_command=True,
    no_args_is_help=False,
)


# Templates in giki.templates.init -> destination path relative to root.
_FILE_MAP: tuple[tuple[str, str], ...] = (
    ("config.yaml", ".giki/config.yaml"),
    ("gitignore.txt", ".gitignore"),
    ("index.md", "index.md"),
    ("log.md", "log.md"),
    ("wiki-rules.md", "wiki-rules.md"),
    ("readme.md", "README.md"),
)

_DIRS: tuple[str, ...] = (".giki", "sources", "wiki", ".giki-state")


def _read_template(name: str) -> bytes:
    """Read a scaffolding template as raw bytes (preserves line endings)."""
    return resources.files("giki.templates.init").joinpath(name).read_bytes()


def _is_git_repo(root: Path) -> bool:
    try:
        git.Repo(str(root), search_parent_directories=False)
        return True
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return False


def _stdin_is_tty() -> bool:
    """Return True if stdin is a TTY. Wrapped for testability."""
    return sys.stdin.isatty()


def _copy_if_absent(src_name: str, dest: Path) -> bool:
    """Write template `src_name` to `dest` if `dest` does not already exist.

    Returns True if the file was created, False if it was kept.
    """
    if dest.exists():
        typer.echo(f"\u00b7 kept {dest}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_read_template(src_name))
    typer.echo(f"+ created {dest}")
    return True


@init_app.callback()
def init_command(
    with_action: bool = typer.Option(
        False,
        "--with-action",
        help="Generate .github/workflows/giki-review.yml",
    ),
    root: Path = typer.Option(
        Path("."),
        "--root",
        help="Target directory (default: cwd)",
        show_default=False,
    ),
) -> None:
    """Scaffold a giki knowledge base in the target directory."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    if not _is_git_repo(root):
        if not _stdin_is_tty():
            should_init = True
        else:
            should_init = typer.confirm(
                f"{root} is not a git repo. Initialize one?",
                default=True,
            )
        if not should_init:
            typer.echo("Aborted — giki requires a git repository.", err=True)
            raise typer.Exit(code=1)
        git.Repo.init(str(root))
        typer.echo(f"+ initialized git repo at {root}")

    # Create directories.
    for d in _DIRS:
        p = root / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            typer.echo(f"+ created {p}/")
        else:
            typer.echo(f"\u00b7 kept {p}/")

    # Copy scaffolding files.
    for template_name, rel_dest in _FILE_MAP:
        _copy_if_absent(template_name, root / rel_dest)

    # Optional GitHub Action workflow.
    if with_action:
        _copy_if_absent(
            "action.yml", root / ".github" / "workflows" / "giki-review.yml"
        )

    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  1. Edit .giki/config.yaml (LLM provider, model)")
    typer.echo("  2. Drop a file into sources/")
    typer.echo("  3. Run: giki ingest sources/<file> --branch wiki/<topic>")
