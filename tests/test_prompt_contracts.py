"""Contract tests: prompt templates render with the exact vars the orchestrator passes."""

from giki.llm.prompts import PromptTemplate


def test_analyze_template_renders():
    t = PromptTemplate.from_package("analyze.md")
    result = t.render(
        source_kind="markdown",
        source_path="sources/x.md",
        chunk_index=1,
        chunk_total=3,
        source_excerpt="Some content.",
        index_summary="(none)",
    )
    assert "kebab-case-slug" in result
    assert "sources/x.md" in result
    assert "1/3" in result
    assert "Some content." in result


def test_synthesize_template_renders_create():
    t = PromptTemplate.from_package("synthesize.md")
    result = t.render(
        mode_block="Write the wiki page body for a new concept.",
        slug="observer",
        title="Observer Pattern",
        source_path="sources/x.md",
        source_excerpt="Content.",
        hints_block="- describe roles",
        aliases_block="Observer",
    )
    assert "Observer Pattern" in result
    assert "describe roles" in result


def test_synthesize_template_renders_update():
    t = PromptTemplate.from_package("synthesize.md")
    mode = (
        "Rewrite the existing wiki page incorporating new material.\n\n"
        "Existing body:\n---\n# Old\n\nOld content.\n---"
    )
    result = t.render(
        mode_block=mode,
        slug="x",
        title="X",
        source_path="s.md",
        source_excerpt="new content",
        hints_block="- (none)",
        aliases_block="(none)",
    )
    assert "Existing body:" in result
    assert "Old content." in result


def test_crosslink_template_renders():
    t = PromptTemplate.from_package("crosslink.md")
    result = t.render(
        slug="topic",
        title="Topic",
        body="Body text about observers.",
        all_pages_index="- a — A\n- b — B",
    )
    assert "topic" in result and "Topic" in result
    assert "neighbors" in result
