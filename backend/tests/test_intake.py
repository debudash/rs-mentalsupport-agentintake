"""Intake conductor, exercised only through respond() / prompt_for()."""

import pytest

from app.domain.intake import (
    CHECK_IN_ITEM,
    DECLINED,
    IntakeConductor,
    IntakeState,
    Turn,
    validate_value,
)
from app.llm.fake import FakeLLM, HeuristicResponder
from app.llm.port import ChatMessage, FailureKind, LLMFailure

STRUCTURED_ANSWERS = [
    ("reason_category", "anxiety"),
    ("reason_text", "Work has been really overwhelming"),
    ("duration", "1_6_months"),
    ("distress", "3"),
    ("safety", "no"),
    ("session_format", "video"),
    ("availability", "mornings,evenings"),
    ("clinician_gender", DECLINED),
    ("clinician_language", "english"),
]


def turn_result(intent="provide-details", answers=(), approved="none", reply="Thank you."):
    return {
        "intent": intent,
        "answers": [{"item": i, "value": v} for i, v in answers],
        "approved_answer_id": approved,
        "reply": reply,
    }


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def conductor(profile, llm):
    return IntakeConductor(profile, llm, timeout=5)


def run(conductor, state, *turns):
    reply = None
    for t in turns:
        state, reply = conductor.respond(state, t)
    return state, reply


def test_first_prompt_asks_the_first_item_with_quick_replies(conductor):
    reply = conductor.prompt_for(IntakeState())
    assert reply.pending_item == "reason_category"
    assert {"value": "anxiety", "label": "Anxiety or worry"} in reply.quick_replies


def test_scripted_conversation_produces_a_complete_assessment(conductor, llm):
    state = IntakeState()
    for item, value in STRUCTURED_ANSWERS:
        state, reply = conductor.respond(state, Turn(item=item, value=value))
    assert reply.complete
    assert conductor.is_complete(state)
    assert state.answers["availability"] == ["mornings", "evenings"]
    assert state.answers["distress"] == 3
    assert state.answers["clinician_gender"] == DECLINED
    assert llm.calls == []  # buttons never need the LLM


def test_free_text_uses_exactly_one_llm_call_per_message(conductor, llm):
    llm.script(turn_result(answers=[("reason_category", "anxiety"), ("duration", "1_6_months")]))
    state, reply = conductor.respond(IntakeState(), Turn(text="anxiety, for about three months"))
    assert len(llm.calls) == 1
    assert state.answers == {"reason_category": "anxiety", "duration": "1_6_months"}
    assert reply.pending_item == "reason_text"  # the checklist decides what's next
    assert reply.signals.intent == "provide-details"


def test_text_sent_to_llm_is_masked(conductor, llm):
    llm.script(turn_result())
    conductor.respond(IntakeState(), Turn(text="call me on 555-123-4567 or me@x.com"))
    sent = llm.calls[0][1][-1].content
    assert "555" not in sent and "me@x.com" not in sent
    assert "[phone]" in sent and "[email]" in sent


def test_earlier_turns_sent_to_llm_are_masked_too(conductor, llm):
    # ISSUE-014 — found by the whole-codebase review: history reloaded from saved (raw)
    # messages was sent to the provider unmasked on the following turns.
    llm.script(turn_result())
    state = IntakeState(
        history=[
            ChatMessage("user", "text me at 555-123-4567, I live at 12 Oak Street"),
            ChatMessage("assistant", "Thanks. Reach us at me@x.com."),
        ]
    )
    conductor.respond(state, Turn(text="it started on 3/14/2025"))
    sent = " ".join(m.content for m in llm.calls[0][1])
    for raw in ("555-123-4567", "12 Oak Street", "me@x.com", "3/14/2025"):
        assert raw not in sent
    assert "[phone]" in sent and "[address]" in sent


def test_ask_question_shows_the_approved_answer_verbatim(conductor, llm, profile):
    llm.script(turn_result(intent="ask-question", approved="cost", reply="Good question!"))
    _, reply = conductor.respond(IntakeState(), Turn(text="how much does this cost?"))
    assert profile.approved_answer("cost").answer in reply.messages
    assert reply.pending_item == "reason_category"  # back to the checklist


def test_unknown_question_gets_honest_answer_and_contact(conductor, llm, profile):
    llm.script(turn_result(intent="ask-question", approved="none"))
    _, reply = conductor.respond(IntakeState(), Turn(text="is parking free?"))
    assert any("don't have an answer" in m and profile.contact.phone in m for m in reply.messages)


@pytest.mark.parametrize(
    "intent,needle,action",
    [
        ("request-reschedule", "scheduling step", None),
        ("request-human", "(555) 010-0199", None),
        ("withdraw-consent", "nothing is deleted unless you confirm", "show_withdrawal"),
        ("out-of-scope", "only help with getting you set up", None),
    ],
)
def test_each_intent_has_its_handling(conductor, llm, intent, needle, action):
    llm.script(turn_result(intent=intent))
    _, reply = conductor.respond(IntakeState(), Turn(text="something"))
    assert any(needle in m for m in reply.messages)
    if action:
        assert action in reply.actions
    assert reply.pending_item == "reason_category"


def test_express_distress_signals_high_stress_and_continues(conductor, llm):
    llm.script(turn_result(intent="express-distress", reply="That sounds really hard."))
    _, reply = conductor.respond(IntakeState(), Turn(text="I'm so overwhelmed"))
    assert reply.signals.high_stress
    assert "That sounds really hard." in reply.messages
    assert reply.pending_item == "reason_category"


def test_llm_crisis_label_pauses(conductor, llm, profile):
    llm.script(turn_result(intent="crisis-risk"))
    state, reply = conductor.respond(IntakeState(), Turn(text="I have no reason to keep going"))
    assert state.crisis_paused and reply.signals.crisis
    assert reply.messages == [profile.crisis.pause_message]


def test_unambiguous_crisis_language_pauses_without_calling_the_llm(conductor, llm):
    state, reply = conductor.respond(IntakeState(), Turn(text="I want to kill myself"))
    assert state.crisis_paused and reply.signals.crisis
    assert llm.calls == []


def test_paused_intake_asks_nothing_until_resumed(conductor, llm):
    state, _ = conductor.respond(IntakeState(), Turn(text="I want to end my life"))
    state, reply = conductor.respond(state, Turn(item="reason_category", value="anxiety"))
    assert reply.pending_item is None and "reason_category" not in state.answers


def test_ambiguous_idiom_gets_check_in_then_no_continues_with_support(conductor, llm):
    state, reply = conductor.respond(IntakeState(), Turn(text="this form is killing me"))
    assert reply.pending_item == CHECK_IN_ITEM and reply.signals.check_in
    assert llm.calls == []
    state, reply = conductor.respond(state, Turn(item=CHECK_IN_ITEM, value="no"))
    assert not state.crisis_paused and reply.signals.high_stress
    assert reply.pending_item == "reason_category"


def test_check_in_yes_pauses(conductor):
    state, _ = conductor.respond(IntakeState(), Turn(text="I can't go on"))
    state, reply = conductor.respond(state, Turn(text="yes"))
    assert state.crisis_paused and reply.signals.crisis


def test_unclear_check_in_answer_asks_again(conductor):
    state, _ = conductor.respond(IntakeState(), Turn(text="I can't go on"))
    state, reply = conductor.respond(state, Turn(text="hmm"))
    assert state.check_in_pending and reply.pending_item == CHECK_IN_ITEM


def test_safety_question_yes_pauses(conductor):
    state = IntakeState()
    for item, value in STRUCTURED_ANSWERS[:4]:
        state, _ = conductor.respond(state, Turn(item=item, value=value))
    state, reply = conductor.respond(state, Turn(item="safety", value="yes"))
    assert state.crisis_paused and reply.signals.crisis


def test_high_self_rated_distress_signals_high_stress(conductor):
    _, reply = conductor.respond(IntakeState(), Turn(item="distress", value=5))
    assert reply.signals.high_stress


def test_invalid_button_value_is_not_stored(conductor):
    state, reply = conductor.respond(IntakeState(), Turn(item="duration", value="forever"))
    assert "duration" not in state.answers
    assert "didn't catch that" in reply.messages[0]


@pytest.mark.parametrize(
    "failure", [FailureKind.TIMEOUT, FailureKind.SERVER_ERROR, FailureKind.UNREACHABLE]
)
def test_llm_failure_degrades_to_scripted_question(conductor, llm, failure):
    llm.fail_next(failure)
    state, reply = conductor.respond(IntakeState(), Turn(text="anxiety"))
    assert reply.signals.llm_failure == failure.value
    assert any("having trouble" in m for m in reply.messages)
    assert "offer_retry_assistant" in reply.actions
    assert state.answers.get("reason_category") == "anxiety"  # scripted match still works
    assert not state.scripted_mode


def test_two_failures_switch_to_scripted_mode_and_intake_still_completes(conductor, llm):
    llm.fail_next(FailureKind.TIMEOUT, times=2)
    state, _ = run(conductor, IntakeState(), Turn(text="anxiety"), Turn(text="long story"))
    assert state.scripted_mode
    calls_before = len(llm.calls)
    for item, value in STRUCTURED_ANSWERS[2:]:
        state, reply = conductor.respond(
            state,
            Turn(text=value.replace("_", " ") if item != "availability" else "Mornings")
            if item in ("reason_text",)
            else Turn(item=item, value=value),
        )
    assert reply.complete and conductor.is_complete(state)
    assert len(llm.calls) == calls_before  # scripted mode never calls the LLM


def test_retry_assistant_leaves_scripted_mode(conductor, llm):
    llm.fail_next(FailureKind.TIMEOUT, times=2)
    state, _ = run(conductor, IntakeState(), Turn(text="a"), Turn(text="b"))
    state, _ = conductor.respond(state, Turn(retry_assistant=True))
    assert not state.scripted_mode and state.llm_failures == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"intent": "book-now", "answers": [], "approved_answer_id": "none", "reply": "ok"},
        {
            "intent": "ask-question",
            "answers": [],
            "approved_answer_id": "free_lunch",
            "reply": "ok",
        },
        {"answers": []},
    ],
)
def test_invalid_llm_output_is_never_shown_or_saved(conductor, llm, bad):
    llm.script(bad)
    state, reply = conductor.respond(IntakeState(), Turn(text="hello there friend"))
    assert reply.signals.llm_failure == "invalid_output"
    assert "made_up" not in state.answers and "duration" not in state.answers
    assert all(m != "ok" for m in reply.messages)


def test_invalid_extracted_values_are_dropped_and_valid_ones_kept(conductor, llm):
    """ISSUE-004 regression. Found by: walking the UI on real Claude Haiku — "mostly anxiety
    honestly, the last few months" came back with duration "3_6_months" (not an allowed
    value) and the whole turn failed, losing the valid "anxiety" too."""
    llm.script(
        turn_result(
            answers=[("reason_category", "anxiety"), ("duration", "3_6_months"), ("made_up", "x")],
            reply="Thank you for sharing that.",
        )
    )
    state, reply = conductor.respond(IntakeState(), Turn(text="mostly anxiety, last few months"))
    assert reply.signals.llm_failure is None
    assert state.answers == {"reason_category": "anxiety"}  # invalid values never saved
    assert reply.pending_item == "reason_text"  # the checklist asks on; duration comes later
    assert "Thank you for sharing that." in reply.messages


def test_system_prompt_requires_exact_allowed_values(conductor, llm):
    llm.script(turn_result())
    conductor.respond(IntakeState(), Turn(text="hi there"))
    assert "exactly one of the allowed values" in llm.calls[0][0]


def test_scripted_mode_matches_option_words_without_guessing(conductor, llm):
    """ISSUE-005 regression. Found by: same walk — in scripted fallback "mostly anxiety
    honestly" did not match the option "Anxiety or worry", so the Client was asked again."""
    state = IntakeState(scripted_mode=True)
    state, _ = conductor.respond(state, Turn(text="mostly anxiety honestly"))
    assert state.answers.get("reason_category") == "anxiety"
    ambiguous = IntakeState(scripted_mode=True)
    ambiguous, reply = conductor.respond(ambiguous, Turn(text="anxiety and grief and sleep"))
    assert "reason_category" not in ambiguous.answers  # several options: ask, don't guess
    assert reply.pending_item == "reason_category"


def test_unsafe_llm_reply_is_replaced(conductor, llm):
    llm.script(
        turn_result(
            answers=[("reason_category", "low_mood")],
            reply="Your appointment is confirmed for Monday at 3pm.",
        )
    )
    _, reply = conductor.respond(IntakeState(), Turn(text="low mood"))
    assert reply.signals.output_check_tripped
    assert not any("confirmed" in m for m in reply.messages)


def test_llm_safety_yes_extraction_pauses(conductor, llm):
    llm.script(turn_result(answers=[("safety", "yes")]))
    state, _ = conductor.respond(IntakeState(), Turn(text="yes I have"))
    assert state.crisis_paused


def test_validate_value_rules(profile):
    item = profile.item
    assert validate_value(item("distress"), "6") is None
    assert validate_value(item("distress"), " 2 ") == 2
    assert validate_value(item("availability"), ["evenings", "mornings"]) == [
        "mornings",
        "evenings",
    ]
    assert validate_value(item("availability"), "mornings,nights") is None
    assert validate_value(item("session_format"), "Video") == "video"
    assert validate_value(item("duration"), DECLINED) is None  # not declinable
    assert validate_value(item("reason_text"), "Prefer not to say") == DECLINED
    assert validate_value(item("reason_text"), "x" * 1001) is None


def test_system_prompt_marks_answered_items_and_pending(conductor, llm):
    llm.script(turn_result())
    state = IntakeState(answers={"reason_category": "grief"})
    conductor.respond(state, Turn(text="since my mum died"))
    system = llm.calls[0][0]
    assert "reason_category" in system and "[answered]" in system
    assert "PENDING_ITEM: reason_text" in system


def test_heuristic_fake_supports_keyless_end_to_end(profile):
    llm = FakeLLM(HeuristicResponder(profile))
    conductor = IntakeConductor(profile, llm, timeout=5)
    state, reply = conductor.respond(IntakeState(), Turn(text="mostly anxiety honestly"))
    assert state.answers.get("reason_category") == "anxiety"
    _, reply = conductor.respond(state, Turn(text="can I talk to a real person?"))
    assert reply.signals.intent == "request-human"


def test_llm_failure_object_is_an_exception():
    assert isinstance(LLMFailure(FailureKind.TIMEOUT), Exception)
