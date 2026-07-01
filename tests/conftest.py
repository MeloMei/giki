"""Shared pytest fixtures."""

from pathlib import Path
import pytest
from pypdf import PdfWriter


@pytest.fixture
def tiny_pdf():
    """A 3-page PDF with distinguishable text on each page.

    Committed to the repo as tests/fixtures/hello.pdf. Regenerate with:
        python tests/fixtures/_make_hello_pdf.py
    """
    p = Path(__file__).parent / "fixtures" / "hello.pdf"
    if not p.exists():
        pytest.skip(f"missing fixture: {p} - run tests/fixtures/_make_hello_pdf.py")
    return p


@pytest.fixture
def empty_pdf(tmp_path):
    """A blank PDF page - pypdf will report no extractable text."""
    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    out = tmp_path / "blank.pdf"
    with open(out, "wb") as f:
        w.write(f)
    return out
