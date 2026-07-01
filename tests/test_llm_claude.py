import json

import httpx
import pytest
import respx

from giki.llm.base import LLMError, Message
from giki.llm.claude import ClaudeAdapter


ADAPTER_KWARGS = dict(
    model="claude-sonnet-4-5-20250929",
    base_url="https://api.anthropic.com",
    api_key="sk-test",
    max_retries=0,
    timeout_sec=5,
)


@respx.mock
def test_chat_success():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [{"type": "text", "text": "hello"}],
                "usage": {"input_tokens": 5, "output_tokens": 2},
                "stop_reason": "end_turn",
            },
        )
    )
    adapter = ClaudeAdapter(**ADAPTER_KWARGS)
    r = adapter.chat([Message(role="user", content="hi")])
    assert r.text == "hello"
    assert r.usage == {"input_tokens": 5, "output_tokens": 2}
    assert r.finish_reason == "end_turn"


@respx.mock
def test_system_message_extracted_into_system_field():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
            },
        )
    )
    adapter = ClaudeAdapter(**ADAPTER_KWARGS)
    adapter.chat([
        Message(role="system", content="you are terse"),
        Message(role="user", content="hi"),
    ])
    body = json.loads(route.calls.last.request.content.decode())
    assert body["system"] == "you are terse"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["model"] == ADAPTER_KWARGS["model"]


@respx.mock
def test_multiple_system_messages_joined():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"},
        )
    )
    ClaudeAdapter(**ADAPTER_KWARGS).chat([
        Message(role="system", content="s1"),
        Message(role="system", content="s2"),
        Message(role="user", content="hi"),
    ])
    body = json.loads(route.calls.last.request.content.decode())
    assert body["system"] == "s1\n\ns2"


@respx.mock
def test_headers_sent_correctly():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"},
        )
    )
    ClaudeAdapter(**ADAPTER_KWARGS).chat([Message(role="user", content="hi")])
    headers = route.calls.last.request.headers
    assert headers["x-api-key"] == "sk-test"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "application/json" in headers["content-type"]


@respx.mock
def test_429_is_retryable():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(429, json={"error": {"message": "rate"}})
    )
    with pytest.raises(LLMError) as exc:
        ClaudeAdapter(**ADAPTER_KWARGS).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is True
    assert exc.value.status == 429


@respx.mock
def test_401_not_retryable():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(401, json={"error": {"message": "no key"}})
    )
    with pytest.raises(LLMError) as exc:
        ClaudeAdapter(**ADAPTER_KWARGS).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is False
    assert exc.value.status == 401


@respx.mock
def test_500_is_retryable():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom"}})
    )
    with pytest.raises(LLMError) as exc:
        ClaudeAdapter(**ADAPTER_KWARGS).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is True


@respx.mock
def test_400_not_retryable():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(400, json={"error": {"message": "bad req"}})
    )
    with pytest.raises(LLMError) as exc:
        ClaudeAdapter(**ADAPTER_KWARGS).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is False


@respx.mock
def test_custom_base_url():
    respx.post("https://theta.example.com/anthropic/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "gateway"}], "stop_reason": "end_turn"},
        )
    )
    adapter = ClaudeAdapter(
        model="c", base_url="https://theta.example.com/anthropic",
        api_key="k", max_retries=0, timeout_sec=5,
    )
    r = adapter.chat([Message(role="user", content="hi")])
    assert r.text == "gateway"


@respx.mock
def test_multiple_content_blocks_concatenated():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [
                    {"type": "text", "text": "part1 "},
                    {"type": "text", "text": "part2"},
                ],
                "stop_reason": "end_turn",
            },
        )
    )
    r = ClaudeAdapter(**ADAPTER_KWARGS).chat([Message(role="user", content="hi")])
    assert r.text == "part1 part2"


def test_provider_and_name_set():
    adapter = ClaudeAdapter(**ADAPTER_KWARGS)
    assert adapter.provider == "claude"
    assert adapter.model == "claude-sonnet-4-5-20250929"
    assert "claude" in adapter.name and adapter.model in adapter.name


@respx.mock
def test_network_error_is_retryable():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    with pytest.raises(LLMError) as exc:
        ClaudeAdapter(**ADAPTER_KWARGS).chat([Message(role="user", content="hi")])
    assert exc.value.retryable is True
