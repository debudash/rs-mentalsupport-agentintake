"""OpenAI-compatible adapter: OpenRouter by default, or local Ollama via LLM_BASE_URL."""

import json
import re

import openai

from app.llm.port import ChatMessage, FailureKind, LLMFailure

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _first_json_object(text: str) -> dict:
    """Some free/local models wrap JSON in prose or code fences; take the first object."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "no json") from None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "not json") from exc
    if not isinstance(data, dict):
        raise LLMFailure(FailureKind.INVALID_OUTPUT, "not an object")
    return data


class OpenAICompatibleLLM:
    def __init__(self, api_key: str, model: str, base_url: str = "", client=None):
        self.model = model
        base_url = base_url or OPENROUTER_BASE_URL
        self.provider = "openrouter" if "openrouter.ai" in base_url else "openai_compatible"
        self._client = client or openai.OpenAI(
            api_key=api_key or "not-needed", base_url=base_url, max_retries=0
        )

    def complete(
        self,
        system: str,
        messages: list[ChatMessage],
        schema: dict,
        schema_name: str,
        timeout: float,
    ) -> dict:
        instruction = (
            "\n\nRespond with only a JSON object matching this JSON schema:\n" + json.dumps(schema)
        )
        try:
            response = self._client.with_options(timeout=timeout).chat.completions.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "system", "content": system + instruction}]
                + [{"role": m.role, "content": m.content} for m in messages],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
            )
        except openai.APITimeoutError as exc:
            raise LLMFailure(FailureKind.TIMEOUT) from exc
        except openai.RateLimitError as exc:
            raise LLMFailure(FailureKind.RATE_LIMITED) from exc
        except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            raise LLMFailure(FailureKind.CONFIG, "credentials") from exc
        except openai.APIStatusError as exc:
            kind = FailureKind.SERVER_ERROR if exc.status_code >= 500 else FailureKind.CONFIG
            raise LLMFailure(kind, str(exc.status_code)) from exc
        except openai.APIConnectionError as exc:
            raise LLMFailure(FailureKind.UNREACHABLE) from exc

        if not response.choices:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "no choices")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "truncated")
        return _first_json_object(choice.message.content or "")

    def ping(self) -> bool:
        try:
            self._client.with_options(timeout=3.0).models.list()
            return True
        except Exception:  # noqa: BLE001 - health check reports reachability only
            return False
