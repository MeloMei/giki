import pytest
from pathlib import Path

from giki.sources.loader import load_source, LoadedSource, SourceLoadError


class TestMarkdown:
    def test_load_md(self, tmp_path):
        p = tmp_path / "note.md"
        p.write_text("# Title\n\nBody.", encoding="utf-8")
        s = load_source(p)
        assert isinstance(s, LoadedSource)
        assert s.kind == "markdown"
        assert s.text == "# Title\n\nBody."
        assert s.path == p

    def test_load_markdown_extension(self, tmp_path):
        p = tmp_path / "note.markdown"
        p.write_text("hello", encoding="utf-8")
        s = load_source(p)
        assert s.kind == "markdown"

    def test_utf8_preserved(self, tmp_path):
        p = tmp_path / "note.md"
        p.write_text("中文 🎉 é", encoding="utf-8")
        s = load_source(p)
        assert "中文" in s.text
        assert "🎉" in s.text


class TestTextLike:
    @pytest.mark.parametrize("ext", [".txt", ".rst", ".org", ".log"])
    def test_text_extensions(self, tmp_path, ext):
        p = tmp_path / f"note{ext}"
        p.write_text("plain content", encoding="utf-8")
        s = load_source(p)
        assert s.kind == "text"
        assert s.text == "plain content"


class TestSha256:
    def test_length_is_64(self, tmp_path):
        p = tmp_path / "a.md"
        p.write_text("x")
        assert len(load_source(p).sha256) == 64

    def test_stable(self, tmp_path):
        p = tmp_path / "a.md"
        p.write_text("same content")
        s1 = load_source(p)
        s2 = load_source(p)
        assert s1.sha256 == s2.sha256

    def test_different_content_different_hash(self, tmp_path):
        (tmp_path / "a.md").write_text("aaa")
        (tmp_path / "b.md").write_text("bbb")
        assert load_source(tmp_path / "a.md").sha256 != load_source(tmp_path / "b.md").sha256

    def test_hash_over_raw_bytes(self, tmp_path):
        """Hash must be computed BEFORE decode — deterministic regardless of encoding round-trips."""
        import hashlib
        p = tmp_path / "a.md"
        raw = "hello 中文".encode("utf-8")
        p.write_bytes(raw)
        expected = hashlib.sha256(raw).hexdigest()
        assert load_source(p).sha256 == expected


class TestErrors:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(SourceLoadError, match="not found"):
            load_source(tmp_path / "does-not-exist.md")

    def test_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "weird.xyz"
        p.write_text("x")
        with pytest.raises(SourceLoadError, match="unsupported"):
            load_source(p)

    def test_no_extension_raises(self, tmp_path):
        p = tmp_path / "noext"
        p.write_text("x")
        with pytest.raises(SourceLoadError, match="unsupported"):
            load_source(p)

    def test_directory_raises(self, tmp_path):
        with pytest.raises(SourceLoadError, match="not a regular file"):
            load_source(tmp_path)
