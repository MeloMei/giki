"""Anthropic Claude adapter.

Compatible with any Anthropic-compatible gateway (theta, evomap, etc.)
via the `base_url` override.
"""

from __future__ import annotations

import httpx

from ._retry import with_retries
from .base import LLMAdapter, LLMError, LLMResponse, Message


class ClaudeAdapter(LLMAdapter):
    provider = "claude"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        max_retries: int = 3,
        timeout_sec: int = 120,
        anthropic_version: str = "2023-06-01",
    ):
        self.model = model
        self.name = f"claude:{model}"
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": anthropic_version,
            "content-type": "application/json",
        }
        self._timeout = timeout_sec
        # Wrap _chat with retry using runtime-configured max_retries
        self.chat = with_retries(max_retries=max_retries)(self._chat)  # type: ignore[method-assign]

    def _chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        conv = [m for m in messages if m.role != "system"]
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in conv],
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        url = f"{self.base_url}/v1/messages"
        try:
            resp = httpx.post(
                url, json=payload, headers=self._headers, timeout=self._timeout
            )
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
        ) as e:
            raise LLMError(f"network error: {e}", retryable=True) from e

        if resp.status_code >= 400:
            retryable = resp.status_code in (408, 429) or resp.status_code >= 500
            raise LLMError(
                f"claude API {resp.status_code}: {resp.text[:200]}",
                retryable=retryable,
                status=resp.status_code,
            )

        data = resp.json()
        blocks = data.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return LLMResponse(
            text=text,
            raw=data,
            usage=data.get("usage"),
            finish_reason=data.get("stop_reason"),
        )

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send messages to Claude. Replaced with a retry-wrapped version in __init__."""
        raise NotImplementedError  # replaced by decorator in __init__
