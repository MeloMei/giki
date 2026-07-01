"""Load source files (.md, .txt, .pdf, etc.) into LoadedSource objects."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SourceKind = Literal["markdown", "text", "pdf"]

_MARKDOWN_EXTS = {".md", ".markdown"}
_TEXT_EXTS = {".txt", ".rst", ".org", ".log"}
_PDF_EXTS = {".pdf"}


class SourceLoadError(Exception):
    """Source cannot be loaded (missing, unsupported, or corrupt)."""


@dataclass
class LoadedSource:
    path: Path
    kind: SourceKind
    text: str
    sha256: str


def load_source(
    path: Path,
    *,
    pdf_page_separator: str = "<!-- giki:page {n} -->",
    pdf_reject_scanned: bool = True,
) -> LoadedSource:
    """Load a source file and return normalized text + SHA-256 of raw bytes."""
    path = Path(path)
    if not path.exists():
        raise SourceLoadError(f"file not found: {path}")
    if not path.is_file():
        raise SourceLoadError(f"not a regular file: {path}")

    ext = path.suffix.lower()
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()

    if ext in _MARKDOWN_EXTS:
        return LoadedSource(path=path, kind="markdown", text=_decode_text(raw), sha256=sha)
    if ext in _TEXT_EXTS:
        return LoadedSource(path=path, kind="text", text=_decode_text(raw), sha256=sha)
    if ext in _PDF_EXTS:
        text = _load_pdf(raw, path, pdf_page_separator, pdf_reject_scanned)
        return LoadedSource(path=path, kind="pdf", text=text, sha256=sha)

    raise SourceLoadError(f"unsupported extension {ext!r} for {path}")


def _decode_text(raw: bytes) -> str:
    # Decode as UTF-8 and normalize line endings to LF for cross-platform consistency.
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _load_pdf(raw: bytes, path: Path, sep: str, reject_scanned: bool) -> str:
    # PDF handling lands in Task 11.
    raise NotImplementedError("PDF loading arrives in Task 11")
