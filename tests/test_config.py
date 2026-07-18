import pytest
import yaml
from pathlib import Path

from giki.config import (
    Config,
    LLMEndpoint,
    load_config,
    ConfigError,
)


VALID_YAML = """
llm:
  compile:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
  review:
    provider: claude
    model: claude-sonnet-4-5-20250929
    base_url: https://api.anthropic.com
    api_key_env: ANTHROPIC_API_KEY
"""


def _write_config(tmp_path: Path, body: str) -> Path:
    d = tmp_path / ".giki"
    d.mkdir()
    (d / "config.yaml").write_text(body, encoding="utf-8")
    return tmp_path


class TestLoadConfig:
    def test_minimal_valid(self, tmp_path):
        root = _write_config(tmp_path, VALID_YAML)
        cfg = load_config(root)
        assert cfg.llm.compile.provider == "claude"
        assert cfg.llm.review.model == "claude-sonnet-4-5-20250929"
        assert cfg.llm.compile.api_key_env == "ANTHROPIC_API_KEY"

    def test_defaults_applied(self, tmp_path):
        root = _write_config(tmp_path, VALID_YAML)
        cfg = load_config(root)
        # LLMEndpoint defaults
        assert cfg.llm.compile.max_retries == 3
        assert cfg.llm.compile.timeout_sec == 120
        # Ingest defaults
        assert cfg.ingest.chunk_size == 12000
        assert cfg.ingest.chunk_overlap == 500
        assert cfg.ingest.synthesize_context == 6000
        assert cfg.ingest.interactive == "auto"
        assert cfg.ingest.pdf.page_separator == "<!-- giki:page {n} -->"
        assert cfg.ingest.pdf.reject_scanned is True
        # Review defaults
        assert cfg.review.unrelated_edit_threshold == 0.30
        assert cfg.review.severity_blocking == ["blocker"]
        assert cfg.review.pr_comment_collapse is True
        # Wiki defaults
        assert cfg.wiki.enforce_slug_pattern == "^[a-z0-9-]+$"
        assert cfg.wiki.max_slug_length == 80
        assert cfg.wiki.related_min_neighbors == 1

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path)

    def test_missing_llm_section_raises(self, tmp_path):
        _write_config(tmp_path, "ingest:\n  chunk_size: 100\n")
        with pytest.raises(ConfigError, match="llm"):
            load_config(tmp_path)

    def test_missing_compile_section_raises(self, tmp_path):
        body = """
llm:
  review:
    provider: claude
    model: m
    base_url: https://x
    api_key_env: K
"""
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="compile"):
            load_config(tmp_path)

    def test_unknown_field_warns_but_loads(self, tmp_path, capsys):
        body = VALID_YAML + "\nunknown_top_level: 42\n"
        _write_config(tmp_path, body)
        cfg = load_config(tmp_path)
        assert cfg.llm.compile.provider == "claude"
        captured = capsys.readouterr()
        assert "unknown" in captured.err.lower()

    def test_invalid_provider_raises(self, tmp_path):
        body = VALID_YAML.replace("provider: claude", "provider: bogus", 1)
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="provider"):
            load_config(tmp_path)

    def test_override_defaults(self, tmp_path):
        body = VALID_YAML + """
ingest:
  chunk_size: 8000
  interactive: never
review:
  severity_blocking: [blocker, warn]
"""
        _write_config(tmp_path, body)
        cfg = load_config(tmp_path)
        assert cfg.ingest.chunk_size == 8000
        assert cfg.ingest.interactive == "never"
        assert cfg.review.severity_blocking == ["blocker", "warn"]

    def test_severity_blocking_explicit_empty_list_preserved(self, tmp_path):
        """User explicitly setting severity_blocking: [] must not be silently replaced."""
        body = VALID_YAML + "\nreview:\n  severity_blocking: []\n"
        _write_config(tmp_path, body)
        cfg = load_config(tmp_path)
        assert cfg.review.severity_blocking == []

    def test_malformed_yaml_raises(self, tmp_path):
        _write_config(tmp_path, "llm: {not valid yaml: [[[")
        with pytest.raises(ConfigError):
            load_config(tmp_path)

    def test_missing_endpoint_field_raises(self, tmp_path):
        body = """
llm:
  compile:
    provider: claude
    model: m
    # base_url missing
    api_key_env: K
  review:
    provider: claude
    model: m
    base_url: https://x
    api_key_env: K
"""
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="base_url"):
            load_config(tmp_path)

    def test_invalid_interactive_raises(self, tmp_path):
        body = VALID_YAML + "\ningest:\n  interactive: bogus\n"
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="interactive"):
            load_config(tmp_path)


class TestConfigPaths:
    def test_config_paths(self, tmp_path):
        root = _write_config(tmp_path, VALID_YAML)
        cfg = load_config(root)
        assert cfg.root == root.resolve()
        assert cfg.giki_dir == (root / ".giki").resolve()
        assert cfg.state_dir == (root / ".giki-state").resolve()


class TestPricing:
    def test_pricing_defaults_to_empty(self, tmp_path):
        root = _write_config(tmp_path, VALID_YAML)
        cfg = load_config(root)
        assert cfg.pricing == {}

    def test_pricing_section_parsed(self, tmp_path):
        body = VALID_YAML + (
            "\npricing:\n  my-gateway-model: [1.0, 4.0]\n  free-model: [0, 0]\n"
        )
        root = _write_config(tmp_path, body)
        cfg = load_config(root)
        assert cfg.pricing == {
            "my-gateway-model": (1.0, 4.0),
            "free-model": (0.0, 0.0),
        }

    def test_pricing_bad_shape_raises(self, tmp_path):
        body = VALID_YAML + "\npricing:\n  my-model: 1.5\n"
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="pricing.my-model"):
            load_config(tmp_path)

    def test_pricing_non_numeric_raises(self, tmp_path):
        body = VALID_YAML + "\npricing:\n  my-model: [cheap, dear]\n"
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="pricing.my-model"):
            load_config(tmp_path)

    def test_pricing_non_mapping_raises(self, tmp_path):
        body = VALID_YAML + "\npricing: 42\n"
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="pricing"):
            load_config(tmp_path)

    def test_pricing_nan_inf_rejected(self, tmp_path):
        for i, bad in enumerate((".nan", ".inf", "-.inf")):
            sub = tmp_path / f"case{i}"
            sub.mkdir()
            body = VALID_YAML + f"\npricing:\n  my-model: [{bad}, 1.0]\n"
            _write_config(sub, body)
            with pytest.raises(ConfigError, match="pricing.my-model"):
                load_config(sub)

    def test_pricing_negative_rejected(self, tmp_path):
        body = VALID_YAML + "\npricing:\n  my-model: [-1.0, 0]\n"
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="pricing.my-model"):
            load_config(tmp_path)

    def test_pricing_bool_rejected(self, tmp_path):
        body = VALID_YAML + "\npricing:\n  my-model: [yes, 0]\n"
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="pricing.my-model"):
            load_config(tmp_path)

    def test_pricing_empty_prefix_rejected(self, tmp_path):
        body = VALID_YAML + '\npricing:\n  "": [1.0, 2.0]\n'
        _write_config(tmp_path, body)
        with pytest.raises(ConfigError, match="non-empty"):
            load_config(tmp_path)

    def test_pricing_keys_stored_lowercase(self, tmp_path):
        body = VALID_YAML + "\npricing:\n  My-Gateway-Model: [1.0, 4.0]\n"
        root = _write_config(tmp_path, body)
        cfg = load_config(root)
        assert cfg.pricing == {"my-gateway-model": (1.0, 4.0)}
