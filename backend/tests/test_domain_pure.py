"""Pure modules: Safety screen, masking, output check, Onboarding engine, Support triggers,
Service profile."""

from pathlib import Path

import pytest
import yaml

from app.domain import masking, output_check, support
from app.domain.onboarding import Action, Facts, Step, check, state
from app.domain.safety import SafetyScreen, Screen, parse_check_in_answer
from app.profile import PROFILE_PATH, load_profile

# ---- Safety screen -------------------------------------------------------------------


@pytest.fixture
def screen(profile):
    return SafetyScreen(profile.crisis.unambiguous, profile.crisis.ambiguous)


@pytest.mark.parametrize(
    "text",
    [
        "I want to kill myself",
        "honestly i dont want to be here anymore",
        "I've been thinking about suicide",
        "sometimes I hurt myself",
        "I just want to die",
        "I'm going to end my life",
        "I DON’T WANT TO LIVE",
        "I keep thinking about self-harm",
    ],
)
def test_unambiguous_language_is_crisis(screen, text):
    assert screen.screen(text) is Screen.CRISIS


@pytest.mark.parametrize(
    "text",
    [
        "this form is killing me",
        "I can't go on like this",
        "I'm done with everything",
        "honestly what's the point",
        "I just want to disappear for a while",
    ],
)
def test_ambiguous_idioms_get_a_check_in(screen, text):
    assert screen.screen(text) is Screen.CHECK_IN


@pytest.mark.parametrize(
    "text",
    [
        "I'm really stressed about work",
        "it's been about three months",
        "I feel anxious most days",
        "",
        "my skills need work",
        "I killed it at my presentation",
    ],
)
def test_plain_stress_is_clear(screen, text):
    assert screen.screen(text) is Screen.CLEAR


@pytest.mark.parametrize(
    "text,expected",
    [
        ("yes", True),
        ("Yeah sometimes", True),
        ("maybe", True),
        ("no", False),
        ("No, just stressed", False),
        ("not really", False),
        ("what do you mean", None),
    ],
)
def test_check_in_answers(text, expected):
    assert parse_check_in_answer(text) is expected


# ---- masking ---------------------------------------------------------------------------


def test_masking_replaces_contact_details():
    text = (
        "Call me on (555) 123-4567 or jane.doe@example.com, I was born 03/14/1990 and "
        "live at 42 Elm Street"
    )
    masked = masking.mask(text)
    for secret in ("555", "jane.doe", "1990", "42 Elm"):
        assert secret not in masked
    assert "[phone]" in masked and "[email]" in masked
    assert "[date]" in masked and "[address]" in masked


def test_masking_leaves_ordinary_text_alone():
    text = "It has been about 3 months and I feel anxious 4 out of 5"
    assert masking.mask(text) == text


# ---- output check ----------------------------------------------------------------------

BENIGN = [
    "It sounds like the last 3 months have been really hard.",
    "Thank you for sharing that.",
    "Take your time — there's no rush.",
    "That makes sense, and you're not alone in feeling this way.",
    "Got it, mornings and evenings work best for you.",
    "I hear you; reaching out takes courage.",
]
BLOCKED = [
    "Your appointment is confirmed for Tuesday.",
    "I've booked you in with Ana.",
    "You'll be seen at 3pm tomorrow.",
    "Sessions cost $120 each.",
    "It sounds like you have depression.",
    "Sertraline might help with that.",
    "I can diagnose this for you.",
    "I guarantee you'll feel better.",
    "See you on Monday!",
    "Your email jane@example.com is noted.",
]


@pytest.mark.parametrize("reply", BENIGN)
def test_output_check_passes_benign_replies(reply):
    assert output_check.check(reply) == (reply, False)


@pytest.mark.parametrize("reply", BLOCKED)
def test_output_check_blocks_commitments_clinical_and_identity(reply):
    shown, tripped = output_check.check(reply)
    assert tripped and shown == output_check.SAFE_FALLBACK_LINE


def test_output_check_empty_reply_gets_safe_line():
    assert output_check.check("   ") == (output_check.SAFE_FALLBACK_LINE, False)


# ---- Onboarding engine -----------------------------------------------------------------


def test_steps_progress_in_order():
    assert state(Facts()).step is Step.CONSENT
    assert state(Facts(consent_given=True)).step is Step.INTAKE
    assert state(Facts(True, True)).step is Step.IDENTITY
    assert state(Facts(True, True, True)).step is Step.SCHEDULING
    done = state(Facts(True, True, True, True))
    assert done.step is Step.DONE and done.complete
    assert done.completed == (Step.CONSENT, Step.INTAKE, Step.IDENTITY, Step.SCHEDULING)


def test_later_steps_are_gated():
    rejection = check(Facts(consent_given=True), Action.BOOK)
    assert rejection and "intake" in rejection.reason
    assert check(Facts(), Action.INTAKE_MESSAGE) is not None
    assert check(Facts(True, True), Action.CONFIRM_IDENTITY) is None


def test_completed_steps_stay_available_for_rescheduling():
    assert check(Facts(True, True, True, True), Action.BOOK) is None
    assert check(Facts(True, True, True), Action.INTAKE_MESSAGE) is None


def test_crisis_pause_blocks_everything_but_resume_and_withdraw():
    paused = Facts(consent_given=True, crisis_paused=True)
    assert check(paused, Action.INTAKE_MESSAGE) is not None
    assert check(paused, Action.BOOK) is not None
    assert check(paused, Action.RESUME) is None
    assert check(paused, Action.WITHDRAW) is None
    assert check(Facts(consent_given=True), Action.RESUME) is not None


# ---- Support triggers ------------------------------------------------------------------

E = support.Event


@pytest.mark.parametrize(
    "event,expected",
    [
        (E("idle", "intake", idle_seconds=45), support.Trigger.LONG_PAUSE),
        (E("idle", "intake", idle_seconds=44), None),
        (E("idle", "intake", idle_seconds=120, step_complete=True), None),
        (E("upload_failed", "identity"), support.Trigger.UPLOAD_PROBLEM),
        (E("high_stress", "intake"), support.Trigger.HIGH_STRESS),
        (E("page_view", "intake"), None),
        (E("typing", "intake"), None),
    ],
)
def test_each_trigger_maps_to_its_content_and_nothing_else(event, expected):
    assert support.decide(event, [], crisis_paused=False) is expected


def test_trigger_shows_once_per_step():
    event = E("idle", "intake", idle_seconds=60)
    shown = [support.shown_key("intake", support.Trigger.LONG_PAUSE)]
    assert support.decide(event, shown, False) is None
    assert support.decide(E("idle", "identity", idle_seconds=60), shown, False) is not None


def test_nothing_shows_during_crisis_pause():
    assert support.decide(E("high_stress", "intake"), [], crisis_paused=True) is None


# ---- Service profile -------------------------------------------------------------------


def test_profile_loads_and_has_required_parts(profile):
    assert profile.item("safety").type == "choice"
    assert len(profile.approved_answers) >= 15
    assert profile.consents["onboarding"].required


def test_broken_profile_fails_at_load(tmp_path: Path):
    data = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    data["assessment"] = [i for i in data["assessment"] if i["id"] != "safety"]
    broken = tmp_path / "broken.yaml"
    broken.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="safety"):
        load_profile(broken)


def test_choice_item_without_options_is_rejected(tmp_path: Path):
    data = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    data["assessment"][0]["options"] = {}
    broken = tmp_path / "broken.yaml"
    broken.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="options"):
        load_profile(broken)
