"""API end to end on the Fake adapters: the whole Onboarding, edge cases, privacy, roles."""

import io
import logging
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy import select, text

from app.db.models import (
    AccessLogEntry,
    Account,
    Assessment,
    Booking,
    Clinician,
    ConsentLogEntry,
    IdentityDetails,
    IntakeMessage,
    Slot,
    TimingRecord,
)
from app.ocr.engines import Line
from tests.conftest import auth, make_role, make_token

ANSWERS = [
    ("reason_category", "anxiety"),
    ("reason_text", "Work has been overwhelming since spring"),
    ("duration", "1_6_months"),
    ("distress", "3"),
    ("safety", "no"),
    ("session_format", "either"),
    ("availability", "mornings,afternoons,evenings"),
    ("clinician_gender", "no_preference"),
    ("clinician_language", "no_preference"),
]


def photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (900, 600), "white").save(buf, "JPEG")
    return buf.getvalue()


def consent(client, h, id_scan=True):
    r = client.post(
        "/api/consent",
        json={"onboarding": True, "id_scan": id_scan, "age_confirmed": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    return r


def finish_intake(client, h):
    for item, value in ANSWERS:
        r = client.post("/api/intake/messages", json={"item": item, "value": value}, headers=h)
        assert r.status_code == 200, r.text
    assert r.json()["complete"]


def confirm_identity(client, h, dob="1990-03-14"):
    return client.post(
        "/api/identity/confirm",
        headers=h,
        json={
            "legal_name": "Jane Q Doe",
            "date_of_birth": dob,
            "address": "123 Main St, Springfield, RS 12345",
            "source": "scan",
            "edited": {"legal_name": False, "date_of_birth": True, "address": False},
        },
    )


def to_scheduling(client, h):
    consent(client, h)
    finish_intake(client, h)
    assert confirm_identity(client, h).json()["confirmed"]


def first_slot(client, h):
    r = client.get("/api/slots", params={"tz": "America/New_York", "show_all": True}, headers=h)
    assert r.status_code == 200
    return r.json()["slots"][0]


# ---- the happy path -------------------------------------------------------------------


def test_full_onboarding_end_to_end(app_client, seeded, new_account, db):
    h = auth(new_account())
    me = app_client.get("/api/me", headers=h).json()
    assert me["role"] == "client" and me["onboarding"]["step"] == "consent"

    consent(app_client, h)
    first = app_client.get("/api/intake", headers=h).json()
    assert first["pending_item"] == "reason_category" and first["quick_replies"]
    finish_intake(app_client, h)
    assert app_client.get("/api/me", headers=h).json()["onboarding"]["step"] == "identity"

    scan = app_client.post(
        "/api/identity/scan", headers=h, files={"file": ("id.jpg", photo(), "image/jpeg")}
    ).json()
    assert scan["accepted"] and scan["fields"]["name"] == {"value": "Jane Q Doe", "status": "read"}
    assert confirm_identity(app_client, h).json()["confirmed"]

    slot = first_slot(app_client, h)
    booked = app_client.post(
        "/api/bookings", json={"slot_id": slot["id"], "tz": "America/New_York"}, headers=h
    )
    assert booked.status_code == 200
    body = booked.json()
    assert body["onboarding"]["step"] == "done"
    assert body["booking"]["time_zone"] in ("EDT", "EST")
    ics = app_client.get("/api/bookings/current/ics", headers=h)
    assert ics.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VEVENT" in ics.text
    # Booking persists across sessions: a fresh token for the same Account still sees it.
    again = app_client.get("/api/bookings/current", headers=auth(h_account(h)))
    assert again.json()["booking"]["reference"] == body["booking"]["reference"]


def h_account(h):
    import jwt

    return jwt.decode(h["Authorization"].split()[1], options={"verify_signature": False})["sub"]


def test_steps_are_gated_by_the_server(app_client, seeded, new_account):
    h = auth(new_account())
    assert app_client.get("/api/slots", headers=h).status_code == 404  # no record yet
    consent(app_client, h)
    r = app_client.post("/api/bookings", json={"slot_id": "x"}, headers=h)
    assert r.status_code == 409 and "intake" in r.json()["detail"]
    assert confirm_identity(app_client, h).status_code == 409


def test_consent_requires_onboarding_and_age(app_client, new_account):
    h = auth(new_account())
    r = app_client.post(
        "/api/consent", json={"onboarding": True, "age_confirmed": False}, headers=h
    )
    assert r.status_code == 422 and "adults" in r.json()["detail"]
    r = app_client.post(
        "/api/consent", json={"onboarding": False, "age_confirmed": True}, headers=h
    )
    assert r.status_code == 422


def test_consents_are_logged_with_versions(app_client, new_account, db):
    account = new_account()
    consent(app_client, auth(account), id_scan=True)
    app_client.post("/api/consent/id-scan", json={"allowed": False}, headers=auth(account))
    rows = db.scalars(select(ConsentLogEntry).where(ConsentLogEntry.account_id == account)).all()
    assert {(r.consent, r.action) for r in rows} == {
        ("onboarding", "granted"),
        ("id_scan", "granted"),
        ("id_scan", "withdrawn"),
    }
    assert all(r.version for r in rows)


# ---- identity edge cases --------------------------------------------------------------


def test_scan_without_id_scan_consent_is_refused(app_client, new_account):
    h = auth(new_account())
    consent(app_client, h, id_scan=False)
    finish_intake(app_client, h)
    r = app_client.post(
        "/api/identity/scan", headers=h, files={"file": ("id.jpg", photo(), "image/jpeg")}
    )
    assert r.status_code == 403


@pytest.mark.parametrize(
    "payload,name",
    [(b"%PDF-1.7", "doc.jpg"), (b"", "empty.png"), (b"\x89PNG\r\n\x1a\nbroken", "x.png")],
)
def test_bad_upload_is_rejected_with_message_and_support(app_client, new_account, payload, name):
    h = auth(new_account())
    consent(app_client, h)
    finish_intake(app_client, h)
    r = app_client.post(
        "/api/identity/scan", headers=h, files={"file": (name, payload, "image/jpeg")}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] is False and body["message"]
    assert body["support"]["trigger"] == "upload_problem"


def test_partial_read_marks_missing_fields_blank(app_client, new_account):
    app_client.engine._lines = [
        Line("NAME", 95),
        Line("JANE DOE", 93),
        Line("DATE OF BIRTH", 95),
        Line("1990-03-14", 92),
    ]
    h = auth(new_account())
    consent(app_client, h)
    finish_intake(app_client, h)
    fields = app_client.post(
        "/api/identity/scan", headers=h, files={"file": ("id.jpg", photo(), "image/jpeg")}
    ).json()["fields"]
    assert fields["name"]["status"] == "read" and fields["date_of_birth"]["status"] == "read"
    assert fields["address"] == {"value": None, "status": "blank"}


def test_unreadable_photo_offers_manual_entry_support(app_client, new_account):
    app_client.engine._lines = []
    h = auth(new_account())
    consent(app_client, h)
    finish_intake(app_client, h)
    body = app_client.post(
        "/api/identity/scan", headers=h, files={"file": ("id.jpg", photo(), "image/jpeg")}
    ).json()
    assert body["accepted"] and body["failure_reason"] == "no_text"
    assert body["support"]["trigger"] == "upload_problem"


def test_identity_validation_and_adults_only(app_client, new_account, db):
    h = auth(new_account())
    consent(app_client, h)
    finish_intake(app_client, h)
    bad = app_client.post(
        "/api/identity/confirm",
        headers=h,
        json={
            "legal_name": "J",
            "date_of_birth": "31/31/1990",
            "address": "nowhere",
            "source": "manual",
        },
    )
    assert bad.status_code == 422
    assert set(bad.json()["detail"]["fields"]) == {"legal_name", "date_of_birth", "address"}
    minor = confirm_identity(app_client, h, dob="2015-01-01").json()
    assert minor["confirmed"] is False and minor["adults_only"]
    assert db.scalars(select(IdentityDetails)).first() is None


# ---- intake via API -------------------------------------------------------------------


def test_crisis_message_pauses_and_counts(app_client, new_account, db):
    h = auth(new_account())
    consent(app_client, h)
    r = app_client.post(
        "/api/intake/messages", json={"text": "I want to kill myself"}, headers=h
    ).json()
    assert r["crisis"] and r["crisis_resources"][0]["href"] == "tel:988"
    assert app_client.get("/api/me", headers=h).json()["onboarding"]["crisis_paused"]
    assert app_client.post("/api/bookings", json={"slot_id": "x"}, headers=h).status_code == 409
    resumed = app_client.post("/api/intake/resume", headers=h).json()
    assert resumed["pending_item"] == "reason_category"
    counters = db.execute(text("select count from daily_counters where name='crisis_pauses'"))
    assert counters.scalar() == 1


def test_high_stress_shows_support_card_once(app_client, new_account):
    h = auth(new_account())
    consent(app_client, h)
    first = app_client.post(
        "/api/intake/messages", json={"item": "distress", "value": 5}, headers=h
    ).json()
    assert first["support"]["trigger"] == "high_stress"
    second = app_client.post(
        "/api/intake/messages", json={"text": "I'm so overwhelmed by all this"}, headers=h
    ).json()
    assert second.get("support") is None


def test_llm_down_intake_still_completes(app_client, new_account):
    from app.llm.port import FailureKind

    app_client.llm.fail_next(FailureKind.SERVER_ERROR, times=10)
    h = auth(new_account())
    consent(app_client, h)
    r = app_client.post("/api/intake/messages", json={"text": "anxiety"}, headers=h).json()
    assert "offer_retry_assistant" in r["actions"]
    r = app_client.post("/api/intake/messages", json={"text": "hard to say"}, headers=h).json()
    assert r["scripted_mode"]
    for item, value in ANSWERS[2:]:
        r = app_client.post(
            "/api/intake/messages", json={"item": item, "value": value}, headers=h
        ).json()
    assert r["complete"]


def test_intake_conversation_is_deleted_when_intake_completes(app_client, new_account, db):
    h = auth(new_account())
    consent(app_client, h)
    app_client.post("/api/intake/messages", json={"text": "mostly anxiety"}, headers=h)
    assert db.scalars(select(IntakeMessage)).first() is not None
    finish_intake(app_client, h)
    db.expire_all()
    assert db.scalars(select(IntakeMessage)).first() is None
    assert db.scalars(select(Assessment)).first().completed_at is not None


def test_idle_event_shows_long_pause_once(app_client, new_account):
    h = auth(new_account())
    consent(app_client, h)
    first = app_client.post(
        "/api/support/events",
        headers=h,
        json={"kind": "idle", "step": "intake", "idle_seconds": 50},
    ).json()
    assert first["support"]["trigger"] == "long_pause"
    again = app_client.post(
        "/api/support/events",
        headers=h,
        json={"kind": "idle", "step": "intake", "idle_seconds": 90},
    ).json()
    assert again["support"] is None
    other = app_client.post(
        "/api/support/events", headers=h, json={"kind": "high_stress", "step": "consent"}
    ).json()
    assert other["support"] is None  # browsers cannot claim high stress


# ---- booking via API ------------------------------------------------------------------


def test_double_booking_via_api(app_client, seeded, new_account):
    a, b = auth(new_account()), auth(new_account())
    to_scheduling(app_client, a)
    to_scheduling(app_client, b)
    slot = first_slot(app_client, a)
    assert (
        app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=a).status_code == 200
    )
    r = app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=b)
    assert r.status_code == 409
    assert r.json()["detail"]["alternatives"]


# ---- withdrawal -----------------------------------------------------------------------


def test_withdrawal_deletes_everything_and_is_verifiable(app_client, seeded, new_account, db):
    account = new_account()
    h = auth(account)
    to_scheduling(app_client, h)
    slot = first_slot(app_client, h)
    app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=h)

    assert app_client.post("/api/withdraw", json={"confirm": False}, headers=h).status_code == 422
    receipt = app_client.post("/api/withdraw", json={"confirm": True}, headers=h).json()
    assert receipt["reference"] and receipt["auth_account_deleted"]
    assert app_client.auth_admin.deleted == [account]

    db.expire_all()
    for model in (Assessment, IdentityDetails, IntakeMessage, Booking):
        assert db.scalars(select(model).where(model.client_id == account)).first() is None
    assert db.get(Account, account) is None
    # Slot released for others
    other = auth(new_account())
    to_scheduling(app_client, other)
    assert (
        app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=other).status_code
        == 200
    )
    # Every endpoint now answers "not found" for this Account; it is never silently
    # recreated. ISSUE-016 — found by the whole-codebase review: these returned 401, but
    # PRD story 78 asks for "not found".
    for method, url in [
        ("get", "/api/me"),
        ("get", "/api/intake"),
        ("get", "/api/identity"),
        ("get", "/api/bookings/current"),
    ]:
        assert getattr(app_client, method)(url, headers=h).status_code == 404
    assert db.get(Account, account) is None
    log = db.scalars(select(ConsentLogEntry).where(ConsentLogEntry.action == "deleted")).one()
    assert log.receipt == receipt["reference"] and log.account_id == account


# ---- privacy --------------------------------------------------------------------------


def test_sensitive_fields_are_encrypted_at_rest(app_client, new_account, db):
    h = auth(new_account())
    consent(app_client, h)
    finish_intake(app_client, h)
    confirm_identity(app_client, h)
    raw = db.execute(text("select legal_name, date_of_birth, address from identity_details")).one()
    assert "Jane" not in raw[0] and "1990" not in raw[1] and "Main" not in raw[2]
    raw_reason = db.execute(text("select reason_text from assessments")).scalar()
    assert "overwhelming" not in raw_reason
    assert db.scalars(select(IdentityDetails)).one().legal_name == "Jane Q Doe"


def test_no_personal_data_in_logs_or_timing_records(app_client, seeded, new_account, db, caplog):
    secret_bits = [
        "Jane",
        "1990-03-14",
        "123 Main",
        "overwhelming",
        "kill myself",
        "555-123-4567",
        "jane@example.com",
    ]
    caplog.set_level(logging.INFO, logger="rs_assist")
    from app.telemetry import JsonFormatter, logger

    handler = logging.StreamHandler(stream := io.StringIO())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        h = auth(new_account())
        consent(app_client, h)
        app_client.post(
            "/api/intake/messages",
            headers=h,
            json={"text": "call 555-123-4567 or jane@example.com, overwhelming"},
        )
        finish_intake(app_client, h)
        app_client.post(
            "/api/identity/scan", headers=h, files={"file": ("id.jpg", photo(), "image/jpeg")}
        )
        confirm_identity(app_client, h)
        slot = first_slot(app_client, h)
        app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=h)
        other = auth(new_account())
        consent(app_client, other)
        app_client.post(
            "/api/intake/messages", json={"text": "I want to kill myself"}, headers=other
        )
    finally:
        logger.removeHandler(handler)
    output = stream.getvalue()
    assert '"event": "request"' in output
    rows = db.scalars(select(TimingRecord)).all()
    dumped = output + " ".join(str(vars(r)) for r in rows)
    for bit in secret_bits:
        assert bit not in dumped, bit
    assert all(h_account(h) not in str(vars(r)) for r in rows)


def test_server_timing_header_is_set(app_client, new_account):
    r = app_client.get("/api/me", headers=auth(new_account()))
    assert "total;dur=" in r.headers["Server-Timing"]


# ---- roles ----------------------------------------------------------------------------


def test_unauthenticated_and_bad_tokens(app_client):
    assert app_client.get("/api/me").status_code == 401
    assert app_client.get("/api/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    expired = {"Authorization": f"Bearer {make_token('x', expires_in=-10)}"}
    assert app_client.get("/api/me", headers=expired).status_code == 401


def test_clinician_sees_only_own_bookings_and_views_are_logged(app_client, seeded, new_account, db):
    client_account = new_account()
    h = auth(client_account)
    to_scheduling(app_client, h)
    slot = first_slot(app_client, h)
    booking = app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=h).json()

    clinicians = db.scalars(select(Clinician)).all()
    mine = next(c for c in clinicians if c.name == slot["clinician"])
    other = next(c for c in clinicians if c.name != slot["clinician"])
    mine.account_id, other.account_id = new_account(), new_account()
    db.commit()
    make_role(db, mine.account_id, "clinician")
    make_role(db, other.account_id, "clinician")

    listed = app_client.get("/api/clinician/bookings", headers=auth(mine.account_id)).json()
    assert [b["id"] for b in listed["bookings"]] == [booking["booking"]["id"]]
    detail = app_client.get(
        f"/api/clinician/bookings/{booking['booking']['id']}", headers=auth(mine.account_id)
    ).json()
    assert detail["client_first_name"] == "Jane"
    assert detail["assessment"]["reason_category"]["answer"] == "Anxiety or worry"
    # ISSUE-015 — found by the whole-codebase review: the Safety answer was hidden, so a
    # Client who said "yes", resumed and booked reached the Clinician with no risk flag.
    assert detail["assessment"]["safety"]["answer"] == "No"
    flat = str(detail)
    assert "1990" not in flat and "Main St" not in flat  # no DOB or address

    assert (
        app_client.get("/api/clinician/bookings", headers=auth(other.account_id)).json()["bookings"]
        == []
    )
    denied = app_client.get(
        f"/api/clinician/bookings/{booking['booking']['id']}", headers=auth(other.account_id)
    )
    assert denied.status_code == 403
    entries = db.scalars(select(AccessLogEntry)).all()
    assert [(e.clinician_account_id, e.client_account_id) for e in entries] == [
        (mine.account_id, client_account)
    ]


def test_clinician_is_flagged_when_the_client_answered_yes_to_safety(
    app_client, seeded, new_account, db
):
    # ISSUE-015 — found by the whole-codebase review: "yes", resume and book reached the
    # Clinician with no sign of the Safety answer.
    h = auth(new_account())
    consent(app_client, h)
    answers = [(i, "yes" if i == "safety" else v) for i, v in ANSWERS]
    for item, value in answers:
        if item == "safety":
            app_client.post("/api/intake/messages", json={"item": item, "value": value}, headers=h)
            assert app_client.get("/api/me", headers=h).json()["onboarding"]["crisis_paused"]
            assert app_client.post("/api/intake/resume", headers=h).status_code == 200
            continue
        r = app_client.post("/api/intake/messages", json={"item": item, "value": value}, headers=h)
        assert r.status_code == 200, r.text
    assert r.json()["complete"]
    assert confirm_identity(app_client, h).json()["confirmed"]
    slot = first_slot(app_client, h)
    booking = app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=h).json()

    clinician = next(c for c in db.scalars(select(Clinician)) if c.name == slot["clinician"])
    clinician.account_id = new_account()
    db.commit()
    make_role(db, clinician.account_id, "clinician")
    detail = app_client.get(
        f"/api/clinician/bookings/{booking['booking']['id']}",
        headers=auth(clinician.account_id),
    ).json()
    assert detail["safety_flag"] is True
    assert detail["assessment"]["safety"]["answer"] == "Yes"


def test_clinician_list_shows_only_upcoming_consultations(app_client, seeded, new_account, db):
    # ISSUE-017 — found by the whole-codebase review: past consultations stayed listed,
    # but PRD story 79 is "see my upcoming Initial consultations".
    h = auth(new_account())
    to_scheduling(app_client, h)
    slot = first_slot(app_client, h)
    booking = app_client.post("/api/bookings", json={"slot_id": slot["id"]}, headers=h).json()
    clinician = next(c for c in db.scalars(select(Clinician)) if c.name == slot["clinician"])
    clinician.account_id = new_account()
    db.commit()
    make_role(db, clinician.account_id, "clinician")
    listed = app_client.get("/api/clinician/bookings", headers=auth(clinician.account_id))
    assert [b["id"] for b in listed.json()["bookings"]] == [booking["booking"]["id"]]

    db.get(Slot, slot["id"]).starts_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    listed = app_client.get("/api/clinician/bookings", headers=auth(clinician.account_id))
    assert listed.json()["bookings"] == []


def test_roles_are_enforced(app_client, new_account, db):
    client_h = auth(new_account())
    assert app_client.get("/api/operator/dashboard", headers=client_h).status_code == 403
    assert app_client.get("/api/clinician/bookings", headers=client_h).status_code == 403
    operator = new_account()
    make_role(db, operator, "operator")
    assert (
        app_client.post(
            "/api/consent", headers=auth(operator), json={"onboarding": True, "age_confirmed": True}
        ).status_code
        == 403
    )
    dash = app_client.get("/api/operator/dashboard", headers=auth(operator))
    assert dash.status_code == 200 and "performance" in dash.json()


def test_health_reports_dependencies_and_writes_heartbeat(app_client, db):
    body = app_client.get("/api/health").json()
    assert body["database"] == "ok" and body["llm"] == "ok" and body["status"] == "ok"
    assert db.execute(text("select count(*) from heartbeat")).scalar() == 1


def test_unexpected_error_is_friendly(app_client, new_account, monkeypatch):
    from app import onboarding_service

    def boom(*_):
        raise RuntimeError("secret user text inside")

    monkeypatch.setattr(onboarding_service, "facts", boom)
    r = app_client.get("/api/me", headers=auth(new_account()))
    assert r.status_code == 500
    assert "secret" not in r.text and "progress is saved" in r.json()["detail"]
