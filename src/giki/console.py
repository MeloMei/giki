"""Shared rich-console helpers for giki CLI output.

Provides a pre-configured :class:`rich.console.Console` instance and
convenience wrappers for coloured output, panels, tables, and progress.

In non-TTY environments (tests, CI, piped output), all functions fall
back to plain-text output for compatibility.
"""

from __future__ import annotations

import sys
import os
import re

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


def _is_tty() -> bool:
    """Check if stdout is a terminal."""
    return sys.stdout.isatty()


def _strip_markup(text: str) -> str:
    """Remove rich markup tags like [bold], [/dim], etc."""
    return re.sub(r'\[/?[a-z]+\]', '', text)


# ── Console (TTY-aware) ─────────────────────────────────────────────────────

# Module-level console for TTY output. For non-TTY, we use a separate
# stripped console or plain `print()` calls.
console = Console(highlight=False)
_plain_console = Console(highlight=False, force_terminal=False, no_color=True)


def _print(msg: str, **kwargs) -> None:
    """Print to stdout, using rich markup on TTY, stripped on non-TTY."""
    if _is_tty():
        console.print(msg, **kwargs)
    else:
        # Strip rich markup tags for non-TTY output
        _plain_console.print(msg, **kwargs)


def _print_err(msg: str) -> None:
    """Print to stderr."""
    c = Console(stderr=True, highlight=False, force_terminal=_is_tty(),
                no_color=not _is_tty())
    c.print(msg)


# ── Banner ──────────────────────────────────────────────────────────────────

BANNER = r"""
  ██████╗ ██╗██╗  ██╗██╗
 ██╔════╝ ██║██║ ██╔╝██║   [bold]Git-Native LLM Wiki[/bold]
 ██║  ██╗ ██║█████╔╝ ██║   Compile knowledge like code
 ██║  ██║ ██║██╔═██╗ ██║
 ╚██████╔╝ ██║██║  ██╗██║   [dim]Review like a pull request[/dim]
  ╚═════╝  ╚═╝╚═╝  ╚═╝╚═╝
"""

PLAIN_BANNER = r"""
  giki  v0.1.0
  Git-Native LLM Wiki
  Compile knowledge like code · Review like a pull request
"""


def show_banner() -> None:
    """Print the giki logo banner."""
    if _is_tty():
        console.print(BANNER)
    else:
        console.print(PLAIN_BANNER)


# ── Output helpers ───────────────────────────────────────────────────────────


def success(msg: str) -> None:
    """Print a green success message (or plain '+' prefix on non-TTY)."""
    if _is_tty():
        console.print(f"[green]+[/green] {msg}")
    else:
        print(f"+ {msg}")


def warn(msg: str) -> None:
    """Print a yellow warning."""
    if _is_tty():
        console.print(f"[yellow]![/yellow] {msg}")
    else:
        print(f"! {msg}")


def error(msg: str) -> None:
    """Print a red error to stderr."""
    if _is_tty():
        _print_err(f"[red]×[/red] {msg}")
    else:
        print(f"error: {msg}", file=sys.stderr)


def info(msg: str) -> None:
    """Print a blue info message."""
    if _is_tty():
        console.print(f"[blue]i[/blue] {msg}")
    else:
        print(f"i {msg}")


def dim(msg: str) -> None:
    """Print dimmed secondary text."""
    if _is_tty():
        console.print(f"[dim]{msg}[/dim]")
    else:
        print(f"  {msg}")


def heading(text: str) -> None:
    """Print a bold section heading."""
    if _is_tty():
        console.print(f"\n[bold]{text}[/bold]")
    else:
        print(f"\n{text}")


def panel(content: str, title: str = "", *, style: str = "") -> Panel:
    """Return a rich Panel. Use ``console.print(panel(...))``."""
    return Panel(content.strip(), title=title, box=box.ROUNDED, border_style=style)


def print_panel(content: str, title: str = "", *, style: str = "") -> None:
    """Print a rich Panel (TTY) or a simple bordered box (non-TTY)."""
    if _is_tty():
        console.print(panel(content, title=title, style=style))
    else:
        # Plain-text fallback: strip rich markup
        content = _strip_markup(content)
        lines = []
        if title:
            lines.append(f"── {title} ──")
        for line in content.strip().split("\n"):
            lines.append(f"  {line}")
        print("\n".join(lines))


def key_value_table(rows: list[tuple[str, str]], title: str = "") -> None:
    """Print a two-column key-value table."""
    if _is_tty():
        table = Table(title=title, box=box.SIMPLE, show_header=False, padding=(0, 1))
        table.add_column("Key", style="dim", width=30)
        table.add_column("Value")
        for k, v in rows:
            table.add_row(k, str(v))
        console.print(table)
    else:
        if title:
            print(f"\n{title}")
        for k, v in rows:
            print(f"  {k}: {v}")
