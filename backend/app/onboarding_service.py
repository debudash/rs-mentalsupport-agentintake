"""Loads and saves what the pure modules need: Onboarding facts and Intake state."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import journeys
from app.db.models import Assessment, Booking, Client, IdentityDetails, IntakeMessage
from app.domain import support
from app.domain.intake import HISTORY_TURNS, IntakeConductor, IntakeState
from app.domain.onboarding import Facts, Step
from app.llm.port import ChatMessage
from app.profile import ServiceProfile

SENSITIVE = ("reason_text", "safety")


# A Client answer given with a quick-reply button: shown on resume, never sent to the LLM.
BUTTON_ROLE = "client_choice"


def facts(db: Session, client: Client | None) -> Facts:
    if client is None:
        return Facts()
    assessment = db.get(Assessment, client.account_id)
    has_booking = db.scalars(
        select(Booking.id).where(Booking.client_id == client.account_id, Booking.status == "active")
    ).first()
    return Facts(
        consent_given=bool(client.onboarding_consent_version and client.age_confirmed),
        assessment_complete=bool(assessment and assessment.completed_at),
        identity_confirmed=db.get(IdentityDetails, client.account_id) is not None,
        has_booking=has_booking is not None,
        crisis_paused=client.crisis_paused,
    )


def load_intake(db: Session, client: Client) -> IntakeState:
    assessment = db.get(Assessment, client.account_id)
    answers: dict = {}
    if assessment is not None:
        answers = dict(assessment.answers)
        if assessment.reason_text is not None:
            answers["reason_text"] = assessment.reason_text
        if assessment.safety is not None:
            answers["safety"] = assessment.safety
    # ISSUE-019: button answers used to be saved as ordinary Client messages, so they
    # (the Safety answer included) reached the LLM as history on the next free-text turn.
    # They are saved with their own role, shown in the transcript, never sent as history.
    messages = db.scalars(
        select(IntakeMessage)
        .where(IntakeMessage.client_id == client.account_id, IntakeMessage.role != BUTTON_ROLE)
        .order_by(IntakeMessage.created_at.desc())
        .limit(HISTORY_TURNS)
    ).all()
    history = [
        ChatMessage("user" if m.role == "client" else "assistant", m.body)
        for m in reversed(messages)
    ]
    return IntakeState(
        answers=answers,
        history=history,
        check_in_pending=client.check_in_pending,
        llm_failures=client.llm_failures,
        scripted_mode=client.scripted_mode,
        crisis_paused=client.crisis_paused,
        gentle=bool(client.gentle_mode),
    )


def save_intake(
    db: Session,
    conductor: IntakeConductor,
    client: Client,
    state: IntakeState,
    client_text: str | None,
    assistant_messages: list[str],
    from_button: bool = False,
) -> bool:
    """Persist the turn. Returns True if this turn completed Intake."""
    assessment = db.get(Assessment, client.account_id)
    if assessment is None:
        assessment = Assessment(client_id=client.account_id, answers={})
        db.add(assessment)
    assessment.answers = {k: v for k, v in state.answers.items() if k not in SENSITIVE}
    assessment.reason_text = _as_text(state.answers.get("reason_text"))
    assessment.safety = _as_text(state.answers.get("safety"))

    client.check_in_pending = state.check_in_pending
    client.llm_failures = state.llm_failures
    client.scripted_mode = state.scripted_mode
    client.crisis_paused = state.crisis_paused
    client.gentle_mode = state.gentle
    client.updated_at = datetime.now(UTC)

    completed_now = assessment.completed_at is None and conductor.is_complete(state)
    if completed_now:
        assessment.completed_at = datetime.now(UTC)
        journeys.record(db, client.account_id, "intake_completed")
        # Minimisation: the conversation was only a means to the Assessment.
        db.execute(delete(IntakeMessage).where(IntakeMessage.client_id == client.account_id))
    elif assessment.completed_at is None:
        if client_text:
            role = BUTTON_ROLE if from_button else "client"
            db.add(IntakeMessage(client_id=client.account_id, role=role, body=client_text))
        if assistant_messages:
            db.add(
                IntakeMessage(
                    client_id=client.account_id,
                    role="assistant",
                    body="\n".join(assistant_messages),
                )
            )
    db.commit()
    return completed_now


def _as_text(value) -> str | None:
    return None if value is None else str(value)


def first_name(legal_name: str) -> str:
    return legal_name.strip().split()[0] if legal_name.strip() else ""


def transcript(db: Session, client: Client) -> list[dict]:
    rows = db.scalars(
        select(IntakeMessage)
        .where(IntakeMessage.client_id == client.account_id)
        .order_by(IntakeMessage.created_at)
    ).all()
    return [{"role": "client" if m.role == BUTTON_ROLE else m.role, "text": m.body} for m in rows]


def assessment_answers(db: Session, client_id: str) -> dict:
    assessment = db.get(Assessment, client_id)
    return dict(assessment.answers) if assessment else {}


def profile_summary(profile: ServiceProfile) -> dict:
    return {
        "service": profile.service.model_dump(),
        "consents": {k: v.model_dump() for k, v in profile.consents.items()},
        "step_guidance": profile.step_guidance,
        "crisis": {
            "resources": [r.model_dump() for r in profile.crisis.resources],
            "pause_message": profile.crisis.pause_message,
        },
        "contact": profile.contact.model_dump(),
        "supportive_content": {k: v.model_dump() for k, v in profile.supportive_content.items()},
    }


def pre_consent_support(
    db: Session, account_id: str, event: support.Event
) -> support.Trigger | None:
    """Supportive content before consent, when there is no Client record (and so no
    support_shown list). A long pause on the Consent Step is a classic drop-off point; the
    Journey remembers whether its card was shown, so the usual once-per-Step rule holds.
    """
    # ISSUE-008: the pause endpoint required the Client record, which only exists after
    # consent, so hesitating at Consent produced no card and no signal.
    # ISSUE-020: any event kind that had a Trigger (e.g. upload_failed) used to show the
    # long-pause card here; only a pause belongs on the Consent Step.
    if event.step != Step.CONSENT or event.kind != "idle":
        return None
    kind = support.Trigger.LONG_PAUSE.value
    shown = (
        [support.shown_key(event.step, support.Trigger.LONG_PAUSE)]
        if journeys.has_friction(db, account_id, event.step, kind)
        else []
    )
    trigger = support.decide(event, shown, crisis_paused=False)
    if trigger is not None:
        journeys.friction(db, account_id, event.step, trigger.value)
        db.commit()
    return trigger
