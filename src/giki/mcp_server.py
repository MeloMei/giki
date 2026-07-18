"""MCP server scaffold for giki.

Exposes giki CLI commands as MCP tools so platforms like QoderWork,
Claude Code, and Codex can invoke giki via stdio transport.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import git
from mcp.server.fastmcp import FastMCP


def _persist_ledger(usage, state_dir: Path) -> str | None:
    """Append usage records to the ledger. Returns an error string on failure.

    The ledger is an audit aid — a write failure must never fail the tool
    call, so OSError is reported back instead of raised.
    """
    if not usage.records:
        return None
    try:
        usage.append_ledger(state_dir)
    except OSError as e:
        return str(e)
    return None


def _usage_text(usage, ledger_error: str | None = None) -> str:
    """One-line usage summary for MCP text output (empty when no calls)."""
    if not usage.records:
        return ""
    note = f" (ledger write failed: {ledger_error})" if ledger_error else ""
    cost, partial = usage.cost_summary()
    known = any(r.cost_usd is not None for r in usage.records)
    if not known:
        cost_text = "n/a (unknown model pricing)"
    elif partial:
        cost_text = f">= ${cost:.4f}"
    else:
        cost_text = f"${cost:.4f}"
    return (
        f"LLM usage: {len(usage.records)} call(s), "
        f"{usage.total_input:,} tokens in, {usage.total_output:,} tokens out, "
        f"est. cost {cost_text}{note}"
    )


def create_server() -> FastMCP:
    """Create and return a FastMCP server with giki tool definitions."""
    server = FastMCP("giki")

    @server.tool(name="giki_init")
    def giki_init(root: str = ".", with_action: bool = False) -> str:
        """Initialize a new giki wiki repository.

        Creates the standard directory layout (.giki/, sources/, wiki/,
        .giki-state/), copies template scaffolding files, and initializes
        a git repository if one does not already exist.

        Args:
            root: Target directory (default: current directory).
            with_action: If True, also generate a GitHub Actions workflow.

        Returns:
            Summary of created/kept files and next steps.
        """
        from giki.commands.init import _DIRS, _FILE_MAP, _copy_if_absent, _is_git_repo

        try:
            root_path = Path(root).resolve()
            root_path.mkdir(parents=True, exist_ok=True)

            lines: list[str] = []

            # Init git repo if needed
            if not _is_git_repo(root_path):
                git.Repo.init(str(root_path))
                lines.append(f"initialized git repo at {root_path}")

            # Create directories
            for d in _DIRS:
                p = root_path / d
                if not p.exists():
                    p.mkdir(parents=True, exist_ok=True)
                    lines.append(f"created {p}/")
                else:
                    lines.append(f"kept {p}/")

            # Copy scaffolding files
            for template_name, rel_dest in _FILE_MAP:
                dest = root_path / rel_dest
                created = _copy_if_absent(template_name, dest)
                if created:
                    lines.append(f"created {dest}")
                else:
                    lines.append(f"kept {dest}")

            # Optional GitHub Action workflow
            if with_action:
                wf_dest = root_path / ".github" / "workflows" / "giki-review.yml"
                created = _copy_if_absent("action.yml", wf_dest)
                if created:
                    lines.append(f"created {wf_dest}")
                else:
                    lines.append(f"kept {wf_dest}")

            # Next steps
            lines.append("")
            lines.append("Next steps:")
            lines.append("1. Edit .giki/config.yaml (LLM provider, model)")
            lines.append("2. Drop a file into sources/")
            lines.append("3. Run: giki ingest sources/<file> --branch wiki/<topic>")

            return "\n".join(lines)
        except Exception as e:
            return f"error: {e}"

    @server.tool(name="giki_ingest")
    def giki_ingest(
        paths: list[str],
        branch: str | None = None,
        yes: bool = True,
        root: str = ".",
    ) -> str:
        """Ingest source documents into the wiki.

        Compiles each source file into one or more wiki pages using the
        configured LLM pipeline.

        Args:
            paths: List of source file paths to ingest.
            branch: Optional git branch to work on.
            yes: If True, accept all suggested pages without prompting.
            root: Knowledge base root directory (default: current directory).

        Returns:
            Summary with created/updated/failed counts and details per source.
        """
        from giki.config import load_config
        from giki.llm import build_client
        from giki.llm.usage import UsageTracker
        from giki.orchestrator import Ingester

        try:
            root_path = Path(root).resolve()
            config = load_config(root_path)
            ingester = Ingester(config)

            usage = UsageTracker(command="ingest", pricing=config.pricing)
            llm_client = usage.wrap(lambda: build_client(config.llm.compile))

            summaries: list[str] = []
            total_created: list[str] = []
            total_updated: list[str] = []
            total_failed: list[str] = []

            for p in paths:
                source_path = Path(p)
                try:
                    result = ingester.ingest(
                        source_path,
                        branch=branch,
                        yes=yes,
                        dry_run=False,
                        llm_client=llm_client,
                    )
                    if result.skipped:
                        summaries.append(f"[skip] {p} (already ingested, no changes)")
                        continue

                    total_created.extend(result.created)
                    total_updated.extend(result.updated)
                    total_failed.extend(result.failed)

                    sha_note = f" (commit {result.commit_sha[:8]})" if result.commit_sha else ""
                    summaries.append(
                        f"[done] {p}: "
                        f"{len(result.created)} created, "
                        f"{len(result.updated)} updated, "
                        f"{len(result.failed)} failed{sha_note}"
                    )
                except Exception as exc:
                    summaries.append(f"[error] {p}: {exc}")

            header = (
                f"Ingest complete: "
                f"{len(total_created)} created, "
                f"{len(total_updated)} updated, "
                f"{len(total_failed)} failed."
            )
            output = header + "\n" + "\n".join(summaries)
            ledger_error = _persist_ledger(usage, config.state_dir)
            usage_line = _usage_text(usage, ledger_error)
            if usage_line:
                output += "\n" + usage_line
            return output
        except Exception as e:
            return f"error: {e}"

    @server.tool(name="giki_review")
    def giki_review(
        base: str = "main",
        pr: int | None = None,
        json_output: bool = False,
        root: str = ".",
    ) -> str:
        """Review wiki changes with mechanical checks and semantic analysis.

        Runs the two-phase review pipeline: mechanical checks (dead links,
        frontmatter validation, index sync, unrelated edits, typed wikilink
        validation) followed by LLM-based semantic review of each changed
        wiki page.

        Args:
            base: Base branch for diff (default: "main").
            pr: Optional PR number (uses gh CLI).
            json_output: If True, return JSON instead of markdown.
            root: Knowledge base root directory (default: current directory).

        Returns:
            Markdown or JSON review findings.
        """
        from giki.config import ConfigError, load_config
        from giki.diff import classify_changes, get_diff_changes, get_pr_diff_changes, read_file_at_commit
        from giki.llm import build_client
        from giki.llm.usage import UsageTracker
        from giki.review_models import ChangeType, MechanicalFinding, ReviewResult, SemanticFinding
        from giki.rules import parse_rules
        from giki.wiki.parser import parse_page
        from giki.wiki.review_agent import (
            aggregate_verdict,
            check_dead_links,
            check_frontmatter,
            check_index_sync,
            check_typed_links,
            check_unrelated_edits,
            cross_page_analysis,
            review_page_semantic,
            summarize_neighbors,
        )
        from giki.wiki.review_fmt import format_json, format_markdown

        try:
            root_path = Path(root).resolve()

            # Load config
            config = load_config(root_path)

            # Parse wiki-rules.md (optional)
            rules_path = root_path / "wiki-rules.md"
            try:
                rules = parse_rules(rules_path)
            except (FileNotFoundError, ValueError):
                rules = []

            # Get diff changes
            if pr is not None:
                changes = get_pr_diff_changes(pr, repo_root=root_path)
            else:
                changes = get_diff_changes(root_path, base=base)

            classified = classify_changes(changes)
            wiki_changes = classified["wiki"]

            # Run mechanical checks
            all_findings: list[MechanicalFinding | SemanticFinding] = []
            wiki_dir = root_path / "wiki"

            all_findings.extend(check_dead_links(wiki_dir, wiki_changes))
            all_findings.extend(
                check_frontmatter(
                    wiki_dir,
                    wiki_changes,
                    slug_pattern=config.wiki.enforce_slug_pattern,
                    max_slug_length=config.wiki.max_slug_length,
                )
            )

            # Index sync check
            index_path = root_path / "index.md"
            index_text = (
                index_path.read_text(encoding="utf-8") if index_path.exists() else ""
            )
            all_findings.extend(check_index_sync(wiki_changes, index_text))

            # Unrelated edits check
            all_findings.extend(
                check_unrelated_edits(changes, config.review.unrelated_edit_threshold)
            )

            # Typed wikilink validation (parity with the CLI review path)
            all_findings.extend(check_typed_links(wiki_dir, wiki_changes))

            # Semantic review per page
            pages_reviewed = 0
            pages_skipped = 0

            # Build mechanical findings text for prompt
            mech_text = "\n".join(
                f"- [{f.severity}] {f.rule_id}: {f.message}" for f in all_findings
            ) or "(none)"

            # Get base commit for "before" content
            import subprocess
            base_commit_result = subprocess.run(
                ["git", "rev-parse", base],
                capture_output=True,
                text=True,
                cwd=str(root_path),
            )
            base_commit = (
                base_commit_result.stdout.strip()
                if base_commit_result.returncode == 0
                else None
            )

            # Build LLM client for semantic review (usage-tracked)
            usage = UsageTracker(command="review", pricing=config.pricing)
            review_client = usage.wrap(lambda: build_client(config.llm.review))
            changed_pages: list[tuple[str, str]] = []

            for change in wiki_changes:
                slug = change.wiki_slug
                if not slug:
                    continue
                page_path = wiki_dir / f"{slug}.md"
                if not page_path.exists() and change.change_type != ChangeType.DELETED:
                    continue

                # Read "after" content
                after_text = (
                    page_path.read_text(encoding="utf-8") if page_path.exists() else ""
                )

                # Read "before" content
                before_text = ""
                if change.change_type == ChangeType.UPDATED and base_commit:
                    before_text = read_file_at_commit(root_path, change.path, base_commit) or ""

                # Check if hand-written (no sources frontmatter)
                is_hand_written = False
                if after_text:
                    try:
                        page = parse_page(after_text)
                        is_hand_written = page.is_hand_written
                    except Exception:
                        pass

                # Build neighbors context from linked pages
                neighbors = summarize_neighbors(wiki_dir, slug)

                findings, _verdict = review_page_semantic(
                    llm=review_client,
                    rules=rules,
                    page_slug=slug,
                    page_before=before_text,
                    page_after=after_text,
                    neighbors_summary=neighbors,
                    mechanical_findings_text=mech_text,
                    is_hand_written=is_hand_written,
                )
                all_findings.extend(findings)

                if is_hand_written:
                    pages_skipped += 1
                else:
                    pages_reviewed += 1

                # Collect page content for cross-page analysis
                if after_text and not is_hand_written:
                    changed_pages.append((slug, after_text))

            # Cross-page analysis: contradictions and semantic overlap
            if len(changed_pages) >= 2:
                cross_findings = cross_page_analysis(
                    llm=review_client,
                    pages=changed_pages,
                    rules=rules,
                )
                all_findings.extend(cross_findings)

            # Aggregate verdict
            verdict = aggregate_verdict(
                all_findings, severity_blocking=config.review.severity_blocking
            )

            result = ReviewResult(
                verdict=verdict,
                findings=all_findings,
                pages_reviewed=pages_reviewed,
                pages_skipped=pages_skipped,
            )

            # Output (usage ledger is persisted either way)
            ledger_error = _persist_ledger(usage, config.state_dir)
            if json_output:
                data = format_json(result)
                if usage.records:
                    data["usage"] = usage.payload(ledger_error)
                return json.dumps(data, indent=2, ensure_ascii=False)
            else:
                md = format_markdown(result, collapse_nits=config.review.pr_comment_collapse)
                usage_line = _usage_text(usage, ledger_error)
                if usage_line:
                    md += "\n\n---\n" + usage_line
                return md
        except Exception as e:
            return f"error: {e}"

    @server.tool(name="giki_config_show")
    def giki_config_show(root: str = ".") -> str:
        """Show the current giki configuration.

        Args:
            root: Knowledge base root directory (default: current directory).

        Returns:
            JSON string of the loaded configuration.
        """
        from giki.config import load_config

        try:
            root_path = Path(root).resolve()
            config = load_config(root_path)
            data = dataclasses.asdict(config)
            # Convert Path objects to strings for JSON serialization
            for key in ("root", "giki_dir", "state_dir"):
                if key in data:
                    data[key] = str(data[key])
            return json.dumps(data, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"error: {e}"

    return server


def main() -> None:
    """Entry point that runs the MCP server over stdio transport."""
    server = create_server()
    server.run(transport="stdio")
