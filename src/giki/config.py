"""Configuration loading. .giki/config.yaml -> typed dataclasses."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


class ConfigError(Exception):
    """Configuration file is missing or invalid."""


_VALID_PROVIDERS = {"claude", "openai"}
_VALID_INTERACTIVE = {"auto", "always", "never"}
_KNOWN_TOP_LEVEL = {"llm", "ingest", "review", "wiki"}


@dataclass
class LLMEndpoint:
    provider: Literal["claude", "openai"]
    model: str
    base_url: str
    api_key_env: str
    max_retries: int = 3
    timeout_sec: int = 120


@dataclass
class LLMConfig:
    compile: LLMEndpoint
    review: LLMEndpoint


@dataclass
class PDFConfig:
    page_separator: str = "<!-- giki:page {n} -->"
    reject_scanned: bool = True


@dataclass
class IngestConfig:
    chunk_size: int = 12000
    chunk_overlap: int = 500
    synthesize_context: int = 6000
    interactive: Literal["auto", "always", "never"] = "auto"
    pdf: PDFConfig = field(default_factory=PDFConfig)


@dataclass
class ReviewConfig:
    unrelated_edit_threshold: float = 0.30
    severity_blocking: list[str] = field(default_factory=lambda: ["blocker"])
    pr_comment_collapse: bool = True


@dataclass
class WikiConfig:
    enforce_slug_pattern: str = "^[a-z0-9-]+$"
    max_slug_length: int = 80
    related_min_neighbors: int = 1


@dataclass
class Config:
    llm: LLMConfig
    ingest: IngestConfig
    review: ReviewConfig
    wiki: WikiConfig
    root: Path
    giki_dir: Path
    state_dir: Path


def load_config(root: Path) -> Config:
    """Load .giki/config.yaml from the given repo root."""
    root = Path(root).resolve()
    cfg_path = root / ".giki" / "config.yaml"
    if not cfg_path.exists():
        raise ConfigError(f".giki/config.yaml not found at {cfg_path}")

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"failed to parse {cfg_path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"{cfg_path}: top-level must be a mapping")

    unknown = set(raw) - _KNOWN_TOP_LEVEL
    if unknown:
        print(
            f"warning: unknown top-level config keys ignored: {sorted(unknown)}",
            file=sys.stderr,
        )

    llm_raw = raw.get("llm")
    if not isinstance(llm_raw, dict):
        raise ConfigError("config: 'llm' section is required")
    if "compile" not in llm_raw:
        raise ConfigError("config: 'llm.compile' is required")
    if "review" not in llm_raw:
        raise ConfigError("config: 'llm.review' is required")

    llm = LLMConfig(
        compile=_parse_endpoint(llm_raw["compile"], "llm.compile"),
        review=_parse_endpoint(llm_raw["review"], "llm.review"),
    )

    ingest = _parse_ingest(raw.get("ingest") or {})
    review = _parse_review(raw.get("review") or {})
    wiki = _parse_wiki(raw.get("wiki") or {})

    return Config(
        llm=llm,
        ingest=ingest,
        review=review,
        wiki=wiki,
        root=root,
        giki_dir=(root / ".giki").resolve(),
        state_dir=(root / ".giki-state").resolve(),
    )


def _parse_endpoint(raw, ctx: str) -> LLMEndpoint:
    if not isinstance(raw, dict):
        raise ConfigError(f"config: '{ctx}' must be a mapping")
    required = ("provider", "model", "base_url", "api_key_env")
    for key in required:
        if key not in raw:
            raise ConfigError(f"config: '{ctx}.{key}' is required")
    if raw["provider"] not in _VALID_PROVIDERS:
        raise ConfigError(
            f"config: '{ctx}.provider' must be one of {sorted(_VALID_PROVIDERS)}, "
            f"got {raw['provider']!r}"
        )
    return LLMEndpoint(
        provider=raw["provider"],
        model=str(raw["model"]),
        base_url=str(raw["base_url"]),
        api_key_env=str(raw["api_key_env"]),
        max_retries=int(raw.get("max_retries", 3)),
        timeout_sec=int(raw.get("timeout_sec", 120)),
    )


def _parse_ingest(raw: dict) -> IngestConfig:
    interactive = raw.get("interactive", "auto")
    if interactive not in _VALID_INTERACTIVE:
        raise ConfigError(
            f"config: 'ingest.interactive' must be one of {sorted(_VALID_INTERACTIVE)}, "
            f"got {interactive!r}"
        )
    pdf_raw = raw.get("pdf") or {}
    return IngestConfig(
        chunk_size=int(raw.get("chunk_size", 12000)),
        chunk_overlap=int(raw.get("chunk_overlap", 500)),
        synthesize_context=int(raw.get("synthesize_context", 6000)),
        interactive=interactive,
        pdf=PDFConfig(
            page_separator=str(pdf_raw.get("page_separator", "<!-- giki:page {n} -->")),
            reject_scanned=bool(pdf_raw.get("reject_scanned", True)),
        ),
    )


def _parse_review(raw: dict) -> ReviewConfig:
    return ReviewConfig(
        unrelated_edit_threshold=float(raw.get("unrelated_edit_threshold", 0.30)),
        severity_blocking=list(raw.get("severity_blocking", ["blocker"])),
        pr_comment_collapse=bool(raw.get("pr_comment_collapse", True)),
    )


def _parse_wiki(raw: dict) -> WikiConfig:
    return WikiConfig(
        enforce_slug_pattern=str(raw.get("enforce_slug_pattern", "^[a-z0-9-]+$")),
        max_slug_length=int(raw.get("max_slug_length", 80)),
        related_min_neighbors=int(raw.get("related_min_neighbors", 1)),
    )
