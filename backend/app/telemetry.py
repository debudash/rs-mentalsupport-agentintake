"""Telemetry recorder: PII-free JSON logs and one timing record per request.

Records carry endpoint, stage timings, outcome, intent label, provider and model — never an
Account id, never message text, never Identity details.
"""

import contextvars
import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger("rs_assist")

# Keys that must never reach a log line, whatever a caller passes.
_FORBIDDEN = {
    "text",
    "message",
    "name",
    "legal_name",
    "date_of_birth",
    "dob",
    "address",
    "email",
    "phone",
    "reason",
    "reason_text",
    "answers",
    "body",
    "image",
    "token",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        extra = getattr(record, "fields", {}) or {}
        payload.update({k: v for k, v in extra.items() if k not in _FORBIDDEN})
        if record.exc_info:
            # Exception type only: exception messages can echo user input.
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).handlers[:] = []
        logging.getLogger(noisy).propagate = False


def log(event: str, **fields) -> None:
    logger.info(event, extra={"fields": fields})


@dataclass
class RequestTimings:
    started: float = field(default_factory=time.perf_counter)
    stages: dict[str, float] = field(default_factory=dict)
    outcome: str | None = None
    intent: str | None = None
    provider: str | None = None
    model: str | None = None

    def add(self, stage: str, ms: float) -> None:
        self.stages[stage] = self.stages.get(stage, 0.0) + ms

    def total_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000

    def server_timing_header(self) -> str:
        parts = [f"{k};dur={v:.1f}" for k, v in self.stages.items()]
        parts.append(f"total;dur={self.total_ms():.1f}")
        return ", ".join(parts)


_current: contextvars.ContextVar[RequestTimings | None] = contextvars.ContextVar(
    "request_timings", default=None
)


def begin() -> RequestTimings:
    timings = RequestTimings()
    _current.set(timings)
    return timings


def current() -> RequestTimings | None:
    return _current.get()


@contextmanager
def timed(stage: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        timings = _current.get()
        if timings is not None:
            timings.add(stage, (time.perf_counter() - started) * 1000)


def note(**fields) -> None:
    """Attach outcome / intent / provider / model to the current request's record."""
    timings = _current.get()
    if timings is None:
        return
    for key, value in fields.items():
        if hasattr(timings, key) and value is not None:
            setattr(timings, key, value)
