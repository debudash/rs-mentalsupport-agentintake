"""Dashboard queries: aggregate, identity-free panels for Operators.

Layer 1 (observability): Performance, LLM health, AI quality.
Counts below SUPPRESS_BELOW are shown as "<5" so no individual can be singled out.
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyCounter, EvalReport, TimingRecord

SUPPRESS_BELOW = 5
TARGETS_MS = {"chat": 3000, "ocr": 8000, "booking": 1000}
ENDPOINT_GROUP = {
    "POST /api/intake/messages": "chat",
    "POST /api/identity/scan": "ocr",
    "POST /api/bookings": "booking",
}
MAX_RECORDS = 20000


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo), 1)


def suppress(count: int) -> int | str:
    return count if count == 0 or count >= SUPPRESS_BELOW else f"<{SUPPRESS_BELOW}"


def dashboard(db: Session, window_hours: int = 24, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=window_hours)
    records = db.scalars(
        select(TimingRecord)
        .where(TimingRecord.at >= since)
        .order_by(TimingRecord.at.desc())
        .limit(MAX_RECORDS)
    ).all()

    by_group: dict[str, list[float]] = defaultdict(list)
    by_endpoint: dict[str, list[float]] = defaultdict(list)
    errors_5xx = 0
    for r in records:
        by_endpoint[r.endpoint].append(r.total_ms)
        group = ENDPOINT_GROUP.get(r.endpoint)
        if group:
            by_group[group].append(r.total_ms)
        if r.status_code >= 500:
            errors_5xx += 1

    performance = []
    for group, target in TARGETS_MS.items():
        values = by_group.get(group, [])
        p95 = percentile(values, 95)
        performance.append(
            {
                "name": group,
                "target_p95_ms": target,
                "count": len(values),
                "p50_ms": percentile(values, 50),
                "p95_ms": p95,
                "meets_target": None if p95 is None else p95 < target,
            }
        )
    endpoints = sorted(
        (
            {
                "endpoint": e,
                "count": len(v),
                "p50_ms": percentile(v, 50),
                "p95_ms": percentile(v, 95),
            }
            for e, v in by_endpoint.items()
        ),
        key=lambda x: -x["count"],
    )

    llm_records = [r for r in records if r.endpoint == "POST /api/intake/messages"]
    outcomes = Counter(r.outcome or "unknown" for r in llm_records)
    llm_calls = sum(1 for r in llm_records if r.llm_ms is not None)
    llm_failures = sum(v for k, v in outcomes.items() if k.startswith("llm_failure"))
    providers = Counter(f"{r.provider}/{r.model}" for r in llm_records if r.provider)
    intents = Counter(r.intent for r in llm_records if r.intent)
    llm_latency = [r.llm_ms for r in llm_records if r.llm_ms is not None]

    reports = {}
    for kind in ("ocr", "intent"):
        latest = db.scalars(
            select(EvalReport).where(EvalReport.kind == kind).order_by(EvalReport.created_at.desc())
        ).first()
        if latest:
            reports[kind] = {"created_at": latest.created_at.isoformat(), **latest.summary}

    counters = db.scalars(
        select(DailyCounter).where(DailyCounter.day >= since.date().isoformat())
    ).all()
    totals = Counter()
    for c in counters:
        totals[c.name] += c.count

    return {
        "window_hours": window_hours,
        "generated_at": now.isoformat(),
        "performance": {
            "targets": performance,
            "endpoints": endpoints,
            "requests": len(records),
            "server_errors": errors_5xx,
        },
        "llm_health": {
            "messages": len(llm_records),
            "llm_calls": llm_calls,
            "failures": llm_failures,
            "failure_rate": round(llm_failures / llm_calls, 3) if llm_calls else None,
            "outcomes": dict(outcomes),
            "fallback_to_scripted": outcomes.get("scripted", 0) + llm_failures,
            "output_check_trips": outcomes.get("output_check_tripped", 0),
            "llm_p50_ms": percentile(llm_latency, 50),
            "llm_p95_ms": percentile(llm_latency, 95),
            "providers": dict(providers),
            "intents": {k: suppress(v) for k, v in intents.items()},
        },
        "ai_quality": reports,
        "safety_and_privacy": {
            "crisis_pauses": suppress(totals.get("crisis_pauses", 0)),
            "withdrawals": suppress(totals.get("withdrawals", 0)),
        },
    }
