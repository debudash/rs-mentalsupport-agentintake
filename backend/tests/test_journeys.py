"""Journeys (dashboard layer 2): anonymous funnel events, unlinkable after Withdrawal."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app import journeys
from app.dashboard import funnel, ocr_corrections
from app.db.models import JourneyEvent, JourneyLink
from tests.conftest import auth
from tests.test_api_flow import ANSWERS, confirm_identity, consent, first_slot, photo


def events_for(db, journey_id):
    return [
        e.event
        for e in db.scalars(
            select(JourneyEvent)
            .where(JourneyEvent.journey_id == journey_id)
            .order_by(JourneyEvent.id)
        )
    ]


# ---- module ----------------------------------------------------------------------------


def test_start_is_idempotent_and_records_sign_up(db):
    journeys.start(db, "acct-1")
    journeys.start(db, "acct-1")
    db.commit()
    link = db.get(JourneyLink, "acct-1")
    assert link.journey_id != "acct-1"
    assert events_for(db, link.journey_id) == ["signed_up"]


def test_funnel_events_recorded_once(db):
    journeys.start(db, "acct-1")
    for _ in range(3):
        journeys.record(db, "acct-1", "consent_completed")
    db.commit()
    assert events_for(db, db.get(JourneyLink, "acct-1").journey_id).count("consent_completed") == 1


def test_unknown_event_is_rejected_and_missing_journey_is_a_no_op(db):
    with pytest.raises(ValueError):
        journeys.record(db, "acct-1", "viewed_answers")
    journeys.record(db, "nobody", "booked")  # no Journey: nothing happens
    db.commit()
    assert db.scalars(select(JourneyEvent)).all() == []


def test_unlink_keeps_events_but_removes_the_way_back(db):
    journeys.start(db, "acct-1")
    journey_id = db.get(JourneyLink, "acct-1").journey_id
    journeys.unlink(db, "acct-1")
    db.commit()
    assert db.get(JourneyLink, "acct-1") is None
    assert events_for(db, journey_id) == ["signed_up", "withdrawn"]


def test_ocr_review_records_booleans_only(db):
    journeys.start(db, "acct-1")
    journeys.record_ocr_review(
        db,
        "acct-1",
        prefilled={"legal_name": True, "date_of_birth": True, "address": False},
        edited={"legal_name": False, "date_of_birth": True, "address": True},
    )
    db.commit()
    details = [
        e.detail for e in db.scalars(select(JourneyEvent).where(JourneyEvent.event == "ocr_field"))
    ]
    by_field = {d["field"]: d for d in details}
    assert by_field["legal_name"] == {
        "field": "legal_name",
        "prefilled": True,
        "blank": False,
        "edited": False,
    }
    assert by_field["date_of_birth"]["edited"] is True
    assert by_field["address"] == {
        "field": "address",
        "prefilled": False,
        "blank": True,
        "edited": False,
    }
    assert all(set(d.values()) <= {True, False, d["field"]} for d in details)


# ---- through the API -------------------------------------------------------------------


def test_onboarding_and_withdrawal_produce_an_unlinkable_funnel(
    app_client, seeded, new_account, db
):
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    for item, value in ANSWERS:
        app_client.post("/api/intake/messages", json={"item": item, "value": value}, headers=h)
    app_client.post(
        "/api/identity/scan", headers=h, files={"file": ("id.jpg", photo(), "image/jpeg")}
    )
    app_client.post(
        "/api/identity/confirm",
        headers=h,
        json={
            "legal_name": "Jane Q Doe",
            "date_of_birth": "1990-03-14",
            "address": "123 Main St, Springfield, RS 12345",
            "source": "scan",
            "prefilled": {"legal_name": True, "date_of_birth": True, "address": True},
            "edited": {"legal_name": False, "date_of_birth": False, "address": True},
        },
    )
    slot = first_slot(app_client, h)
    app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=h)
    app_client.post("/api/bookings", json={"slot_id": first_slot(app_client, h)["id"]}, headers=h)

    db.expire_all()
    journey_id = db.get(JourneyLink, account).journey_id
    assert [e for e in events_for(db, journey_id) if e != "ocr_field"] == journeys.FUNNEL
    assert events_for(db, journey_id).count("ocr_field") == 3

    app_client.post("/api/withdraw", json={"confirm": True}, headers=h)
    db.expire_all()
    assert db.get(JourneyLink, account) is None
    assert events_for(db, journey_id)[-1] == "withdrawn"
    # Nothing in the analytics tables mentions the Account.
    dump = str(db.execute(text("select * from journey_events")).all())
    assert account not in dump and "Jane" not in dump and "Main St" not in dump


def test_manual_identity_records_no_ocr_events(app_client, new_account, db):
    h = auth(new_account())
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    for item, value in ANSWERS:
        app_client.post("/api/intake/messages", json={"item": item, "value": value}, headers=h)
    assert confirm_identity(app_client, h).status_code == 200  # source "scan" in helper...
    db.expire_all()
    # ...but the helper sends no "prefilled" map, so no OCR review is recorded
    assert db.scalars(select(JourneyEvent).where(JourneyEvent.event == "ocr_field")).all() == []


def test_staff_accounts_get_no_journey(app_client, new_account, db):
    from tests.conftest import make_role

    operator = new_account()
    make_role(db, operator, "operator")
    app_client.get("/api/operator/dashboard", headers=auth(operator))
    db.expire_all()
    assert db.get(JourneyLink, operator) is None


# ---- dashboard -------------------------------------------------------------------------

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def add_journey(db, events, start=NOW - timedelta(hours=2), gap_minutes=3):
    jid = f"j-{len(db.scalars(select(JourneyEvent)).all())}-{events[-1]}-{start.minute}"
    for i, event in enumerate(events):
        db.add(
            JourneyEvent(journey_id=jid, event=event, at=start + timedelta(minutes=i * gap_minutes))
        )


def test_funnel_counts_drop_off_and_median_minutes(db):
    full = journeys.FUNNEL
    for _ in range(6):
        add_journey(db, full)
    for _ in range(6):
        add_journey(db, full[:3])  # stopped after Intake
    for _ in range(2):
        add_journey(db, full[:1])  # signed up, never consented
    db.commit()
    stages = {s["event"]: s for s in funnel(db, NOW - timedelta(hours=24))}
    assert stages["signed_up"]["reached"] == 14
    assert stages["consent_completed"]["reached"] == 12
    assert stages["intake_completed"]["reached"] == 12
    assert stages["identity_completed"]["reached"] == 6
    assert stages["booked"]["reached"] == 6
    assert stages["identity_completed"]["drop_off_pct"] == 50.0
    assert stages["consent_completed"]["median_minutes_from_previous"] == 3.0
    assert stages["signed_up"]["median_minutes_from_previous"] is None


def test_funnel_suppresses_small_counts_and_ignores_old_journeys(db):
    for _ in range(3):
        add_journey(db, journeys.FUNNEL[:2])
    add_journey(db, journeys.FUNNEL, start=NOW - timedelta(days=5))
    db.commit()
    stages = {s["event"]: s for s in funnel(db, NOW - timedelta(hours=24))}
    assert stages["signed_up"]["reached"] == "<5"
    assert stages["signed_up"]["drop_off_pct"] is None  # never computed from suppressed counts
    assert stages["booked"]["reached"] == 0


def test_ocr_corrections_per_field(db):
    for i in range(10):
        for field in journeys.OCR_FIELDS:
            prefilled = not (field == "address" and i < 2)
            db.add(
                JourneyEvent(
                    journey_id=f"j{i}",
                    event="ocr_field",
                    at=NOW - timedelta(hours=1),
                    detail={
                        "field": field,
                        "prefilled": prefilled,
                        "blank": not prefilled,
                        "edited": field == "date_of_birth" and i < 3,
                    },
                )
            )
    db.commit()
    rows = {r["field"]: r for r in ocr_corrections(db, NOW - timedelta(hours=24))}
    assert rows["legal_name"] == {
        "field": "legal_name",
        "reviews": 10,
        "prefilled_pct": 100.0,
        "blank_pct": 0.0,
        "edited_pct": 0.0,
    }
    assert rows["date_of_birth"]["edited_pct"] == 30.0
    assert rows["address"]["blank_pct"] == 20.0
