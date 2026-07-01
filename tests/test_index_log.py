import pytest
from pathlib import Path

from giki.wiki.index_log import IndexEntry, append_to_index


def test_creates_file_if_missing(tmp_path):
    p = tmp_path / "index.md"
    append_to_index(p, [IndexEntry(slug="a", title="Alpha", tags=["greek"])])
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "# Index" in content
    assert "<!-- giki:index-begin -->" in content
    assert "<!-- giki:index-end -->" in content
    assert "## greek" in content
    assert "- [[a]] \u2014 Alpha" in content


def test_single_entry_categorized(tmp_path):
    p = tmp_path / "index.md"
    append_to_index(p, [IndexEntry(slug="obs", title="Observer", tags=["pattern"])])
    content = p.read_text(encoding="utf-8")
    assert "## pattern" in content
    assert "- [[obs]] \u2014 Observer" in content


def test_uncategorized_bucket(tmp_path):
    p = tmp_path / "index.md"
    append_to_index(p, [IndexEntry(slug="orphan", title="Orphan", tags=[])])
    content = p.read_text(encoding="utf-8")
    assert "## Uncategorized" in content
    assert "- [[orphan]] \u2014 Orphan" in content


def test_alphabetical_categories(tmp_path):
    p = tmp_path / "index.md"
    append_to_index(p, [
        IndexEntry(slug="z", title="Z", tags=["zeta"]),
        IndexEntry(slug="a", title="A", tags=["alpha"]),
    ])
    content = p.read_text(encoding="utf-8")
    ia = content.index("## alpha")
    iz = content.index("## zeta")
    assert ia < iz


def test_alphabetical_within_category(tmp_path):
    p = tmp_path / "index.md"
    append_to_index(p, [
        IndexEntry(slug="c", title="C", tags=["shared"]),
        IndexEntry(slug="a", title="A", tags=["shared"]),
        IndexEntry(slug="b", title="B", tags=["shared"]),
    ])
    content = p.read_text(encoding="utf-8")
    ia = content.index("[[a]]")
    ib = content.index("[[b]]")
    ic = content.index("[[c]]")
    assert ia < ib < ic


def test_multiple_tags_appear_under_each(tmp_path):
    p = tmp_path / "index.md"
    append_to_index(p, [IndexEntry(slug="x", title="X", tags=["t1", "t2"])])
    content = p.read_text(encoding="utf-8")
    assert content.count("[[x]] \u2014 X") == 2


def test_idempotent(tmp_path):
    p = tmp_path / "index.md"
    entry = IndexEntry(slug="a", title="A", tags=["greek"])
    append_to_index(p, [entry])
    append_to_index(p, [entry])
    content = p.read_text(encoding="utf-8")
    assert content.count("[[a]] \u2014 A") == 1


def test_preserves_content_above_marker(tmp_path):
    p = tmp_path / "index.md"
    p.write_text(
        "# Index\n\n"
        "Human-written preamble.\n\n"
        "Custom section here.\n\n"
        "<!-- giki:index-begin -->\n<!-- giki:index-end -->\n",
        encoding="utf-8",
    )
    append_to_index(p, [IndexEntry(slug="a", title="A", tags=["t"])])
    content = p.read_text(encoding="utf-8")
    assert "Human-written preamble." in content
    assert "Custom section here." in content
    assert "[[a]] \u2014 A" in content


def test_appending_second_batch_merges(tmp_path):
    p = tmp_path / "index.md"
    append_to_index(p, [IndexEntry(slug="a", title="A", tags=["t"])])
    append_to_index(p, [IndexEntry(slug="b", title="B", tags=["t"])])
    content = p.read_text(encoding="utf-8")
    assert "[[a]] \u2014 A" in content
    assert "[[b]] \u2014 B" in content
    assert content.count("## t") == 1


def test_empty_entries_list(tmp_path):
    """Calling with an empty list on a fresh file should still create it."""
    p = tmp_path / "index.md"
    append_to_index(p, [])
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "<!-- giki:index-begin -->" in content
