import pytest

from giki.llm._retry import with_retries
from giki.llm.base import LLMError


class TestWithRetries:
    def test_succeeds_first_try(self):
        calls = {"n": 0}

        @with_retries(max_retries=3, base_delay=0)
        def fn():
            calls["n"] += 1
            return "ok"

        assert fn() == "ok"
        assert calls["n"] == 1

    def test_retries_on_retryable(self):
        calls = {"n": 0}

        @with_retries(max_retries=3, base_delay=0)
        def fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise LLMError("transient", retryable=True)
            return "ok"

        assert fn() == "ok"
        assert calls["n"] == 3

    def test_no_retry_on_non_retryable(self):
        calls = {"n": 0}

        @with_retries(max_retries=3, base_delay=0)
        def fn():
            calls["n"] += 1
            raise LLMError("fatal", retryable=False, status=401)

        with pytest.raises(LLMError) as exc:
            fn()
        assert exc.value.status == 401
        assert calls["n"] == 1

    def test_gives_up_after_max_retries(self):
        calls = {"n": 0}

        @with_retries(max_retries=2, base_delay=0)
        def fn():
            calls["n"] += 1
            raise LLMError("still bad", retryable=True)

        with pytest.raises(LLMError):
            fn()
        # max_retries=2 -> 1 initial + 2 retries = 3 total
        assert calls["n"] == 3

    def test_non_llmerror_not_caught(self):
        """Non-LLMError exceptions propagate immediately without retry."""
        calls = {"n": 0}

        @with_retries(max_retries=3, base_delay=0)
        def fn():
            calls["n"] += 1
            raise ValueError("something else")

        with pytest.raises(ValueError):
            fn()
        assert calls["n"] == 1

    def test_passes_args_and_kwargs(self):
        @with_retries(max_retries=1, base_delay=0)
        def fn(a, b, *, c):
            return a + b + c

        assert fn(1, 2, c=3) == 6

    def test_preserves_metadata(self):
        @with_retries(max_retries=1, base_delay=0)
        def my_function():
            """My docstring."""
            return 1

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."
