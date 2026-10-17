"""Anthropic adapter: structured output via output_config.format (JSON schema)."""

import json

import anthropic

from app.llm.port import ChatMessage, FailureKind, LLMFailure


class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, api_key: str, model: str, effort: str, client=None):
        self.model = model
        self._effort = effort
        # Retries stay at 0: one slow attempt is better than stacked latency (< 3 s p95).
        self._client = client or anthropic.Anthropic(api_key=api_key or None, max_retries=0)

    def complete(
        self,
        system: str,
        messages: list[ChatMessage],
        schema: dict,
        schema_name: str,
        timeout: float,
    ) -> dict:
        try:
            response = self._client.with_options(timeout=timeout).messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                output_config={
                    "effort": self._effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except anthropic.APITimeoutError as exc:
            raise LLMFailure(FailureKind.TIMEOUT) from exc
        except anthropic.RateLimitError as exc:
            raise LLMFailure(FailureKind.RATE_LIMITED) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise LLMFailure(FailureKind.CONFIG, "credentials") from exc
        except anthropic.APIStatusError as exc:
            kind = FailureKind.SERVER_ERROR if exc.status_code >= 500 else FailureKind.CONFIG
            raise LLMFailure(kind, str(exc.status_code)) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMFailure(FailureKind.UNREACHABLE) from exc

        if response.stop_reason == "refusal":
            raise LLMFailure(FailureKind.REFUSED)
        if response.stop_reason == "max_tokens":
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "truncated")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "not json") from exc
        if not isinstance(data, dict):
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "not an object")
        return data

    def ping(self) -> bool:
        try:
            self._client.with_options(timeout=3.0).models.retrieve(self.model)
            return True
        except Exception:  # noqa: BLE001 - health check reports reachability only
            return False
