import json
from pathlib import Path

from giki.sources.state import SourceState


class TestNeedsIngest:
    def test_new_source(self, tmp_path):
        state = SourceState.load(tmp_path)
        assert state.needs_ingest(Path("sources/a.md"), "hash1") is True

    def test_unchanged_source(self, tmp_path):
        state = SourceState.load(tmp_path)
        state.mark(Path("sources/a.md"), "hash1", pages=["a", "b"])
        state.save()
        reloaded = SourceState.load(tmp_path)
        assert reloaded.needs_ingest(Path("sources/a.md"), "hash1") is False

    def test_changed_hash(self, tmp_path):
        state = SourceState.load(tmp_path)
        state.mark(Path("sources/a.md"), "hash1", pages=[])
        state.save()
        reloaded = SourceState.load(tmp_path)
        assert reloaded.needs_ingest(Path("sources/a.md"), "hash2") is True


class TestPagesFor:
    def test_get_pages(self, tmp_path):
        state = SourceState.load(tmp_path)
        state.mark(Path("sources/a.md"), "h", pages=["observer-pattern", "event-bus"])
        state.save()
        reloaded = SourceState.load(tmp_path)
        assert reloaded.pages_for(Path("sources/a.md")) == ["observer-pattern", "event-bus"]

    def test_unknown_source_returns_empty(self, tmp_path):
        state = SourceState.load(tmp_path)
        assert state.pages_for(Path("sources/never.md")) == []

    def test_empty_pages_list_preserved(self, tmp_path):
        state = SourceState.load(tmp_path)
        state.mark(Path("sources/a.md"), "h", pages=[])
        state.save()
        reloaded = SourceState.load(tmp_path)
        assert reloaded.pages_for(Path("sources/a.md")) == []


class TestPersistence:
    def test_paths_stored_as_posix(self, tmp_path):
        """Windows uses backslashes; the store must use forward slashes."""
        state = SourceState.load(tmp_path)
        state.mark(Path("sources") / "a.md", "h", pages=[])
        state.save()
        raw = (tmp_path / ".giki-state" / "sources.json").read_text(encoding="utf-8")
        assert "sources/a.md" in raw
        assert "\\\\" not in raw
        assert "sources\a.md" not in raw

    def test_json_is_sorted(self, tmp_path):
        state = SourceState.load(tmp_path)
        state.mark(Path("sources/z.md"), "h", pages=[])
        state.mark(Path("sources/a.md"), "h", pages=[])
        state.mark(Path("sources/m.md"), "h", pages=[])
        state.save()
        raw = (tmp_path / ".giki-state" / "sources.json").read_text(encoding="utf-8")
        i_a = raw.index("sources/a.md")
        i_m = raw.index("sources/m.md")
        i_z = raw.index("sources/z.md")
        assert i_a < i_m < i_z

    def test_creates_state_dir(self, tmp_path):
        assert not (tmp_path / ".giki-state").exists()
        state = SourceState.load(tmp_path)
        state.mark(Path("sources/a.md"), "h", pages=[])
        state.save()
        assert (tmp_path / ".giki-state").is_dir()
        assert (tmp_path / ".giki-state" / "sources.json").is_file()

    def test_load_missing_file(self, tmp_path):
        """Should not error when state file doesn't exist yet."""
        state = SourceState.load(tmp_path)
        assert state.entries == {}

    def test_load_malformed_json_falls_back(self, tmp_path):
        (tmp_path / ".giki-state").mkdir()
        (tmp_path / ".giki-state" / "sources.json").write_text("not { json", encoding="utf-8")
        state = SourceState.load(tmp_path)
        assert state.entries == {}

    def test_load_empty_file(self, tmp_path):
        (tmp_path / ".giki-state").mkdir()
        (tmp_path / ".giki-state" / "sources.json").write_text("", encoding="utf-8")
        state = SourceState.load(tmp_path)
        assert state.entries == {}

    def test_roundtrip_unicode(self, tmp_path):
        """ensure_ascii=False -> Chinese path components should survive round-trip."""
        state = SourceState.load(tmp_path)
        state.mark(Path("sources/中文-note.md"), "h", pages=["页面"])
        state.save()
        reloaded = SourceState.load(tmp_path)
        assert reloaded.pages_for(Path("sources/中文-note.md")) == ["页面"]
