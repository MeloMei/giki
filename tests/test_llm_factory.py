import os

import pytest

from giki.config import LLMEndpoint
from giki.llm import build_client
from giki.llm.claude import ClaudeAdapter
from giki.llm.openai import OpenAIAdapter


def _endpoint(provider: str = "claude", api_key_env: str = "TEST_KEY") -> LLMEndpoint:
    return LLMEndpoint(
        provider=provider,
        model="m",
        base_url="https://example.com",
        api_key_env=api_key_env,
    )


def test_builds_claude(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "sk-x")
    adapter = build_client(_endpoint("claude"))
    assert isinstance(adapter, ClaudeAdapter)
    assert adapter.provider == "claude"


def test_builds_openai(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "sk-x")
    adapter = build_client(_endpoint("openai"))
    assert isinstance(adapter, OpenAIAdapter)
    assert adapter.provider == "openai"


def test_missing_env_var_raises(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TEST_KEY"):
        build_client(_endpoint("claude"))


def test_empty_env_var_also_raises(monkeypatch):
    """An env var that is set but empty should be treated as missing."""
    monkeypatch.setenv("TEST_KEY", "")
    with pytest.raises(RuntimeError, match="TEST_KEY"):
        build_client(_endpoint("claude"))


def test_endpoint_fields_propagated(monkeypatch):
    monkeypatch.setenv("MY_KEY", "sk-abc")
    ep = LLMEndpoint(
        provider="claude",
        model="claude-3",
        base_url="https://x.example.com",
        api_key_env="MY_KEY",
        max_retries=5,
        timeout_sec=60,
    )
    adapter = build_client(ep)
    assert adapter.model == "claude-3"
    assert adapter.base_url == "https://x.example.com"


def test_module_reexports():
    """Common public names should be importable from `giki.llm` top-level."""
    from giki.llm import (
        LLMAdapter, LLMError, LLMResponse, Message,
        ClaudeAdapter, OpenAIAdapter, build_client,
    )
    assert build_client is not None
