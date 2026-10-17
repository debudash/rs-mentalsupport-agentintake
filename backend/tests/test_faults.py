"""Fault injection (FAULT_INJECT): each forced failure degrades the way docs/RELIABILITY.md says,
and the switch can never be turned on in production."""

import time

import pytest
from sqlalchemy import text

from app import faults
from app.config import Settings, get_settings
from app.db.session import make_engine
from app.domain.intake import IntakeConductor, IntakeState, Turn
from app.llm.port import FailureKind, LLMFailure
from app.ocr import DocumentReader
from tests.test_ocr import png_bytes


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_no_faults_by_default():
    assert faults.active(settings()) == frozenset()


def test_lists_are_parsed_and_unknown_names_rejected():
    assert faults.active(settings(fault_inject=" llm_down, ocr_fail ")) == {"llm_down", "ocr_fail"}
    with pytest.raises(ValueError, match="llm_typo"):
        faults.active(settings(fault_inject="llm_typo"))


def test_refused_in_production():
    with pytest.raises(RuntimeError, match="production"):
        faults.active(settings(app_env="production", fault_inject="llm_down"))


def test_llm_down_fails_fast_and_health_sees_it(heuristic_llm):
    llm = faults.wrap_llm(heuristic_llm, {"llm_down"})
    with pytest.raises(LLMFailure) as err:
        llm.complete("s", [], {}, "x", timeout=5)
    assert err.value.kind is FailureKind.UNREACHABLE
    assert llm.ping() is False
    assert (llm.provider, llm.model) == (heuristic_llm.provider, heuristic_llm.model)


def test_llm_timeout_waits_the_full_timeout_then_fails(heuristic_llm):
    llm = faults.wrap_llm(heuristic_llm, {"llm_timeout"})
    start = time.perf_counter()
    with pytest.raises(LLMFailure) as err:
        llm.complete("s", [], {}, "x", timeout=0.2)
    assert err.value.kind is FailureKind.TIMEOUT
    assert time.perf_counter() - start >= 0.2


def test_intake_degrades_to_scripted_questions_under_an_injected_llm_fault(profile, heuristic_llm):
    conductor = IntakeConductor(profile, faults.wrap_llm(heuristic_llm, {"llm_down"}), timeout=5)
    state, reply = conductor.respond(IntakeState(), Turn(text="mostly anxiety"))
    assert "offer_retry_assistant" in reply.actions
    state, _ = conductor.respond(state, Turn(text="hard to say"))
    assert state.scripted_mode


def test_ocr_fail_sends_the_client_to_typing(fake_engine):
    reader = DocumentReader(faults.wrap_engine(fake_engine, {"ocr_fail"}), 70, 8 * 1024 * 1024)
    result = reader.read_identity(png_bytes())
    assert result.failure_reason == "engine_error" and not result.any_read
    assert reader.available()


def test_db_slow_adds_latency_to_every_query():
    engine = make_engine("sqlite://")
    faults.slow_down(engine, {"db_slow"}, delay_ms=150)
    with engine.connect() as conn:
        start = time.perf_counter()
        conn.execute(text("select 1"))
    assert time.perf_counter() - start >= 0.15


def test_inactive_faults_change_nothing(heuristic_llm, fake_engine):
    assert faults.wrap_llm(heuristic_llm, set()) is heuristic_llm
    assert faults.wrap_engine(fake_engine, set()) is fake_engine


def test_health_lists_active_faults(app_client, monkeypatch):
    monkeypatch.setenv("FAULT_INJECT", "ocr_fail")
    get_settings.cache_clear()
    try:
        body = app_client.get("/api/health").json()
    finally:
        monkeypatch.delenv("FAULT_INJECT")
        get_settings.cache_clear()
    assert body["faults"] == ["ocr_fail"] and body["status"] == "degraded"
    assert "faults" not in app_client.get("/api/health").json()
