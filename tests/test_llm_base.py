import pytest

from giki.llm.base import LLMAdapter, LLMError, LLMResponse, Message


class TestMessage:
    def test_valid_roles(self):
        for role in ("system", "user", "assistant"):
            m = Message(role=role, content="hi")
            assert m.role == role
            assert m.content == "hi"

    def test_rejects_bad_role(self):
        with pytest.raises(ValueError, match="role"):
            Message(role="bogus", content="x")

    def test_empty_content_ok(self):
        # Empty content is a corner case but shouldn't crash the constructor
        m = Message(role="user", content="")
        assert m.content == ""


class TestLLMResponse:
    def test_all_fields(self):
        r = LLMResponse(
            text="hello",
            raw={"id": "x"},
            usage={"in": 1, "out": 2},
            finish_reason="stop",
        )
        assert r.text == "hello"
        assert r.raw == {"id": "x"}
        assert r.usage == {"in": 1, "out": 2}
        assert r.finish_reason == "stop"

    def test_optional_fields_default(self):
        r = LLMResponse(text="hi")
        assert r.text == "hi"
        assert r.raw == {}
        assert r.usage is None
        assert r.finish_reason is None


class TestLLMError:
    def test_default_not_retryable(self):
        e = LLMError("boom")
        assert e.retryable is False
        assert e.status is None
        assert str(e) == "boom"

    def test_retryable_flag(self):
        e = LLMError("transient", retryable=True)
        assert e.retryable is True

    def test_with_status(self):
        e = LLMError("bad request", retryable=False, status=400)
        assert e.status == 400

    def test_is_exception(self):
        assert issubclass(LLMError, Exception)


class TestLLMAdapter:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            LLMAdapter()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        class Fake(LLMAdapter):
            provider = "fake"

            def __init__(self, model: str = "fake-m"):
                self.name = f"fake:{model}"
                self.model = model

            def chat(self, messages, *, temperature=0.0, max_tokens=4096):
                return LLMResponse(text="fake", finish_reason="stop")

        f = Fake()
        r = f.chat([Message(role="user", content="hi")])
        assert r.text == "fake"
        assert f.provider == "fake"
        assert f.model == "fake-m"
        assert f.name == "fake:fake-m"

    def test_subclass_without_chat_still_abstract(self):
        class Incomplete(LLMAdapter):
            provider = "x"

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]
