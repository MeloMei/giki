"""LLM adapter layer.

Public API:
- `LLMAdapter`, `Message`, `LLMResponse`, `LLMError` — base types
- `ClaudeAdapter`, `OpenAIAdapter` — concrete adapters
- `build_client(endpoint)` — factory

The factory reads the API key from the environment variable named by
`endpoint.api_key_env`. API keys must never be stored in config files.
"""

from __future__ import annotations

import os

from ..config import LLMEndpoint
from .base import LLMAdapter, LLMError, LLMResponse, Message
from .claude import ClaudeAdapter
from .openai import OpenAIAdapter

__all__ = [
    "LLMAdapter",
    "LLMError",
    "LLMResponse",
    "Message",
    "ClaudeAdapter",
    "OpenAIAdapter",
    "build_client",
]


def build_client(endpoint: LLMEndpoint) -> LLMAdapter:
    """Construct an LLMAdapter from an LLMEndpoint config.

    Reads the API key from the env var named by `endpoint.api_key_env`.
    Raises RuntimeError if the env var is missing or empty.
    """
    key = os.environ.get(endpoint.api_key_env)
    if not key:
        raise RuntimeError(
            f"env var {endpoint.api_key_env!r} is not set (or is empty); "
            f"export it before running giki"
        )
    kwargs = dict(
        model=endpoint.model,
        base_url=endpoint.base_url,
        api_key=key,
        max_retries=endpoint.max_retries,
        timeout_sec=endpoint.timeout_sec,
    )
    if endpoint.provider == "claude":
        return ClaudeAdapter(**kwargs)
    if endpoint.provider == "openai":
        return OpenAIAdapter(**kwargs)
    raise ValueError(f"unknown provider {endpoint.provider!r}")
