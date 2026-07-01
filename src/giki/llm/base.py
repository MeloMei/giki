"""Abstract adapter, message, response, and error types for LLM calls."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant"]
_VALID_ROLES = {"system", "user", "assistant"}


@dataclass
class Message:
    role: Role
    content: str

    def __post_init__(self):
        if self.role not in _VALID_ROLES:
            raise ValueError(
                f"Message.role must be one of {sorted(_VALID_ROLES)}, got {self.role!r}"
            )


@dataclass
class LLMResponse:
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int] | None = None
    finish_reason: str | None = None


class LLMError(Exception):
    """Base error type for LLM adapters. Carries retryable and status."""

    def __init__(
        self,
        msg: str,
        *,
        retryable: bool = False,
        status: int | None = None,
    ):
        super().__init__(msg)
        self.retryable = retryable
        self.status = status


class LLMAdapter(ABC):
    """Abstract adapter for a single (provider, model, endpoint) tuple.

    Subclasses set class attribute `provider` and instance attributes
    `name` and `model` in their `__init__`.
    """

    name: str
    provider: str
    model: str

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send messages, return response. Raise LLMError on failure."""
