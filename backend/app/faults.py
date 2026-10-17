"""Fault injection: force the failures the system is built to survive, for demos and drills.

FAULT_INJECT is a comma-separated list of:
- llm_timeout  every LLM call waits the full LLM_TIMEOUT_SECONDS, then times out
- llm_down     every LLM call fails at once (provider unreachable); /health shows the LLM down
- ocr_fail     the OCR engine errors on every photo, so the Client is offered typing
- db_slow      every database query waits FAULT_DB_DELAY_MS first

Each wraps a real dependency at its seam, so everything downstream (fallbacks, supportive
content, telemetry, the dashboard) reacts exactly as it would to the real failure. Refused
when APP_ENV=production. See docs/RELIABILITY.md for what each one should look like.
"""

import time
from collections.abc import Set

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import Settings
from app.llm.port import FailureKind, LLMFailure, LLMPort
from app.ocr.engines import OCREngine

FAULTS = frozenset({"llm_timeout", "llm_down", "ocr_fail", "db_slow"})


def active(settings: Settings) -> frozenset[str]:
    names = frozenset(n.strip() for n in settings.fault_inject.split(",") if n.strip())
    unknown = names - FAULTS
    if unknown:
        raise ValueError(f"Unknown FAULT_INJECT value(s): {', '.join(sorted(unknown))}")
    if names and settings.app_env == "production":
        raise RuntimeError("FAULT_INJECT is refused when APP_ENV=production")
    return names


class _FaultyLLM:
    def __init__(self, inner: LLMPort, timeout: bool):
        self._timeout = timeout
        self.provider, self.model = inner.provider, inner.model

    def complete(self, system, messages, schema, schema_name, timeout):
        if self._timeout:
            time.sleep(timeout)
            raise LLMFailure(FailureKind.TIMEOUT, "injected fault")
        raise LLMFailure(FailureKind.UNREACHABLE, "injected fault")

    def ping(self) -> bool:
        return False


class _FailingEngine:
    def __init__(self, inner: OCREngine):
        self.name = inner.name

    def available(self) -> bool:
        return True

    def read(self, gray):
        raise RuntimeError("injected fault: ocr_fail")


def wrap_llm(llm: LLMPort, faults: Set[str]) -> LLMPort:
    if "llm_down" in faults:
        return _FaultyLLM(llm, timeout=False)
    if "llm_timeout" in faults:
        return _FaultyLLM(llm, timeout=True)
    return llm


def wrap_engine(engine: OCREngine, faults: Set[str]) -> OCREngine:
    return _FailingEngine(engine) if "ocr_fail" in faults else engine


def slow_down(engine: Engine, faults: Set[str], delay_ms: int) -> None:
    if "db_slow" in faults:
        event.listen(engine, "before_cursor_execute", lambda *_: time.sleep(delay_ms / 1000))
