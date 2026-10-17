"""Stretch #6 — sentiment-adaptive tone ("gentle mode"), through the Intake conductor."""

import pytest

from app.domain.intake import (
    BREAK_REPLY,
    BREAK_VALUE,
    CHECK_IN_ITEM,
    IntakeConductor,
    IntakeState,
    Turn,
)
from app.llm.fake import FakeLLM
from tests.conftest import auth
from tests.test_api_flow import consent

# The high-stress supportive card (same triggers) already says "we can go slowly"; the chat
# must not repeat it.
REPEATED = "take this slowly"


def result(intent="provide-details", answers=(), reply="Thank you."):
    return {
        "intent": intent,
        "answers": [{"item": i, "value": v} for i, v in answers],
        "approved_answer_id": "none",
        "reply": reply,
    }


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def conductor(profile, llm):
    return IntakeConductor(profile, llm, timeout=5)


@pytest.mark.parametrize("trigger", ["distress_button", "distress_intent", "check_in_no"])
def test_each_high_stress_signal_turns_gentle_mode_on(conductor, llm, trigger):
    state = IntakeState()
    if trigger == "distress_button":
        state, reply = conductor.respond(state, Turn(item="distress", value=5))
    elif trigger == "distress_intent":
        llm.script(result(intent="express-distress", reply="That sounds hard."))
        state, reply = conductor.respond(state, Turn(text="I'm so overwhelmed"))
    else:
        state, _ = conductor.respond(state, Turn(text="this form is killing me"))
        state, reply = conductor.respond(state, Turn(item=CHECK_IN_ITEM, value="no"))
    assert state.gentle
    assert BREAK_REPLY in reply.quick_replies
    assert not any(REPEATED in m.lower() for m in reply.messages)


def test_calm_conversation_stays_normal(conductor):
    state, reply = conductor.respond(IntakeState(), Turn(item="distress", value=2))
    assert not state.gentle
    assert all(q["value"] != BREAK_VALUE for q in reply.quick_replies)


def test_high_stress_signal_also_shows_the_supportive_card_via_signals(conductor):
    _, reply = conductor.respond(IntakeState(), Turn(item="distress", value=5))
    assert reply.signals.high_stress  # the API turns this into the one reassurance card


def test_gentle_mode_offers_a_break_on_every_question(conductor):
    state, reply = conductor.respond(
        IntakeState(gentle=True), Turn(item="reason_category", value="anxiety")
    )
    assert reply.pending_item == "reason_text"  # a free-text question
    assert {"value": BREAK_VALUE, "label": "Take a break"} in reply.quick_replies


def test_gentle_mode_shapes_the_prompt_and_trims_the_reply(conductor, llm):
    llm.script(
        result(
            answers=[("reason_category", "grief")],
            reply="I'm so sorry for your loss. Grief can be really heavy. Take care.",
        )
    )
    state, reply = conductor.respond(IntakeState(gentle=True), Turn(text="my dad died"))
    system = llm.calls[0][0]
    assert "finding this hard" in system and "one short" in system
    assert "I'm so sorry for your loss." in reply.messages
    assert not any("Grief can be really heavy" in m for m in reply.messages)


def test_gentle_mode_never_changes_safety(conductor):
    state, reply = conductor.respond(IntakeState(gentle=True), Turn(text="I want to end my life"))
    assert state.crisis_paused and reply.signals.crisis
    assert all(q["value"] != BREAK_VALUE for q in reply.quick_replies)


def test_break_value_is_never_stored_as_an_answer(conductor):
    state, reply = conductor.respond(
        IntakeState(gentle=True), Turn(item="reason_category", value=BREAK_VALUE)
    )
    assert "reason_category" not in state.answers
    assert reply.pending_item == "reason_category"


def test_gentle_mode_persists_across_sessions(app_client, new_account):
    h = auth(new_account())
    consent(app_client, h)
    first = app_client.post(
        "/api/intake/messages", json={"item": "distress", "value": 5}, headers=h
    ).json()
    assert first["gentle"] is True
    again = app_client.get("/api/intake", headers=h).json()  # a new session
    assert again["gentle"] is True
    assert {"value": BREAK_VALUE, "label": "Take a break"} in again["quick_replies"]
