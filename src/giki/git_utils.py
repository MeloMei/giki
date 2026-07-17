"""GitPython facade for giki operations.

Kept small and focused: open, clean-check, branch, commit. No fancy git
plumbing - orchestrator uses these as building blocks.
"""

from __future__ import annotations

from pathlib import Path

import git


class GitError(Exception):
    """A git operation failed or preconditions were not met."""


def open_repo(root: Path) -> git.Repo:
    """Open the git repo at `root` (searches parent dirs). Raise GitError if not a repo."""
    try:
        return git.Repo(str(Path(root)), search_parent_directories=True)
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        pass
    # Fallback: direct open (may still fail with a clear error).
    try:
        return git.Repo(str(Path(root)))
    except (git.InvalidGitRepositoryError, git.NoSuchPathError) as e:
        raise GitError(f"not a git repo: {root}") from e


def ensure_clean_worktree(repo: git.Repo) -> None:
    """Raise GitError if the worktree has uncommitted changes or unwanted untracked files.

    Files under `.giki-state/` are exempt (regeneratable state).
    """
    if repo.is_dirty(untracked_files=False):
        raise GitError("worktree is dirty (uncommitted modifications)")
    untracked = _relevant_untracked(repo)
    if untracked:
        raise GitError(f"worktree has untracked files: {untracked}")


def _relevant_untracked(repo: git.Repo) -> list[str]:
    """Untracked files, ignoring `.giki-state/*` and `sources/*` at any depth.

    `.giki-state/` contains regeneratable state.
    `sources/` contains user input documents that are expected to exist
    as untracked files before ingest.
    """
    _EXEMPT_PREFIXES = (".giki-state/", ".giki-state\\", "sources/", "sources\\")
    _EXEMPT_INFIXS = ("/.giki-state/", "\\.giki-state\\", "/sources/", "\\sources\\")
    return [
        p for p in repo.untracked_files
        if not (
            any(p.startswith(pre) for pre in _EXEMPT_PREFIXES)
            or any(inf in p for inf in _EXEMPT_INFIXS)
        )
    ]


def checkout_branch(repo: git.Repo, name: str, *, create: bool = True) -> None:
    """Checkout `name`, creating it from HEAD if it does not exist and create=True.

    Refuses if worktree is dirty.
    """
    ensure_clean_worktree(repo)
    heads = {h.name: h for h in repo.heads}
    if name in heads:
        heads[name].checkout()
    else:
        if not create:
            raise GitError(f"branch {name!r} does not exist")
        repo.create_head(name).checkout()


def add_and_commit(
    repo: git.Repo,
    paths: list[Path | str],
    message: str,
    *,
    exclude: list[Path | str] | None = None,
) -> git.Commit:
    """Stage the given paths and commit with the given message. Return the commit.

    ``exclude`` lists repo-relative paths that must stay out of the commit
    even when a staged directory contains them (e.g. local state files not
    covered by an older .gitignore). Excluded paths that were never staged
    (already gitignored) are silently skipped.
    """
    string_paths = [str(p) for p in paths]
    if not string_paths:
        raise GitError("no paths to commit")
    repo.index.add(string_paths)
    if exclude:
        # `git rm --cached` works on unborn HEAD (unlike index.reset) and
        # --ignore-unmatch keeps it silent when the path was never staged.
        repo.git.rm(
            "--cached", "-r", "--quiet", "--ignore-unmatch", "--",
            *[str(p) for p in exclude],
        )
    commit = repo.index.commit(message)
    return commit
