import pytest

from giki.sources.loader import load_source, SourceLoadError


def test_pdf_kind(tiny_pdf):
    s = load_source(tiny_pdf)
    assert s.kind == "pdf"


def test_pdf_pages_concatenated(tiny_pdf):
    s = load_source(tiny_pdf)
    assert "page one alpha" in s.text
    assert "page two beta" in s.text
    assert "page three gamma" in s.text


def test_pdf_page_separators_present(tiny_pdf):
    s = load_source(tiny_pdf)
    assert "<!-- giki:page 1 -->" in s.text
    assert "<!-- giki:page 2 -->" in s.text
    assert "<!-- giki:page 3 -->" in s.text


def test_pdf_pages_in_order(tiny_pdf):
    s = load_source(tiny_pdf)
    i1 = s.text.index("page one alpha")
    i2 = s.text.index("page two beta")
    i3 = s.text.index("page three gamma")
    assert i1 < i2 < i3


def test_pdf_custom_separator(tiny_pdf):
    s = load_source(tiny_pdf, pdf_page_separator="===PAGE {n}===")
    assert "===PAGE 1===" in s.text
    assert "<!-- giki:page 1 -->" not in s.text


def test_scanned_pdf_rejected_by_default(empty_pdf):
    with pytest.raises(SourceLoadError, match="scanned"):
        load_source(empty_pdf)


def test_scanned_pdf_allowed_when_flag_off(empty_pdf):
    s = load_source(empty_pdf, pdf_reject_scanned=False)
    assert s.kind == "pdf"
    # Page separators still present even for blank content
    assert "<!-- giki:page 1 -->" in s.text


def test_pdf_sha256_stable(tiny_pdf):
    """PDF hash is over raw bytes - must match across reads."""
    import hashlib
    raw = tiny_pdf.read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    s = load_source(tiny_pdf)
    assert s.sha256 == expected
