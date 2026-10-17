"""Journeys: anonymous funnel events, unlinkable after Withdrawal.

Each Client Account gets a random Journey id at sign-up. Events carry the Journey id, the
event name and the time — plus, for ID scans, per-field booleans — never answers or
Identity details. Withdrawal deletes the Account->Journey link, so what remains cannot be
tied back to anyone. Crisis pauses are never recorded here (daily count only).
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import JourneyEvent, JourneyLink

FUNNEL = ["signed_up", "consent_completed", "intake_completed", "identity_completed", "booked"]
OTHER_EVENTS = {"withdrawn", "ocr_field", "friction", "nps"}
REPEATABLE = {"ocr_field", "friction"}
# Friction signals: where people hit trouble. Crisis and safety check-ins are never recorded.
FRICTION_KINDS = {"long_pause", "upload_problem", "high_stress", "upload_rejected", "llm_fallback"}
OCR_FIELDS = ("legal_name", "date_of_birth", "address")


def start(db: Session, account_id: str) -> None:
    """Create the Journey and record sign-up. Idempotent."""
    if db.get(JourneyLink, account_id) is not None:
        return
    link = JourneyLink(account_id=account_id)
    db.add(link)
    db.flush()
    db.add(JourneyEvent(journey_id=link.journey_id, event="signed_up"))


def record(db: Session, account_id: str, event: str, detail: dict | None = None) -> None:
    """Record an event once per Journey (ocr_field and friction may repeat). No-op without a
    Journey."""
    if event not in FUNNEL and event not in OTHER_EVENTS:
        raise ValueError(f"unknown journey event {event}")
    link = db.get(JourneyLink, account_id)
    if link is None:
        return
    if event == "friction" and (detail or {}).get("kind") not in FRICTION_KINDS:
        raise ValueError(f"unknown friction kind {detail}")
    if event not in REPEATABLE:
        seen = db.scalars(
            select(JourneyEvent.id).where(
                JourneyEvent.journey_id == link.journey_id, JourneyEvent.event == event
            )
        ).first()
        if seen:
            return
    db.add(JourneyEvent(journey_id=link.journey_id, event=event, detail=detail))


def record_ocr_review(db: Session, account_id: str, prefilled: dict, edited: dict) -> None:
    """One event per field: was it pre-filled from the scan, left blank, edited by the Client."""
    for field in OCR_FIELDS:
        was_prefilled = bool(prefilled.get(field))
        record(
            db,
            account_id,
            "ocr_field",
            {
                "field": field,
                "prefilled": was_prefilled,
                "blank": not was_prefilled,
                "edited": bool(edited.get(field)) if was_prefilled else False,
            },
        )


def friction(db: Session, account_id: str, step: str, kind: str) -> None:
    record(db, account_id, "friction", {"step": step, "kind": kind})


def has_event(db: Session, account_id: str, event: str) -> bool:
    link = db.get(JourneyLink, account_id)
    if link is None:
        return False
    return (
        db.scalars(
            select(JourneyEvent.id).where(
                JourneyEvent.journey_id == link.journey_id, JourneyEvent.event == event
            )
        ).first()
        is not None
    )


def unlink(db: Session, account_id: str) -> None:
    """At Withdrawal: record the outcome, then cut the only link back to the person."""
    record(db, account_id, "withdrawn")
    db.execute(delete(JourneyLink).where(JourneyLink.account_id == account_id))
