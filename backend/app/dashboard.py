"""Dashboard queries: aggregate, identity-free panels for Operators.

Layer 1 (observability): Performance, LLM health, AI quality.
Layer 2 (product analytics): Onboarding funnel and OCR corrections, from anonymous Journeys.
Counts below SUPPRESS_BELOW are shown as "<5" so no individual can be singled out.
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyCounter, EvalReport, JourneyEvent, TimingRecord
from app.journeys import FUNNEL, OCR_FIELDS

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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def funnel(db: Session, since: datetime) -> list[dict]:
    """For Journeys that signed up since `since`: how many reached each Step, the drop-off
    from the previous Step, and the median minutes it took. Small counts are suppressed,
    and nothing is derived from a suppressed count."""
    started = select(JourneyEvent.journey_id).where(
        JourneyEvent.event == "signed_up", JourneyEvent.at >= since
    )
    rows = db.execute(
        select(JourneyEvent.journey_id, JourneyEvent.event, JourneyEvent.at).where(
            JourneyEvent.journey_id.in_(started), JourneyEvent.event.in_(FUNNEL)
        )
    ).all()
    times: dict[str, dict[str, datetime]] = defaultdict(dict)
    for journey_id, event, at in rows:
        times[journey_id][event] = _aware(at)

    stages, previous = [], None
    for event in FUNNEL:
        reached = sum(1 for t in times.values() if event in t)
        stage = {
            "event": event,
            "reached": suppress(reached),
            "drop_off_pct": None,
            "median_minutes_from_previous": None,
        }
        if previous is not None and reached >= SUPPRESS_BELOW:
            before = previous["count"]
            if before >= SUPPRESS_BELOW:
                stage["drop_off_pct"] = round(100 * (before - reached) / before, 1)
            gaps = [
                (t[event] - t[previous["event"]]).total_seconds() / 60
                for t in times.values()
                if event in t and previous["event"] in t
            ]
            stage["median_minutes_from_previous"] = percentile(gaps, 50)
        stages.append(stage)
        previous = {"event": event, "count": reached}
    return stages


def ocr_corrections(db: Session, since: datetime) -> list[dict]:
    """Per field: how often the scan pre-filled it, left it blank, and how often Clients
    edited a pre-filled value. Percentages are withheld below SUPPRESS_BELOW reviews."""
    details = db.scalars(
        select(JourneyEvent.detail).where(
            JourneyEvent.event == "ocr_field", JourneyEvent.at >= since
        )
    ).all()
    out = []
    for field in OCR_FIELDS:
        rows = [d for d in details if d and d.get("field") == field]
        n = len(rows)
        prefilled = sum(1 for d in rows if d.get("prefilled"))
        row = {
            "field": field,
            "reviews": suppress(n),
            "prefilled_pct": None,
            "blank_pct": None,
            "edited_pct": None,
        }
        if n >= SUPPRESS_BELOW:
            row["prefilled_pct"] = round(100 * prefilled / n, 1)
            row["blank_pct"] = round(100 * sum(1 for d in rows if d.get("blank")) / n, 1)
            if prefilled >= SUPPRESS_BELOW:
                edited = sum(1 for d in rows if d.get("prefilled") and d.get("edited"))
                row["edited_pct"] = round(100 * edited / prefilled, 1)
        out.append(row)
    return out


def nps(db: Session, since: datetime) -> dict:
    """Net Promoter Score from the post-booking question: % promoters (9-10) minus %
    detractors (0-6). Withheld below SUPPRESS_BELOW responses."""
    scores = [
        d["score"]
        for d in db.scalars(
            select(JourneyEvent.detail).where(JourneyEvent.event == "nps", JourneyEvent.at >= since)
        )
        if d and isinstance(d.get("score"), int)
    ]
    n = len(scores)
    out = {
        "responses": suppress(n),
        "promoters_pct": None,
        "passives_pct": None,
        "detractors_pct": None,
        "nps": None,
    }
    if n >= SUPPRESS_BELOW:
        promoters = sum(1 for s in scores if s >= 9)
        detractors = sum(1 for s in scores if s <= 6)
        out.update(
            responses=n,
            promoters_pct=round(100 * promoters / n, 1),
            passives_pct=round(100 * (n - promoters - detractors) / n, 1),
            detractors_pct=round(100 * detractors / n, 1),
            nps=round(100 * (promoters - detractors) / n),
        )
    return out


def friction_by_step(db: Session, since: datetime) -> list[dict]:
    """Where people hit trouble: friction signals counted by Step and kind."""
    counts: Counter = Counter()
    for d in db.scalars(
        select(JourneyEvent.detail).where(
            JourneyEvent.event == "friction", JourneyEvent.at >= since
        )
    ):
        if d:
            counts[(d.get("step"), d.get("kind"))] += 1
    order = {e.replace("_completed", ""): i for i, e in enumerate(FUNNEL)}
    return [
        {"step": step, "kind": kind, "count": suppress(n)}
        for (step, kind), n in sorted(
            counts.items(), key=lambda kv: (order.get(kv[0][0], 9), -kv[1])
        )
    ]


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
        "funnel": funnel(db, since),
        "ocr_corrections": ocr_corrections(db, since),
        "friction_by_step": friction_by_step(db, since),
        "nps": nps(db, since),
        "safety_and_privacy": {
            "crisis_pauses": suppress(totals.get("crisis_pauses", 0)),
            "withdrawals": suppress(totals.get("withdrawals", 0)),
        },
    }
