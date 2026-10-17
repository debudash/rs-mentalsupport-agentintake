"""LLM adapters against fake SDK clients, token verification, and dashboard queries."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import anthropic
import httpx2
import openai
import pytest

from app.access import StaticSecretVerifier, Unauthenticated
from app.dashboard import dashboard, percentile, suppress
from app.db.models import DailyCounter, EvalReport, TimingRecord
from app.llm import build_llm
from app.llm.anthropic_adapter import AnthropicLLM
from app.llm.fake import FakeLLM
from app.llm.openai_adapter import OpenAICompatibleLLM, _first_json_object
from app.llm.port import ChatMessage, FailureKind, LLMFailure
from tests.conftest import SECRET, make_token

REQ = httpx2.Request("POST", "https://api.example/v1")


def status_error(module, code):
    return module.APIStatusError("boom", response=httpx2.Response(code, request=REQ), body=None)


class FakeSDK:
    """Mimics client.with_options(...).messages.create / chat.completions.create."""

    def __init__(self, result=None, error=None):
        self.result, self.error, self.kwargs = result, error, None
        self.messages = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.models = SimpleNamespace(retrieve=lambda *_: True, list=lambda: [])

    def with_options(self, **_):
        return self

    def _create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.result


def anthropic_response(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=text)])


def openai_response(text, finish="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=text))]
    )


MSGS = [ChatMessage("user", "hi")]


def test_anthropic_adapter_parses_structured_output():
    sdk = FakeSDK(anthropic_response('{"intent": "provide-details"}'))
    llm = AnthropicLLM("k", "claude-opus-5-5", "low", client=sdk)
    assert llm.complete("sys", MSGS, {"type": "object"}, "t", 5) == {"intent": "provide-details"}
    assert sdk.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert sdk.kwargs["output_config"]["effort"] == "low"
    assert llm.ping()


@pytest.mark.parametrize(
    "error,kind",
    [
        (anthropic.APITimeoutError(request=REQ), FailureKind.TIMEOUT),
        (anthropic.APIConnectionError(request=REQ), FailureKind.UNREACHABLE),
        (status_error(anthropic, 503), FailureKind.SERVER_ERROR),
        (status_error(anthropic, 400), FailureKind.CONFIG),
    ],
)
def test_anthropic_adapter_maps_errors(error, kind):
    llm = AnthropicLLM("k", "m", "low", client=FakeSDK(error=error))
    with pytest.raises(LLMFailure) as err:
        llm.complete("sys", MSGS, {}, "t", 5)
    assert err.value.kind is kind


@pytest.mark.parametrize(
    "response,kind",
    [
        (anthropic_response("", stop="refusal"), FailureKind.REFUSED),
        (anthropic_response('{"a":', stop="max_tokens"), FailureKind.INVALID_OUTPUT),
        (anthropic_response("not json"), FailureKind.INVALID_OUTPUT),
        (anthropic_response("[1, 2]"), FailureKind.INVALID_OUTPUT),
    ],
)
def test_anthropic_adapter_rejects_unusable_responses(response, kind):
    llm = AnthropicLLM("k", "m", "low", client=FakeSDK(response))
    with pytest.raises(LLMFailure) as err:
        llm.complete("sys", MSGS, {}, "t", 5)
    assert err.value.kind is kind


def test_openai_adapter_handles_wrapped_json_and_errors():
    llm = OpenAICompatibleLLM(
        "k", "meta/llama:free", client=FakeSDK(openai_response('Sure! ```{"intent": "x"}```'))
    )
    assert llm.provider == "openrouter"
    assert llm.complete("sys", MSGS, {"type": "object"}, "t", 5) == {"intent": "x"}
    timeout = OpenAICompatibleLLM(
        "k", "m", client=FakeSDK(error=openai.APITimeoutError(request=REQ))
    )
    with pytest.raises(LLMFailure, match="timeout"):
        timeout.complete("sys", MSGS, {}, "t", 5)
    truncated = OpenAICompatibleLLM("k", "m", client=FakeSDK(openai_response("{", finish="length")))
    with pytest.raises(LLMFailure, match="invalid_output"):
        truncated.complete("sys", MSGS, {}, "t", 5)
    server = OpenAICompatibleLLM("k", "m", client=FakeSDK(error=status_error(openai, 502)))
    with pytest.raises(LLMFailure, match="server_error"):
        server.complete("sys", MSGS, {}, "t", 5)


def test_ollama_base_url_is_not_openrouter():
    llm = OpenAICompatibleLLM(
        "", "llama3.2", base_url="http://localhost:11434/v1", client=FakeSDK()
    )
    assert llm.provider == "openai_compatible"


def test_first_json_object_rejects_prose():
    with pytest.raises(LLMFailure):
        _first_json_object("no json at all")


def test_build_llm_selects_adapter():
    from app.config import Settings

    assert build_llm(Settings(llm_provider="fake")).provider == "fake"
    assert (
        build_llm(Settings(llm_provider="anthropic", anthropic_api_key="k")).provider == "anthropic"
    )
    assert (
        build_llm(Settings(llm_provider="openai_compatible", openrouter_api_key="k")).provider
        == "openrouter"
    )


def test_fake_llm_scripting():
    llm = FakeLLM().script({"ok": 1}).fail_next(FailureKind.SERVER_ERROR)
    assert llm.complete("s", MSGS, {}, "t", 1) == {"ok": 1}
    with pytest.raises(LLMFailure):
        llm.complete("s", MSGS, {}, "t", 1)
    with pytest.raises(LLMFailure):  # nothing scripted, no responder
        llm.complete("s", MSGS, {}, "t", 1)


# ---- token verification ----------------------------------------------------------------


def test_verifier_accepts_valid_and_rejects_wrong_audience_or_secret():
    import jwt

    verifier = StaticSecretVerifier(SECRET)
    assert verifier.verify(make_token("abc")) == "abc"
    wrong_aud = jwt.encode({"sub": "abc", "aud": "other"}, SECRET, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        verifier.verify(wrong_aud)
    forged = jwt.encode({"sub": "abc", "aud": "authenticated"}, "x" * 40, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        verifier.verify(forged)
    no_sub = jwt.encode({"aud": "authenticated"}, SECRET, algorithm="HS256")
    with pytest.raises(Unauthenticated):
        verifier.verify(no_sub)


# ---- dashboard -------------------------------------------------------------------------

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def test_percentile_and_suppression():
    assert percentile([], 95) is None
    assert percentile([100, 200, 300, 400], 50) == 250
    assert suppress(0) == 0 and suppress(3) == "<5" and suppress(12) == 12


def test_dashboard_panels(db):
    for i in range(20):
        db.add(
            TimingRecord(
                at=NOW - timedelta(minutes=i),
                endpoint="POST /api/intake/messages",
                status_code=200,
                total_ms=1000 + i * 50,
                llm_ms=800 + i * 40,
                outcome="llm_ok" if i % 5 else "llm_failure:timeout",
                intent="provide-details",
                provider="anthropic",
                model="m",
            )
        )
    db.add(TimingRecord(at=NOW, endpoint="POST /api/bookings", status_code=200, total_ms=120))
    db.add(
        TimingRecord(
            at=NOW - timedelta(days=3),
            endpoint="POST /api/bookings",
            status_code=500,
            total_ms=9999,
        )
    )
    db.add(DailyCounter(day="2026-10-16", name="crisis_pauses", count=2))
    db.add(EvalReport(kind="ocr", summary={"overall_accuracy": 0.93}))
    db.commit()

    panels = dashboard(db, 24, now=NOW)
    chat = next(p for p in panels["performance"]["targets"] if p["name"] == "chat")
    assert chat["count"] == 20 and chat["meets_target"] is True
    booking = next(p for p in panels["performance"]["targets"] if p["name"] == "booking")
    assert booking["count"] == 1 and panels["performance"]["server_errors"] == 0
    assert panels["llm_health"]["failures"] == 4 and panels["llm_health"]["llm_calls"] == 20
    assert panels["llm_health"]["providers"] == {"anthropic/m": 20}
    assert panels["ai_quality"]["ocr"]["overall_accuracy"] == 0.93
    assert panels["safety_and_privacy"]["crisis_pauses"] == "<5"
