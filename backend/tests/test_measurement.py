"""Making the business metrics measurable: NPS after booking, and per-Step friction signals."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import journeys
from app.dashboard import friction_by_step, nps
from app.db.models import JourneyEvent, JourneyLink
from tests.conftest import auth
from tests.test_api_flow import ANSWERS, confirm_identity, consent, first_slot

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def onboard_and_book(app_client, h):
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    for item, value in ANSWERS:
        app_client.post("/api/intake/messages", json={"item": item, "value": value}, headers=h)
    confirm_identity(app_client, h)
    slot = first_slot(app_client, h)
    assert (
        app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=h).status_code == 200
    )


# ---- NPS -------------------------------------------------------------------------------


def test_nps_is_recorded_once_after_booking(app_client, seeded, new_account, db):
    account = new_account()
    h = auth(account)
    early = app_client.post("/api/feedback", json={"score": 9}, headers=h)
    assert early.status_code in (404, 409)  # not before booking
    onboard_and_book(app_client, h)
    assert app_client.post("/api/feedback", json={"score": 9}, headers=h).status_code == 200
    assert app_client.post("/api/feedback", json={"score": 3}, headers=h).status_code == 409
    db.expire_all()
    jid = db.get(JourneyLink, account).journey_id
    scores = [
        e.detail
        for e in db.scalars(
            select(JourneyEvent).where(JourneyEvent.journey_id == jid, JourneyEvent.event == "nps")
        )
    ]
    assert scores == [{"score": 9}]


def test_nps_score_is_validated(app_client, seeded, new_account):
    h = auth(new_account())
    onboard_and_book(app_client, h)
    for bad in (-1, 11, "ten"):
        assert app_client.post("/api/feedback", json={"score": bad}, headers=h).status_code == 422


def test_nps_maths_and_suppression(db):
    for i, score in enumerate([10, 10, 9, 9, 8, 7, 6, 3, 10, 9]):
        db.add(
            JourneyEvent(
                journey_id=f"j{i}",
                event="nps",
                detail={"score": score},
                at=NOW - timedelta(hours=1),
            )
        )
    db.commit()
    result = nps(db, NOW - timedelta(hours=24))
    # promoters 6 (9-10), passives 2 (7-8), detractors 2 (0-6) -> 60% - 20% = 40
    assert result == {
        "responses": 10,
        "promoters_pct": 60.0,
        "passives_pct": 20.0,
        "detractors_pct": 20.0,
        "nps": 40,
    }
    db.query(JourneyEvent).delete()
    for i in range(3):
        db.add(JourneyEvent(journey_id=f"k{i}", event="nps", detail={"score": 10}, at=NOW))
    db.commit()
    assert nps(db, NOW - timedelta(hours=24))["nps"] is None  # too few to show


# ---- friction by Step ------------------------------------------------------------------


def test_friction_signals_are_recorded_per_step(app_client, seeded, new_account, db):
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    app_client.post(
        "/api/support/events",
        json={"kind": "idle", "step": "intake", "idle_seconds": 60},
        headers=h,
    )
    app_client.post("/api/intake/messages", json={"item": "distress", "value": 5}, headers=h)
    for item, value in ANSWERS:
        app_client.post("/api/intake/messages", json={"item": item, "value": value}, headers=h)
    app_client.post(
        "/api/identity/scan", headers=h, files={"file": ("x.pdf", b"%PDF-1.7", "application/pdf")}
    )
    db.expire_all()
    jid = db.get(JourneyLink, account).journey_id
    friction = [
        e.detail
        for e in db.scalars(
            select(JourneyEvent).where(
                JourneyEvent.journey_id == jid, JourneyEvent.event == "friction"
            )
        )
    ]
    kinds = {(f["step"], f["kind"]) for f in friction}
    assert ("intake", "long_pause") in kinds
    assert ("intake", "high_stress") in kinds
    assert ("identity", "upload_rejected") in kinds
    assert ("identity", "upload_problem") in kinds


def test_llm_fallback_is_a_friction_signal(app_client, new_account, db):
    from app.llm.port import FailureKind

    app_client.llm.fail_next(FailureKind.TIMEOUT)
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    app_client.post("/api/intake/messages", json={"text": "anxiety mostly"}, headers=h)
    db.expire_all()
    jid = db.get(JourneyLink, account).journey_id
    details = [
        e.detail
        for e in db.scalars(
            select(JourneyEvent).where(
                JourneyEvent.journey_id == jid, JourneyEvent.event == "friction"
            )
        )
    ]
    assert {"step": "intake", "kind": "llm_fallback"} in details


def test_crisis_never_appears_on_a_journey(app_client, new_account, db):
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    app_client.post("/api/intake/messages", json={"text": "this form is killing me"}, headers=h)
    app_client.post("/api/intake/messages", json={"text": "I want to end my life"}, headers=h)
    db.expire_all()
    jid = db.get(JourneyLink, account).journey_id
    dump = str(
        [
            (e.event, e.detail)
            for e in db.scalars(select(JourneyEvent).where(JourneyEvent.journey_id == jid))
        ]
    )
    assert "crisis" not in dump and "check_in" not in dump


def test_a_no_to_the_safety_check_in_never_appears_on_a_journey(app_client, new_account, db):
    # ISSUE-018 — found by the whole-codebase review: the high-stress card after a "No" to
    # the Safety check-in was recorded as friction, a safety signal on the Journey.
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    app_client.post("/api/intake/messages", json={"text": "this form is killing me"}, headers=h)
    answered = app_client.post(
        "/api/intake/messages", json={"item": "check_in", "value": "no"}, headers=h
    ).json()
    assert answered["support"]["trigger"] == "high_stress"  # the Client still gets the card
    db.expire_all()
    jid = db.get(JourneyLink, account).journey_id
    friction = db.scalars(
        select(JourneyEvent).where(JourneyEvent.journey_id == jid, JourneyEvent.event == "friction")
    ).all()
    assert friction == []


def test_friction_by_step_table(db):
    rows = (
        [("intake", "long_pause")] * 6
        + [("identity", "upload_rejected")] * 5
        + [("identity", "llm_fallback")] * 2
    )
    for i, (step, kind) in enumerate(rows):
        db.add(
            JourneyEvent(
                journey_id=f"f{i}",
                event="friction",
                detail={"step": step, "kind": kind},
                at=NOW - timedelta(hours=1),
            )
        )
    db.commit()
    table = {
        (r["step"], r["kind"]): r["count"] for r in friction_by_step(db, NOW - timedelta(days=1))
    }
    assert table[("intake", "long_pause")] == 6
    assert table[("identity", "upload_rejected")] == 5
    assert table[("identity", "llm_fallback")] == "<5"


def test_journey_accepts_new_events():
    assert "nps" in journeys.OTHER_EVENTS and "friction" in journeys.OTHER_EVENTS


def test_browser_reported_step_must_be_a_real_step(app_client, new_account, db):
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)
    consent(app_client, h)
    r = app_client.post(
        "/api/support/events",
        headers=h,
        json={"kind": "idle", "step": "jane@example.com", "idle_seconds": 90},
    )
    assert r.status_code == 200 and r.json()["support"] is None
    db.expire_all()
    dump = str([e.detail for e in db.scalars(select(JourneyEvent))])
    assert "jane@example.com" not in dump


def test_long_pause_at_consent_is_visible_before_any_client_record(app_client, new_account, db):
    """A pause on the Consent Step happens before the Client record exists; it must still
    show the reassurance card once and count as friction."""
    # ISSUE-008 — found by comparing the synthetic cohort's script with the dashboard.
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)  # signed up, nothing consented yet
    first = app_client.post(
        "/api/support/events",
        headers=h,
        json={"kind": "idle", "step": "consent", "idle_seconds": 60},
    ).json()
    again = app_client.post(
        "/api/support/events",
        headers=h,
        json={"kind": "idle", "step": "consent", "idle_seconds": 90},
    ).json()
    assert first["support"]["trigger"] == "long_pause"
    assert again["support"] is None
    db.expire_all()
    jid = db.get(JourneyLink, account).journey_id
    details = [
        e.detail
        for e in db.scalars(
            select(JourneyEvent).where(
                JourneyEvent.journey_id == jid, JourneyEvent.event == "friction"
            )
        )
    ]
    assert details == [{"step": "consent", "kind": "long_pause"}]


def test_only_a_long_pause_shows_a_card_before_consent(app_client, new_account, db):
    account = new_account()
    h = auth(account)
    app_client.get("/api/me", headers=h)
    for kind in ("upload_failed", "high_stress"):
        r = app_client.post(
            "/api/support/events", headers=h, json={"kind": kind, "step": "consent"}
        ).json()
        assert r["support"] is None
