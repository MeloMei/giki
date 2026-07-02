"""`giki chat` -- Q&A with BM25 retrieval and RAG.

Single-query mode:
    giki chat "What is a wikilink?"

Interactive REPL mode (no positional arg):
    giki chat
    > What is a wikilink?
    ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..console import console, error, info, warn


# ---------------------------------------------------------------------------
# RAG prompt builder
# ---------------------------------------------------------------------------


def _build_rag_prompt(
    context_pages: list[tuple[str, str]],
    question: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_content) for the RAG call."""
    system_prompt = (
        "You are a knowledge base assistant. Answer the user's question "
        "using ONLY the following wiki pages as context."
    )

    if context_pages:
        sections = []
        for title, body in context_pages:
            sections.append(f"### Page: {title}\n{body}")
        context_block = "\n\n".join(sections)
        user_content = (
            f"## Context\n{context_block}\n\n---\n"
            f"Question: {question}\n\n"
            "Provide a clear, concise answer based on the context. "
            "If the context doesn't contain enough information, say so."
        )
    else:
        user_content = (
            f"Question: {question}\n\n"
            "No relevant wiki pages were found. "
            "Say that the knowledge base has no information on this topic."
        )

    return system_prompt, user_content


# ---------------------------------------------------------------------------
# Core ask logic
# ---------------------------------------------------------------------------


def _ask(
    question: str,
    *,
    top_k: int,
    root: Path,
) -> str:
    """Search the wiki, build RAG prompt, call LLM, return answer text."""
    from ..config import load_config
    from ..llm import build_client
    from ..llm.base import Message
    from ..search import SearchIndex
    from ..wiki.parser import parse_page
    from ..wiki.store import WikiStore

    root = root.resolve()

    # Load config
    config = load_config(root)

    # Build / load search index
    store = WikiStore(root)
    idx = SearchIndex(root)
    if not idx.load():
        idx.build(store.wiki_dir)
        idx.save()

    # Search
    results = idx.search(question, top_k=top_k)
    context_pages: list[tuple[str, str]] = []
    for slug, _score in results:
        if store.exists(slug):
            try:
                page = parse_page(store.read(slug))
                context_pages.append((page.title, page.body))
            except Exception:
                # Skip pages that fail to parse
                continue

    # Build prompt and call LLM
    system_prompt, user_content = _build_rag_prompt(context_pages, question)
    client = build_client(config.llm.compile)
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_content),
    ]
    response = client.chat(messages)
    return response.text


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------


def _repl(*, top_k: int, root: Path) -> None:
    """Interactive loop: read questions until EOF / Ctrl+C."""
    info("giki chat — interactive mode. Type your question and press Enter.")
    info("Press Ctrl+D (EOF) or Ctrl+C to exit.")
    console.print()

    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        line = line.strip()
        if not line:
            continue

        try:
            answer = _ask(line, top_k=top_k, root=root)
        except Exception as exc:
            error(f"Failed to answer: {exc}")
            continue

        console.print()
        console.print(answer)
        console.print()


# ---------------------------------------------------------------------------
# CLI command
# ---------------------------------------------------------------------------


def chat_command(
    question: Optional[str] = typer.Argument(
        None,
        help="Question to ask. If omitted, starts interactive REPL mode.",
    ),
    top_k: int = typer.Option(3, "--top-k", help="Number of pages to retrieve."),
    root: Path = typer.Option(Path("."), "--root", help="Wiki project root."),
) -> None:
    """Ask questions about your wiki using BM25 retrieval and RAG."""
    if question:
        try:
            answer = _ask(question, top_k=top_k, root=root)
        except Exception as exc:
            error(f"Failed to answer: {exc}")
            raise typer.Exit(code=1)
        console.print(answer)
    else:
        _repl(top_k=top_k, root=root)
