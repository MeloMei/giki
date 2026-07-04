"""Ingest orchestration: source -> LLM analyze -> LLM synthesize -> LLM crosslink -> git commit.

Full end-to-end pipeline (Phases 0-7) plus a top-level ``ingest()`` entry point.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import git
import yaml

from .config import Config
from .git_utils import add_and_commit, checkout_branch, open_repo, ensure_clean_worktree
from .llm import build_client
from .llm.base import LLMAdapter, LLMError, Message
from .llm.prompts import PromptTemplate
from .sources.loader import LoadedSource, load_source
from .sources.state import SourceState
from .utils import extract_json, iso_now, to_slug
from .wiki.index_log import IndexEntry, LogEvent, append_to_index, append_to_log
from .wiki.linker import Linker, apply_related_block
from .wiki.parser import parse_page
from .wiki.store import WikiStore


@dataclass
class SuggestedPage:
    filename: str
    title: str
    action: Literal["create", "update"]
    hints: list[str] = field(default_factory=list)
    source_anchors: list[str] = field(default_factory=list)
    aliases_suggested: list[str] = field(default_factory=list)


@dataclass
class IngestResult:
    source_path: Path
    branch: str | None
    created: list[str]
    updated: list[str]
    failed: list[str]
    commit_sha: str | None
    skipped: bool = False


class Ingester:
    """End-to-end ingest orchestrator.

    Cheap to construct - LLM clients are built lazily by later phases.
    """

    def __init__(self, config: Config):
        self.config = config
        self._state: SourceState | None = None

    # -------- Phase 0: Bootstrap --------

    def bootstrap(self, branch: str | None) -> git.Repo:
        """Open repo, ensure clean, optionally switch to `branch`."""
        repo = open_repo(self.config.root)
        ensure_clean_worktree(repo)
        if branch:
            checkout_branch(repo, branch, create=True)
        return repo

    # -------- Phase 1: Source Loading --------

    @property
    def state(self) -> SourceState:
        if self._state is None:
            self._state = SourceState.load(self.config.root)
        return self._state

    def load_source(self, path: Path) -> tuple[LoadedSource, bool]:
        """Load a source file and report whether it needs re-ingest.

        needs_ingest is True if:
          * The source has never been ingested, OR
          * The source's SHA-256 hash has changed since the last ingest.
        """
        loaded = load_source(
            path,
            pdf_page_separator=self.config.ingest.pdf.page_separator,
            pdf_reject_scanned=self.config.ingest.pdf.reject_scanned,
        )
        needs = self.state.needs_ingest(path, loaded.sha256)
        return loaded, needs

    # -------- Phase 2: Analyze --------

    def analyze(
        self,
        source: LoadedSource,
        *,
        llm_client: LLMAdapter | None = None,
    ) -> list[SuggestedPage]:
        """Split source into chunks, ask LLM for suggested pages, merge results."""
        client = llm_client or build_client(self.config.llm.compile)
        chunks = _chunk_text(
            source.text,
            size=self.config.ingest.chunk_size,
            overlap=self.config.ingest.chunk_overlap,
        )
        if not chunks:
            # Empty source: still make one call so the prompt path runs once.
            chunks = [""]

        store = WikiStore(
            self.config.root,
            slug_pattern=self.config.wiki.enforce_slug_pattern,
            max_slug_length=self.config.wiki.max_slug_length,
        )
        linker = Linker(store)
        index_summary = _build_index_summary(store)

        merged: dict[str, SuggestedPage] = {}
        for i, chunk in enumerate(chunks, start=1):
            page_list = self._analyze_chunk(
                client=client,
                chunk=chunk,
                chunk_i=i,
                chunk_n=len(chunks),
                source_path=str(source.path),
                source_kind=source.kind,
                index_summary=index_summary,
            )
            for raw in page_list:
                _merge_into(merged, raw)

        # Force `update` action on any slug that already exists in the wiki
        # (direct filename or via alias).
        for slug, sp in merged.items():
            resolved = linker.resolve(sp.filename)
            if resolved is not None:
                sp.action = "update"

        return list(merged.values())

    def _analyze_chunk(
        self,
        *,
        client: LLMAdapter,
        chunk: str,
        chunk_i: int,
        chunk_n: int,
        source_path: str,
        source_kind: str,
        index_summary: str,
    ) -> list[dict]:
        prompt = _render_analyze_prompt(
            chunk=chunk, chunk_i=chunk_i, chunk_n=chunk_n,
            source_path=source_path, source_kind=source_kind,
            index_summary=index_summary,
        )
        messages = [Message(role="user", content=prompt)]

        try:
            response = client.chat(messages)
            data = extract_json(response.text)
        except ValueError:
            correction = Message(
                role="system",
                content=(
                    "Your previous response was not valid JSON. "
                    "Return ONLY a JSON object matching the schema, "
                    "no prose, no markdown fences."
                ),
            )
            response = client.chat([correction] + messages)
            try:
                data = extract_json(response.text)
            except ValueError as e:
                raise LLMError(
                    f"analyze: failed to parse JSON after retry: {e}"
                ) from e

        pages = data.get("suggested_pages", []) if isinstance(data, dict) else []
        return list(pages)

    # -------- Phase 3: Interactive Confirmation --------

    def confirm_pages(
        self,
        candidates: list[SuggestedPage],
        *,
        yes: bool,
        dry_run: bool,
        tty: bool,
    ) -> list[SuggestedPage]:
        """Show candidate pages, filter based on user choice or flags."""
        if dry_run:
            self._print_candidates(candidates)
            return []
        if yes or not tty:
            return list(candidates)

        selected: list[SuggestedPage] = []
        for sp in candidates:
            prompt = f"[{sp.action}] {sp.filename} \u2014 {sp.title}   include? [y/N]: "
            try:
                answer = input(prompt)
            except EOFError:
                answer = ""
            if answer.strip().lower() in ("y", "yes"):
                selected.append(sp)
        return selected

    def _print_candidates(self, candidates: list[SuggestedPage]) -> None:
        print(f"Candidate pages ({len(candidates)}):")
        for sp in candidates:
            print(f"  [{sp.action:6s}] {sp.filename} \u2014 {sp.title}")

    # -------- Phase 4: Synthesize --------

    def synthesize(
        self,
        source: LoadedSource,
        page: SuggestedPage,
        *,
        llm_client: LLMAdapter | None = None,
    ) -> tuple[str, bool]:
        """Generate/rewrite a single wiki page.

        Returns (filename, success). LLM failures do NOT raise \u2014 the
        caller records them in the failed list.
        """
        client = llm_client or build_client(self.config.llm.compile)
        store = WikiStore(
            self.config.root,
            slug_pattern=self.config.wiki.enforce_slug_pattern,
            max_slug_length=self.config.wiki.max_slug_length,
        )

        source_excerpt = source.text[: self.config.ingest.synthesize_context]

        try:
            if page.action == "update" and store.exists(page.filename):
                existing_text = store.read(page.filename)
                existing_page = parse_page(existing_text)
                prompt = _render_synthesize_update_prompt(
                    slug=page.filename,
                    title=page.title,
                    existing_body=existing_page.body,
                    source_path=str(source.path),
                    source_excerpt=source_excerpt,
                    hints=page.hints,
                    aliases=page.aliases_suggested,
                )
                new_body = client.chat([Message(role="user", content=prompt)]).text
                content = _wrap_frontmatter_update(
                    existing=existing_page,
                    page=page,
                    body=new_body,
                    source_path=str(source.path),
                )
            else:
                prompt = _render_synthesize_create_prompt(
                    slug=page.filename,
                    title=page.title,
                    source_path=str(source.path),
                    source_excerpt=source_excerpt,
                    hints=page.hints,
                    aliases=page.aliases_suggested,
                )
                new_body = client.chat([Message(role="user", content=prompt)]).text
                content = _wrap_frontmatter_create(
                    page=page,
                    body=new_body,
                    source_path=str(source.path),
                )

            store.write(page.filename, content)
            return page.filename, True
        except LLMError:
            return page.filename, False

    def synthesize_all(
        self,
        source: LoadedSource,
        pages: list[SuggestedPage],
        *,
        llm_client: LLMAdapter | None = None,
    ) -> tuple[list[str], list[str]]:
        """Synthesize every page; collect successes and failures."""
        succeeded: list[str] = []
        failed: list[str] = []
        for sp in pages:
            slug, ok = self.synthesize(source, sp, llm_client=llm_client)
            (succeeded if ok else failed).append(slug)
        return succeeded, failed

    # -------- Phase 5: Crosslink --------

    def crosslink(
        self,
        succeeded_slugs: list[str],
        *,
        llm_client: LLMAdapter | None = None,
    ) -> tuple[list[str], list[str]]:
        """Ask LLM to propose neighbors + inline hints; apply best-effort per page."""
        if not succeeded_slugs:
            return [], []
        client = llm_client or build_client(self.config.llm.compile)
        store = WikiStore(
            self.config.root,
            slug_pattern=self.config.wiki.enforce_slug_pattern,
            max_slug_length=self.config.wiki.max_slug_length,
        )
        linker = Linker(store)

        all_pages_index = _build_full_page_index(store)

        succeeded: list[str] = []
        failed: list[str] = []
        for slug in succeeded_slugs:
            if not store.exists(slug):
                failed.append(slug)
                continue
            existing_page = parse_page(store.read(slug))
            prompt = _render_crosslink_prompt(
                slug=slug,
                title=existing_page.title,
                body=existing_page.body,
                all_pages_index=all_pages_index,
            )
            try:
                response = client.chat([Message(role="user", content=prompt)])
                data = extract_json(response.text)
            except (LLMError, ValueError):
                failed.append(slug)
                continue

            neighbors_raw = data.get("neighbors", []) if isinstance(data, dict) else []
            inline_hints_raw = data.get("inline_hints", []) if isinstance(data, dict) else []

            # Filter neighbors: only include those that resolve, exclude self, dedupe.
            resolved_neighbors: list[str] = []
            for n in neighbors_raw:
                if not isinstance(n, str):
                    continue
                r = linker.resolve(n)
                if r and r != slug and r not in resolved_neighbors:
                    resolved_neighbors.append(r)

            # Apply inline hints to body (only for resolvable targets and whole-word matches).
            new_body = existing_page.body
            for hint in inline_hints_raw:
                if not isinstance(hint, dict):
                    continue
                phrase = str(hint.get("phrase") or "")
                target = str(hint.get("target") or "")
                if not phrase or not target:
                    continue
                if linker.resolve(target) is None:
                    continue
                new_body = _replace_first_whole_word(new_body, phrase, target)

            # Apply Related block.
            new_body = apply_related_block(
                new_body,
                resolved_neighbors,
                min_neighbors=self.config.wiki.related_min_neighbors,
            )

            # Rewrite the page preserving frontmatter.
            store.write(slug, _replace_body(store.read(slug), new_body))
            succeeded.append(slug)

        return succeeded, failed

    # -------- Phase 6: Index & Log & State --------

    def update_index_and_log(
        self,
        source: LoadedSource,
        *,
        created: list[str],
        updated: list[str],
        failed: list[str],
        timestamp_iso: str,
    ) -> None:
        store = WikiStore(
            self.config.root,
            slug_pattern=self.config.wiki.enforce_slug_pattern,
            max_slug_length=self.config.wiki.max_slug_length,
        )
        entries: list[IndexEntry] = []
        for slug in list(created) + list(updated):
            if not store.exists(slug):
                continue
            page = parse_page(store.read(slug))
            entries.append(IndexEntry(slug=slug, title=page.title, tags=list(page.tags)))
        if entries:
            append_to_index(self.config.root / "index.md", entries)

        append_to_log(
            self.config.root / "log.md",
            LogEvent(
                timestamp_iso=timestamp_iso,
                source_path=str(source.path),
                pages_created=list(created),
                pages_updated=list(updated),
                pages_failed=list(failed),
            ),
        )

        # Update source state.
        self.state.mark(source.path, source.sha256, pages=list(created) + list(updated))
        self.state.save()

    # -------- Phase 7: Commit --------

    def commit(
        self,
        repo: git.Repo,
        source: LoadedSource,
        *,
        created: list[str],
        updated: list[str],
        failed: list[str],
    ) -> git.Commit | None:
        succeeded = list(created) + list(updated)
        total = len(succeeded) + len(failed)
        n = len(succeeded)
        msg = f"ingest: {source.path.name} \u2014 {n} of {total} pages"
        if failed:
            msg += f" ({len(failed)} failed)"

        # Compute the prefix from repo working_dir to config.root so that
        # git paths are correct when root is a subdirectory (e.g. kbase/).
        repo_root = Path(repo.working_dir).resolve()
        config_root = self.config.root.resolve()
        try:
            prefix = config_root.relative_to(repo_root)
        except ValueError:
            prefix = Path()

        paths: list[str] = []
        for rel in ("wiki", "index.md", "log.md", ".giki-state"):
            candidate = self.config.root / rel
            if candidate.exists():
                paths.append(str(prefix / rel))

        if not paths:
            return None
        try:
            return add_and_commit(repo, paths, msg)
        except Exception:
            return None

    # -------- Top-level ingest --------

    def ingest(
        self,
        source_path: Path,
        *,
        branch: str | None,
        yes: bool,
        dry_run: bool,
        retry_failed: bool = False,
        llm_client: LLMAdapter | None = None,
    ) -> IngestResult:
        """End-to-end ingest of one source file."""
        source_path = Path(source_path)

        # Open repo first.
        repo = open_repo(self.config.root)

        # Now check worktree cleanliness (sources/ is exempt in git_utils).
        ensure_clean_worktree(repo)
        if branch:
            checkout_branch(repo, branch, create=True)

        # Phase 1
        loaded, needs = self.load_source(source_path)
        if not needs and not retry_failed:
            return IngestResult(
                source_path=source_path,
                branch=branch,
                created=[], updated=[], failed=[],
                commit_sha=None,
                skipped=True,
            )

        # Phase 2
        candidates = self.analyze(loaded, llm_client=llm_client)

        # Phase 3
        selected = self.confirm_pages(
            candidates,
            yes=yes,
            dry_run=dry_run,
            tty=sys.stdin.isatty(),
        )
        if dry_run or not selected:
            return IngestResult(
                source_path=source_path,
                branch=branch,
                created=[], updated=[], failed=[],
                commit_sha=None,
                skipped=False,
            )

        # Phase 4
        succeeded, failed_synth = self.synthesize_all(loaded, selected, llm_client=llm_client)

        # Phase 5 (best-effort; failures don't remove the page)
        self.crosslink(succeeded, llm_client=llm_client)

        # Partition into created vs updated based on selected action.
        created_slugs: list[str] = []
        updated_slugs: list[str] = []
        for sp in selected:
            if sp.filename in succeeded:
                if sp.action == "update":
                    updated_slugs.append(sp.filename)
                else:
                    created_slugs.append(sp.filename)

        # Phase 6
        self.update_index_and_log(
            loaded,
            created=created_slugs,
            updated=updated_slugs,
            failed=failed_synth,
            timestamp_iso=iso_now(),
        )

        # Phase 7
        commit = self.commit(
            repo, loaded,
            created=created_slugs, updated=updated_slugs, failed=failed_synth,
        )

        return IngestResult(
            source_path=source_path,
            branch=branch,
            created=created_slugs,
            updated=updated_slugs,
            failed=failed_synth,
            commit_sha=commit.hexsha if commit is not None else None,
            skipped=False,
        )


def _render_analyze_prompt(
    *, chunk: str, chunk_i: int, chunk_n: int,
    source_path: str, source_kind: str, index_summary: str,
) -> str:
    tmpl = PromptTemplate.from_package("analyze.md")
    return tmpl.render(
        source_kind=source_kind,
        source_path=source_path,
        chunk_index=chunk_i,
        chunk_total=chunk_n,
        source_excerpt=chunk,
        index_summary=index_summary or "(none)",
    )


def _build_index_summary(store: WikiStore) -> str:
    lines: list[str] = []
    for slug, page in store.all_pages():
        lines.append(f"- {slug} \u2014 {page.title}")
    return "\n".join(lines)


def _chunk_text(text: str, *, size: int, overlap: int) -> list[str]:
    """Slide-window chunk. Break on paragraph boundaries when possible."""
    if not text:
        return []
    if size <= 0 or len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # Try to break on nearest '\n\n' before `end` (within last 20% of the window)
        if end < len(text):
            window_start = max(start, end - size // 5)
            para_break = text.rfind("\n\n", window_start, end)
            if para_break != -1 and para_break > start:
                end = para_break + 2  # include the newlines
        chunks.append(text[start:end])
        if end >= len(text):
            break
        next_start = end - overlap
        if next_start <= start:
            # Guarantee forward progress if overlap >= size
            next_start = start + 1
        start = next_start
    return chunks


def _merge_into(merged: dict[str, SuggestedPage], raw: dict) -> None:
    """Merge one raw dict into the accumulator, deduping by slug."""
    if not isinstance(raw, dict):
        return
    filename = str(raw.get("filename") or "").strip()
    if not filename:
        return
    try:
        slug = to_slug(filename)
    except ValueError:
        return

    title = str(raw.get("title") or slug)
    action = raw.get("action", "create")
    if action not in ("create", "update"):
        action = "create"
    hints = [str(h) for h in (raw.get("hints") or [])]
    anchors = [str(a) for a in (raw.get("source_anchors") or [])]
    aliases = [str(a) for a in (raw.get("aliases_suggested") or [])]

    if slug in merged:
        sp = merged[slug]
        for h in hints:
            if h not in sp.hints:
                sp.hints.append(h)
        for a in anchors:
            if a not in sp.source_anchors:
                sp.source_anchors.append(a)
        for a in aliases:
            if a not in sp.aliases_suggested:
                sp.aliases_suggested.append(a)
        # Prefer update over create if any chunk marked update
        if action == "update":
            sp.action = "update"
    else:
        merged[slug] = SuggestedPage(
            filename=slug,
            title=title,
            action=action,
            hints=hints,
            source_anchors=anchors,
            aliases_suggested=aliases,
        )


def _render_synthesize_create_prompt(
    *, slug: str, title: str, source_path: str,
    source_excerpt: str, hints: list[str], aliases: list[str],
) -> str:
    tmpl = PromptTemplate.from_package("synthesize.md")
    hints_block = "\n".join(f"- {h}" for h in hints) or "- (none)"
    aliases_block = ", ".join(aliases) or "(none)"
    mode_block = "Write the wiki page body for a new concept."
    return tmpl.render(
        mode_block=mode_block,
        slug=slug,
        title=title,
        source_path=source_path,
        source_excerpt=source_excerpt,
        hints_block=hints_block,
        aliases_block=aliases_block,
    )


def _render_synthesize_update_prompt(
    *, slug: str, title: str, existing_body: str, source_path: str,
    source_excerpt: str, hints: list[str], aliases: list[str],
) -> str:
    tmpl = PromptTemplate.from_package("synthesize.md")
    hints_block = "\n".join(f"- {h}" for h in hints) or "- (none)"
    aliases_block = ", ".join(aliases) or "(none)"
    mode_block = (
        "Rewrite the existing wiki page incorporating new material.\n\n"
        "CRITICAL: Preserve any content NOT covered by the new source. Only rewrite\n"
        "paragraphs that the new source clearly supersedes or expands. Existing\n"
        "[[wikilinks]] should be kept unless clearly obsolete.\n\n"
        "Existing body:\n---\n" + existing_body + "\n---"
    )
    return tmpl.render(
        mode_block=mode_block,
        slug=slug,
        title=title,
        source_path=source_path,
        source_excerpt=source_excerpt,
        hints_block=hints_block,
        aliases_block=aliases_block,
    )


def _wrap_frontmatter_create(
    *, page: SuggestedPage, body: str, source_path: str,
) -> str:
    now = iso_now()
    fm = {
        "title": page.title,
        "aliases": list(page.aliases_suggested),
        "tags": [],
        "created": now,
        "updated": now,
        "sources": [{"path": source_path}],
    }
    return _format_page(fm, body)


def _wrap_frontmatter_update(
    *, existing, page: SuggestedPage, body: str, source_path: str,
) -> str:
    aliases = list(existing.aliases)
    for a in page.aliases_suggested:
        if a not in aliases:
            aliases.append(a)

    sources = list(existing.sources)
    if not any(s.get("path") == source_path for s in sources):
        sources.append({"path": source_path})

    fm = {
        "title": page.title,
        "aliases": aliases,
        "tags": list(existing.tags),
        "created": existing.created,
        "updated": iso_now(),
        "sources": sources,
    }
    return _format_page(fm, body)


def _format_page(frontmatter: dict, body: str) -> str:
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip()
    body = body.strip() + "\n"
    return f"---\n{fm_yaml}\n---\n\n{body}"


def _build_full_page_index(store: WikiStore) -> str:
    """One line per page: 'slug - Title - aliases: A, B'."""
    lines: list[str] = []
    for slug, page in store.all_pages():
        aliases = ", ".join(page.aliases) if page.aliases else "(none)"
        lines.append(f"- {slug} \u2014 {page.title} \u2014 aliases: {aliases}")
    return "\n".join(lines) or "(no pages yet)"


def _render_crosslink_prompt(
    *, slug: str, title: str, body: str, all_pages_index: str,
) -> str:
    tmpl = PromptTemplate.from_package("crosslink.md")
    return tmpl.render(
        slug=slug,
        title=title,
        body=body,
        all_pages_index=all_pages_index,
    )


def _replace_first_whole_word(text: str, phrase: str, target: str) -> str:
    """Replace the first whole-word occurrence of `phrase` with `[[target|phrase]]`.

    If the phrase is empty or not found, return `text` unchanged.
    """
    if not phrase.strip():
        return text
    pattern = r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])"
    replacement = f"[[{target}|{phrase}]]"
    return re.sub(pattern, replacement, text, count=1)


_FRONTMATTER_SPLIT_RE = re.compile(r"\A(---\n.*?\n---\n)(.*)\Z", re.DOTALL)


def _replace_body(page_text: str, new_body: str) -> str:
    """Replace body (post-frontmatter) of a page file with `new_body`."""
    m = _FRONTMATTER_SPLIT_RE.match(page_text)
    if not m:
        return new_body  # No frontmatter: just return the new body.
    fm_block = m.group(1)
    return fm_block + "\n" + new_body.strip() + "\n"
