"""HTTP API: translates requests into module calls. Deliberately thin."""

from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import consent as consent_module
from app import journeys, telemetry
from app import onboarding_service as svc
from app.access import Caller, clinician_bookings, clinician_view, require
from app.api.deps import caller, conductor, profile
from app.auth_admin import AuthAdmin, get_auth_admin
from app.config import get_settings
from app.dashboard import dashboard
from app.db.models import Client, Clinician, Heartbeat, IdentityDetails
from app.db.session import get_db
from app.domain import onboarding, support
from app.domain.intake import IntakeConductor, Reply, Turn
from app.domain.onboarding import Action
from app.llm import get_llm
from app.ocr import DocumentReader, UploadRejected, get_reader
from app.ocr.parse import clean_name, parse_date
from app.profile import ServiceProfile
from app.scheduling import (
    OpenSlot,
    OutsideWindow,
    Scheduling,
    SlotTaken,
    calendar_file,
    filters_from_assessment,
    zone,
)

router = APIRouter(prefix="/api")


# ---- helpers --------------------------------------------------------------------------


def _client(db: Session, who: Caller) -> Client | None:
    require(who, "client")
    return db.get(Client, who.account_id)


def _require_client(db: Session, who: Caller) -> Client:
    client = _client(db, who)
    if client is None:
        raise HTTPException(404, "No onboarding record. Please start with the consent step.")
    return client


def _gate(db: Session, client: Client | None, action: Action) -> None:
    rejection = onboarding.check(svc.facts(db, client), action)
    if rejection:
        raise HTTPException(409, rejection.reason)


def _support_card(db: Session, prof: ServiceProfile, client: Client, event: support.Event):
    trigger = support.decide(event, list(client.support_shown or []), client.crisis_paused)
    if trigger is None:
        return None
    client.support_shown = list(client.support_shown or []) + [
        support.shown_key(event.step, trigger)
    ]
    db.commit()
    card = prof.supportive_content[trigger.value]
    return {"trigger": trigger.value, "title": card.title, "body": card.body}


def _state_payload(db: Session, client: Client | None) -> dict:
    current = onboarding.state(svc.facts(db, client))
    return {
        "step": current.step.value,
        "completed": [s.value for s in current.completed],
        "crisis_paused": current.crisis_paused,
    }


def _local_label(local: datetime, long: bool = False) -> str:
    day = local.strftime("%A" if long else "%a")
    month = local.strftime("%B" if long else "%b")
    return f"{day} {local.day} {month}, {local.hour % 12 or 12}:{local:%M} {local:%p}"


def _slot_out(slot: OpenSlot, tz_name: str | None) -> dict:
    local = slot.starts_at.astimezone(zone(tz_name))
    return {
        "id": slot.id,
        "starts_at": slot.starts_at.isoformat(),
        "local_label": _local_label(local),
        "time_zone": local.tzname(),
        "format": slot.format,
        "clinician": slot.clinician_name,
    }


# ---- health & config --------------------------------------------------------------------


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    status = {"app": "ok"}
    try:
        # A write, not just a read: keeps the Supabase Free plan from pausing.
        beat = db.get(Heartbeat, 1)
        if beat is None:
            db.add(Heartbeat(id=1, at=datetime.now(UTC)))
        else:
            beat.at = datetime.now(UTC)
        db.commit()
        db.execute(text("select 1"))
        status["database"] = "ok"
    except Exception:  # noqa: BLE001
        db.rollback()
        status["database"] = "unreachable"
    reader = get_reader()
    status["ocr"] = "ok" if reader.available() else "unavailable"
    status["ocr_engine"] = reader.engine_name
    llm = get_llm()
    status["llm"] = "ok" if llm.ping() else "unreachable"
    status["llm_provider"] = llm.provider
    status["llm_model"] = llm.model
    status["status"] = "ok" if status["database"] == "ok" else "degraded"
    return status


@router.get("/config")
def public_config() -> dict:
    settings = get_settings()
    return {"supabase_url": settings.supabase_url, "supabase_anon_key": settings.supabase_anon_key}


# ---- me ---------------------------------------------------------------------------------


@router.get("/me")
def me(
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    payload: dict[str, Any] = {"role": who.role, "profile": svc.profile_summary(prof)}
    if who.role == "client":
        client = db.get(Client, who.account_id)
        payload["onboarding"] = _state_payload(db, client)
        payload["consents"] = {
            "onboarding": bool(client and client.onboarding_consent_version),
            "id_scan": bool(client and client.id_scan_consent_version),
            "age_confirmed": bool(client and client.age_confirmed),
        }
    return payload


# ---- consent ----------------------------------------------------------------------------


class ConsentIn(BaseModel):
    onboarding: bool
    id_scan: bool = False
    age_confirmed: bool


@router.post("/consent")
def grant_consent(
    body: ConsentIn,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    require(who, "client")
    result = consent_module.grant(
        db, prof, who.account_id, body.onboarding, body.id_scan, body.age_confirmed
    )
    if isinstance(result, consent_module.ConsentRejected):
        raise HTTPException(422, result.reason)
    return {"onboarding": _state_payload(db, result)}


class IdScanIn(BaseModel):
    allowed: bool


@router.post("/consent/id-scan")
def set_id_scan(
    body: IdScanIn,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    consent_module.set_id_scan(db, prof, client, body.allowed)
    db.commit()
    return {"id_scan": bool(client.id_scan_consent_version)}


# ---- intake -----------------------------------------------------------------------------


def _reply_out(reply: Reply, prof: ServiceProfile) -> dict:
    out = {
        "messages": reply.messages,
        "pending_item": reply.pending_item,
        "input_kind": reply.input_kind,
        "quick_replies": reply.quick_replies,
        "complete": reply.complete,
        "actions": reply.actions,
        "crisis": reply.signals.crisis,
    }
    if reply.signals.crisis:
        out["crisis_resources"] = [r.model_dump() for r in prof.crisis.resources]
    return out


@router.get("/intake")
def intake_state(
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    cond: IntakeConductor = Depends(conductor),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    if not client.crisis_paused:
        _gate(db, client, Action.INTAKE_MESSAGE)
    state = svc.load_intake(db, client)
    reply = cond.prompt_for(state)
    reply.signals.crisis = state.crisis_paused
    out = _reply_out(reply, prof)
    out["transcript"] = svc.transcript(db, client)
    out["scripted_mode"] = client.scripted_mode
    out["gentle"] = bool(client.gentle_mode)
    return out


class IntakeIn(BaseModel):
    text: str | None = Field(default=None, max_length=2000)
    item: str | None = None
    value: Any = None
    retry_assistant: bool = False


@router.post("/intake/messages")
def intake_message(
    body: IntakeIn,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    cond: IntakeConductor = Depends(conductor),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    if not client.crisis_paused:
        _gate(db, client, Action.INTAKE_MESSAGE)
    with telemetry.timed("db"):
        state = svc.load_intake(db, client)
    was_paused = state.crisis_paused
    new_state, reply = cond.respond(
        state,
        Turn(
            text=body.text, item=body.item, value=body.value, retry_assistant=body.retry_assistant
        ),
    )
    s = reply.signals
    if s.llm_ms is not None:
        timings = telemetry.current()
        if timings:
            timings.add("llm", s.llm_ms)
    outcome = (
        "crisis"
        if s.crisis
        else "check_in"
        if s.check_in
        else f"llm_failure:{s.llm_failure}"
        if s.llm_failure
        else "scripted"
        if s.fallback
        else "output_check_tripped"
        if s.output_check_tripped
        else "llm_ok"
        if s.llm_used
        else "structured"
    )
    llm = get_llm()
    telemetry.note(
        outcome=outcome,
        intent=s.intent,
        provider=llm.provider if s.llm_used else None,
        model=llm.model if s.llm_used else None,
    )
    if s.llm_failure:
        telemetry.log(
            "llm_error",
            provider=llm.provider,
            error_type=s.llm_failure,
            latency_ms=round(s.llm_ms or 0, 1),
        )

    client_text = body.text or (str(body.value) if body.item else None)
    with telemetry.timed("db"):
        completed = svc.save_intake(db, cond, client, new_state, client_text, reply.messages)
        if s.crisis and not was_paused:
            consent_module.bump_counter(db, "crisis_pauses")
            db.commit()
    out = _reply_out(reply, prof)
    out["complete"] = completed or reply.complete
    out["scripted_mode"] = new_state.scripted_mode
    out["gentle"] = new_state.gentle
    if s.high_stress:
        out["support"] = _support_card(
            db, prof, client, support.Event(kind="high_stress", step="intake")
        )
    return out


@router.post("/intake/resume")
def intake_resume(
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    cond: IntakeConductor = Depends(conductor),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    _gate(db, client, Action.RESUME)
    client.crisis_paused = False
    db.commit()
    state = svc.load_intake(db, client)
    reply = cond.prompt_for(state, ["Welcome back. We can carry on whenever you're ready."])
    return {**_reply_out(reply, prof), "onboarding": _state_payload(db, client)}


# ---- identity ---------------------------------------------------------------------------


@router.post("/identity/scan")
async def identity_scan(
    file: UploadFile = File(...),
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
    reader: DocumentReader = Depends(get_reader),
) -> dict:
    client = _require_client(db, who)
    _gate(db, client, Action.SCAN_ID)
    if not client.id_scan_consent_version:
        raise HTTPException(403, "ID scan consent is needed to read a photo. You can type instead.")
    max_bytes = get_settings().upload_max_bytes
    data = await file.read(max_bytes + 1)
    try:
        with telemetry.timed("ocr"):
            result = await run_in_threadpool(reader.read_identity, data)
    except UploadRejected as rejected:
        del data
        telemetry.note(outcome=f"rejected:{rejected.reason}")
        card = _support_card(db, prof, client, support.Event(kind="upload_failed", step="identity"))
        return {
            "accepted": False,
            "reason": rejected.reason,
            "message": rejected.message,
            "support": card,
            "fields": None,
        }
    del data
    fields = {
        name: {"value": f.value, "status": "read" if f.value else "blank"}
        for name, f in result.fields.items()
    }
    read_names = ",".join(n for n, f in fields.items() if f["value"])
    telemetry.note(outcome=f"read:{read_names}" if read_names else "read:none")
    out = {
        "accepted": True,
        "fields": fields,
        "failure_reason": result.failure_reason,
        "support": None,
    }
    if not result.any_read:
        out["support"] = _support_card(
            db, prof, client, support.Event(kind="upload_failed", step="identity")
        )
    return out


class IdentityIn(BaseModel):
    legal_name: str = Field(min_length=1, max_length=120)
    date_of_birth: str = Field(min_length=1, max_length=40)
    address: str = Field(min_length=1, max_length=240)
    source: str = Field(pattern="^(scan|manual)$")
    edited: dict[str, bool] = Field(default_factory=dict)
    # Which fields the scan pre-filled (true/false only) — for the OCR-correction metric.
    prefilled: dict[str, bool] = Field(default_factory=dict)


def _age(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


@router.post("/identity/confirm")
def identity_confirm(
    body: IdentityIn,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    _gate(db, client, Action.CONFIRM_IDENTITY)
    errors = {}
    name = clean_name(body.legal_name) or (
        body.legal_name.strip() if len(body.legal_name.strip().split()) >= 2 else None
    )
    if not name:
        errors["legal_name"] = "Please enter your full legal name (first and last)."
    iso = parse_date(body.date_of_birth)
    if not iso:
        errors["date_of_birth"] = "Please enter a valid date of birth, for example 1990-03-14."
    address = " ".join(body.address.split())
    if len(address) < 8 or not any(c.isdigit() for c in address):
        errors["address"] = "Please enter your full address, including the street number."
    if errors:
        raise HTTPException(422, {"fields": errors})
    if _age(date.fromisoformat(iso), date.today()) < prof.service.minimum_age:
        return {
            "confirmed": False,
            "adults_only": True,
            "message": (
                f"This service is for adults aged {prof.service.minimum_age} and over, so we "
                "can't continue your sign-up. A school counselor or family doctor is a good "
                "place to start, and 988 is free and available to everyone, any time."
            ),
            "crisis_resources": [r.model_dump() for r in prof.crisis.resources],
        }
    details = db.get(IdentityDetails, client.account_id) or IdentityDetails(
        client_id=client.account_id
    )
    details.legal_name = name
    details.date_of_birth = iso
    details.address = address
    details.source = body.source
    details.edited = {
        k: bool(v)
        for k, v in body.edited.items()
        if k in ("legal_name", "date_of_birth", "address")
    }
    details.confirmed_at = datetime.now(UTC)
    db.add(details)
    client.first_name = svc.first_name(name)
    journeys.record(db, client.account_id, "identity_completed")
    if body.source == "scan" and body.prefilled:
        journeys.record_ocr_review(db, client.account_id, body.prefilled, details.edited)
    db.commit()
    return {"confirmed": True, "onboarding": _state_payload(db, client)}


@router.get("/identity")
def identity_get(who: Caller = Depends(caller), db: Session = Depends(get_db)) -> dict:
    client = _require_client(db, who)
    details = db.get(IdentityDetails, client.account_id)
    if details is None:
        raise HTTPException(404, "No identity details yet.")
    return {
        "legal_name": details.legal_name,
        "date_of_birth": details.date_of_birth,
        "address": details.address,
        "source": details.source,
    }


# ---- scheduling -------------------------------------------------------------------------


@router.get("/slots")
def slots(
    tz: str | None = Query(default=None, max_length=64),
    show_all: bool = False,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    _gate(db, client, Action.VIEW_SLOTS)
    filters = filters_from_assessment(svc.assessment_answers(db, client.account_id), show_all)
    with telemetry.timed("db"):
        found = Scheduling(db, prof).open_slots(filters, tz)
    return {
        "slots": [_slot_out(s, tz) for s in found[:400]],
        "filtered": not show_all,
        "filters": {
            "session_format": filters.session_format,
            "availability": list(filters.availability),
            "clinician_gender": filters.clinician_gender,
            "clinician_language": filters.clinician_language,
        },
    }


class BookingIn(BaseModel):
    slot_id: str = Field(max_length=36)
    tz: str | None = Field(default=None, max_length=64)


def _booking_out(db: Session, prof: ServiceProfile, client_id: str, tz: str | None) -> dict | None:
    found = Scheduling(db, prof).current_booking(client_id)
    if not found:
        return None
    booking, slot, clinician = found
    local = slot.starts_at if slot.starts_at.tzinfo else slot.starts_at.replace(tzinfo=UTC)
    local = local.astimezone(zone(tz))
    return {
        "id": booking.id,
        "reference": booking.reference,
        "starts_at": slot.starts_at.isoformat(),
        "local_label": _local_label(local, long=True),
        "time_zone": local.tzname(),
        "format": slot.format,
        "clinician": clinician.name,
        "minutes": prof.service.consultation_minutes,
    }


@router.post("/bookings")
def book(
    body: BookingIn,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    _gate(db, client, Action.BOOK)
    with telemetry.timed("db"):
        result = Scheduling(db, prof).book(client.account_id, body.slot_id)
    if isinstance(result, SlotTaken):
        telemetry.note(outcome="slot_taken")
        raise HTTPException(
            409,
            {
                "message": "Someone just took that time. Here are the nearest alternatives.",
                "alternatives": [_slot_out(s, body.tz) for s in result.alternatives],
            },
        )
    if isinstance(result, OutsideWindow):
        raise HTTPException(422, result.reason)
    telemetry.note(outcome="booked")
    journeys.record(db, client.account_id, "booked")
    db.commit()
    return {
        "booking": _booking_out(db, prof, client.account_id, body.tz),
        "onboarding": _state_payload(db, client),
    }


@router.get("/bookings/current")
def current_booking(
    tz: str | None = Query(default=None, max_length=64),
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _require_client(db, who)
    booking = _booking_out(db, prof, client.account_id, tz)
    if booking is None:
        raise HTTPException(404, "No booking yet.")
    return {"booking": booking}


@router.get("/bookings/current/ics")
def current_booking_ics(
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> Response:
    client = _require_client(db, who)
    found = Scheduling(db, prof).current_booking(client.account_id)
    if not found:
        raise HTTPException(404, "No booking yet.")
    return Response(
        calendar_file(*found, prof),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="initial-consultation.ics"'},
    )


# ---- support ----------------------------------------------------------------------------


class SupportEventIn(BaseModel):
    kind: str = Field(max_length=32)
    step: str = Field(max_length=32)
    idle_seconds: float = 0


@router.post("/support/events")
def support_event(
    body: SupportEventIn,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    client = _client(db, who)
    if client is None:
        return {"support": None}
    current = onboarding.state(svc.facts(db, client))
    step_complete = body.step in [s.value for s in current.completed]
    # Only events reported by the browser; high stress is decided server-side in Intake.
    kind = body.kind if body.kind in ("idle", "upload_failed") else "ignored"
    event = support.Event(
        kind=kind, step=body.step, idle_seconds=body.idle_seconds, step_complete=step_complete
    )
    return {"support": _support_card(db, prof, client, event)}


# ---- withdrawal -------------------------------------------------------------------------


class WithdrawIn(BaseModel):
    confirm: bool


@router.post("/withdraw")
def withdraw(
    body: WithdrawIn,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    auth_admin: AuthAdmin = Depends(get_auth_admin),
) -> dict:
    require(who, "client")
    if not body.confirm:
        raise HTTPException(422, "Please confirm you want to delete everything.")
    receipt = consent_module.withdraw(db, auth_admin, who.account_id)
    return {
        "reference": receipt.reference,
        "deleted_at": receipt.deleted_at.isoformat(),
        "deleted": [
            "Assessment and intake conversation",
            "Identity details",
            "Booking (the time is released)",
            "Onboarding progress",
            "Account",
        ],
        "auth_account_deleted": receipt.auth_account_deleted,
    }


# ---- clinician --------------------------------------------------------------------------


@router.get("/clinician/bookings")
def clinician_list(who: Caller = Depends(caller), db: Session = Depends(get_db)) -> dict:
    rows = clinician_bookings(db, who)
    clinician = db.scalars(select(Clinician).where(Clinician.account_id == who.account_id)).first()
    return {
        "clinician": clinician.name if clinician else None,
        "bookings": [
            {
                "id": b.id,
                "starts_at": s.starts_at.isoformat(),
                "format": s.format,
                "reference": b.reference,
            }
            for b, s in rows
        ],
    }


@router.get("/clinician/bookings/{booking_id}")
def clinician_detail(
    booking_id: str,
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
    prof: ServiceProfile = Depends(profile),
) -> dict:
    view = clinician_view(db, who, booking_id)
    labels = {item.id: item for item in prof.assessment}
    readable = {}
    for key, value in (view.assessment or {}).items():
        item = labels.get(key)
        if item is None:
            continue
        if isinstance(value, list):
            readable[key] = {
                "question": item.question,
                "answer": ", ".join(item.options.get(v, v) for v in value),
            }
        else:
            readable[key] = {
                "question": item.question,
                "answer": item.options.get(str(value), str(value)) if item.options else str(value),
            }
    return {
        "booking_id": view.booking_id,
        "starts_at": view.starts_at.isoformat() if view.starts_at else None,
        "format": view.format,
        "reference": view.reference,
        "client_first_name": view.client_first_name,
        "assessment": readable,
    }


# ---- operator ---------------------------------------------------------------------------


@router.get("/operator/dashboard")
def operator_dashboard(
    hours: int = Query(default=24, ge=1, le=24 * 14),
    who: Caller = Depends(caller),
    db: Session = Depends(get_db),
) -> dict:
    require(who, "operator")
    return dashboard(db, hours)
