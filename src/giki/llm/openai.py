"""OpenAI Chat Completions adapter.

Any OpenAI-compatible endpoint works by overriding `base_url`:
Ollama, vLLM, LM Studio, Azure OpenAI, third-party gateways.
"""

from __future__ import annotations

import httpx

from ._retry import with_retries
from .base import LLMAdapter, LLMError, LLMResponse, Message


class OpenAIAdapter(LLMAdapter):
    provider = "openai"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        max_retries: int = 3,
        timeout_sec: int = 120,
    ):
        self.model = model
        self.name = f"openai:{model}"
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
        self._timeout = timeout_sec
        self.chat = with_retries(max_retries=max_retries)(self._chat)  # type: ignore[method-assign]

    def _chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        url = f"{self.base_url}/chat/completions"
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
                f"openai API {resp.status_code}: {resp.text[:200]}",
                retryable=retryable,
                status=resp.status_code,
            )

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("openai: empty choices in response")
        choice = choices[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        return LLMResponse(
            text=text,
            raw=data,
            usage=data.get("usage"),
            finish_reason=choice.get("finish_reason"),
        )

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send messages to an OpenAI-compatible endpoint. Replaced by decorator in __init__."""
        raise NotImplementedError  # replaced by decorator in __init__
