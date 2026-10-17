"""LLM port: one generic structured call. Adapters: Anthropic, OpenAI-compatible, Fake.

complete() returns the parsed JSON object the model produced, or raises LLMFailure.
Business validation of that object belongs to the caller.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class FailureKind(StrEnum):
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    UNREACHABLE = "unreachable"
    RATE_LIMITED = "rate_limited"
    REFUSED = "refused"
    INVALID_OUTPUT = "invalid_output"
    CONFIG = "config"


class LLMFailure(Exception):
    def __init__(self, kind: FailureKind, detail: str = ""):
        super().__init__(f"{kind.value}: {detail}" if detail else kind.value)
        self.kind = kind


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMPort(Protocol):
    provider: str
    model: str

    def complete(
        self,
        system: str,
        messages: list[ChatMessage],
        schema: dict,
        schema_name: str,
        timeout: float,
    ) -> dict: ...

    def ping(self) -> bool: ...
