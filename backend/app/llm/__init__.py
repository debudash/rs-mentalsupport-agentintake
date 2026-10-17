"""Builds the configured LLM adapter."""

from functools import lru_cache

from app.config import Settings, get_settings
from app.llm.port import LLMPort
from app.profile import get_profile


def build_llm(settings: Settings) -> LLMPort:
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_adapter import AnthropicLLM

        return AnthropicLLM(settings.anthropic_api_key, settings.llm_model, settings.llm_effort)
    if settings.llm_provider == "openai_compatible":
        from app.llm.openai_adapter import OpenAICompatibleLLM

        return OpenAICompatibleLLM(
            settings.openrouter_api_key, settings.llm_model, settings.llm_base_url
        )
    from app.llm.fake import FakeLLM, HeuristicResponder

    return FakeLLM(HeuristicResponder(get_profile()), delay_ms=settings.fake_llm_delay_ms)


class DebugLoggingLLM:
    """Development only: appends full prompts and responses to a git-ignored local file."""

    def __init__(self, inner: LLMPort, path: str = "llm_debug.log"):
        self._inner, self._path = inner, path
        self.provider, self.model = inner.provider, inner.model

    def complete(self, system, messages, schema, schema_name, timeout):
        import json

        result, error = None, None
        try:
            result = self._inner.complete(system, messages, schema, schema_name, timeout)
            return result
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"system": system,
                                     "messages": [m.__dict__ for m in messages],
                                     "result": result, "error": error}) + "\n")

    def ping(self) -> bool:
        return self._inner.ping()


@lru_cache
def get_llm() -> LLMPort:
    settings = get_settings()
    llm = build_llm(settings)
    if settings.llm_debug_log:
        if settings.app_env != "development":
            raise RuntimeError("LLM_DEBUG_LOG is only allowed when APP_ENV=development")
        llm = DebugLoggingLLM(llm)
    return llm
