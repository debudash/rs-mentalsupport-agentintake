"""Onboarding engine: Step order, gating, Crisis pause and completion — pure logic.

Callers pass in the facts they loaded; the engine answers "where is this Client?" and
"is this action allowed now?". It never touches the database.
"""

from dataclasses import dataclass
from enum import StrEnum


class Step(StrEnum):
    CONSENT = "consent"
    INTAKE = "intake"
    IDENTITY = "identity"
    SCHEDULING = "scheduling"
    DONE = "done"


ORDER = [Step.CONSENT, Step.INTAKE, Step.IDENTITY, Step.SCHEDULING]


class Action(StrEnum):
    GRANT_CONSENT = "grant_consent"
    INTAKE_MESSAGE = "intake_message"
    RESUME = "resume"
    SCAN_ID = "scan_id"
    CONFIRM_IDENTITY = "confirm_identity"
    VIEW_SLOTS = "view_slots"
    BOOK = "book"
    WITHDRAW = "withdraw"


# The Step an action belongs to. Actions on an earlier, completed Step stay allowed
# (e.g. rescheduling after Done), actions on a later Step are rejected.
_ACTION_STEP = {
    Action.GRANT_CONSENT: Step.CONSENT,
    Action.INTAKE_MESSAGE: Step.INTAKE,
    Action.SCAN_ID: Step.IDENTITY,
    Action.CONFIRM_IDENTITY: Step.IDENTITY,
    Action.VIEW_SLOTS: Step.SCHEDULING,
    Action.BOOK: Step.SCHEDULING,
}


@dataclass(frozen=True)
class Facts:
    consent_given: bool = False
    assessment_complete: bool = False
    identity_confirmed: bool = False
    has_booking: bool = False
    crisis_paused: bool = False


@dataclass(frozen=True)
class State:
    step: Step
    completed: tuple[Step, ...]
    crisis_paused: bool

    @property
    def complete(self) -> bool:
        return self.step is Step.DONE


@dataclass(frozen=True)
class Rejection:
    reason: str


def state(facts: Facts) -> State:
    done_flags = [
        facts.consent_given,
        facts.assessment_complete,
        facts.identity_confirmed,
        facts.has_booking,
    ]
    completed: list[Step] = []
    current = Step.DONE
    for step, done in zip(ORDER, done_flags, strict=True):
        if not done:
            current = step
            break
        completed.append(step)
    return State(step=current, completed=tuple(completed), crisis_paused=facts.crisis_paused)


def check(facts: Facts, action: Action) -> Rejection | None:
    """None if the action is allowed now, otherwise the reason it is not."""
    if action is Action.WITHDRAW:
        return None
    current = state(facts)
    if facts.crisis_paused:
        if action is Action.RESUME:
            return None
        return Rejection("Onboarding is paused. Please look after yourself first.")
    if action is Action.RESUME:
        return Rejection("Onboarding is not paused.")
    target = _ACTION_STEP[action]
    if current.step is Step.DONE or target in current.completed or target is current.step:
        return None
    return Rejection(f"Please finish the {current.step.value} step first.")
