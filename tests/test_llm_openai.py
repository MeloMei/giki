import json

import httpx
import pytest
import respx

from giki.llm.base import LLMError, Message
from giki.llm.openai import OpenAIAdapter


KW = dict(
    model="gpt-5o",
    base_url="https://api.openai.com/v1",
    api_key="sk-test",
    max_retries=0,
    timeout_sec=5,
)


@respx.mock
def test_chat_success():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cmpl",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )
    )
    r = OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])
    assert r.text == "hello"
    assert r.finish_reason == "stop"
    assert r.usage == {"prompt_tokens": 5, "completion_tokens": 2}


@respx.mock
def test_system_and_user_forwarded_verbatim():
    """OpenAI natively supports role=system; no special extraction like Claude."""
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )
    )
    OpenAIAdapter(**KW).chat([
        Message(role="system", content="s"),
        Message(role="user", content="u"),
        Message(role="assistant", content="prev"),
    ])
    body = json.loads(route.calls.last.request.content.decode())
    assert body["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "prev"},
    ]
    assert body["model"] == KW["model"]


@respx.mock
def test_authorization_header():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )
    )
    OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])
    assert route.calls.last.request.headers["Authorization"] == "Bearer sk-test"


@respx.mock
def test_429_is_retryable():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate"}})
    )
    with pytest.raises(LLMError) as exc:
        OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is True
    assert exc.value.status == 429


@respx.mock
def test_401_not_retryable():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, json={"error": {"message": "no key"}})
    )
    with pytest.raises(LLMError) as exc:
        OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is False


@respx.mock
def test_500_is_retryable():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom"}})
    )
    with pytest.raises(LLMError) as exc:
        OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is True


@respx.mock
def test_ollama_compatible_base_url():
    """Ollama's OpenAI-compatible endpoint should Just Work with the same adapter."""
    respx.post("http://localhost:11434/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "llama"}, "finish_reason": "stop"}]},
        )
    )
    adapter = OpenAIAdapter(
        model="llama3.1", base_url="http://localhost:11434/v1",
        api_key="ollama", max_retries=0, timeout_sec=5,
    )
    r = adapter.chat([Message(role="user", content="hi")])
    assert r.text == "llama"


@respx.mock
def test_empty_choices_raises():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": []})
    )
    with pytest.raises(LLMError, match="empty"):
        OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])


@respx.mock
def test_missing_content_field_ok():
    """Content field can be None (e.g. tool-call response). Return empty text, don't crash."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": None}, "finish_reason": "tool_calls"}]},
        )
    )
    r = OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])
    assert r.text == ""
    assert r.finish_reason == "tool_calls"


@respx.mock
def test_network_error_is_retryable():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    with pytest.raises(LLMError) as exc:
        OpenAIAdapter(**KW).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is True


def test_provider_and_name_set():
    adapter = OpenAIAdapter(**KW)
    assert adapter.provider == "openai"
    assert adapter.model == "gpt-5o"
    assert "openai" in adapter.name and adapter.model in adapter.name


@respx.mock
def test_temperature_and_max_tokens_passed():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )
    )
    OpenAIAdapter(**KW).chat(
        [Message(role="user", content="hi")], temperature=0.7, max_tokens=100
    )
    body = json.loads(route.calls.last.request.content.decode())
    assert body["temperature"] == 0.7
    assert body["max_tokens"] == 100
