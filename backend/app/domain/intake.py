"""Intake conductor: one Client message in, the assistant's turn out.

Per message: Safety screen -> (structured answer, or masking -> exactly ONE structured LLM
call -> validation) -> output check -> next question from the server-held checklist.

The checklist, not the LLM, decides what is still missing and when Intake is complete.
The LLM interprets free text, extracts answers, picks an Approved answer and writes a short
acknowledgement. Any LLM failure or invalid output degrades to scripted questions.
"""

import time
from dataclasses import dataclass, field, replace
from typing import Any

from pydantic import BaseModel, ValidationError

from app.domain import masking, output_check
from app.domain.safety import SafetyScreen, Screen, parse_check_in_answer
from app.llm.port import ChatMessage, FailureKind, LLMFailure, LLMPort
from app.profile import AssessmentItem, ServiceProfile

INTENTS = [
    "provide-details",
    "ask-question",
    "request-reschedule",
    "express-distress",
    "crisis-risk",
    "request-human",
    "withdraw-consent",
    "out-of-scope",
]
DECLINED = "prefer_not_to_say"
CHECK_IN_ITEM = "check_in"
HIGH_DISTRESS = 4
MAX_TEXT = 1000
HISTORY_TURNS = 6
FAILURES_BEFORE_SCRIPTED = 2


@dataclass
class IntakeState:
    answers: dict[str, Any] = field(default_factory=dict)
    history: list[ChatMessage] = field(default_factory=list)
    check_in_pending: bool = False
    llm_failures: int = 0
    scripted_mode: bool = False
    crisis_paused: bool = False


@dataclass(frozen=True)
class Turn:
    text: str | None = None
    item: str | None = None
    value: Any = None
    retry_assistant: bool = False


@dataclass
class Signals:
    intent: str | None = None
    high_stress: bool = False
    crisis: bool = False
    check_in: bool = False
    llm_used: bool = False
    llm_failure: str | None = None
    llm_ms: float | None = None
    fallback: bool = False
    output_check_tripped: bool = False


@dataclass
class Reply:
    messages: list[str]
    pending_item: str | None
    input_kind: str | None
    quick_replies: list[dict[str, str]]
    complete: bool = False
    actions: list[str] = field(default_factory=list)
    signals: Signals = field(default_factory=Signals)


class _Answer(BaseModel):
    item: str
    value: str


class IntakeTurn(BaseModel):
    """The single structured result of the per-message LLM call."""

    intent: str
    answers: list[_Answer]
    approved_answer_id: str
    reply: str


def validate_value(item: AssessmentItem, raw: Any) -> Any | None:
    """Normalised value for an Assessment item, or None if it is not valid."""
    if isinstance(raw, str) and raw.strip().lower().replace(" ", "_") == DECLINED:
        return DECLINED if item.declinable else None
    if item.type == "text":
        if not isinstance(raw, str):
            return None
        value = raw.strip()
        return value if 0 < len(value) <= MAX_TEXT else None
    if item.type == "scale":
        try:
            value = int(str(raw).strip())
        except ValueError:
            return None
        return value if item.min <= value <= item.max else None
    by_label = {label.lower(): key for key, label in item.options.items()}

    def one(token: str) -> str | None:
        token = str(token).strip()
        if token in item.options:
            return token
        return by_label.get(token.lower())

    if item.type == "choice":
        return one(raw) if isinstance(raw, str | int) else None
    tokens = raw if isinstance(raw, list) else str(raw).split(",")
    keys = [one(t) for t in tokens if str(t).strip()]
    if not keys or any(k is None for k in keys):
        return None
    return sorted(set(keys), key=list(item.options).index)


def _scripted_match(item: AssessmentItem, text: str) -> Any | None:
    """Best-effort reading of free text without the LLM (scripted mode)."""
    direct = validate_value(item, text)
    if direct is not None or item.type == "text":
        return direct
    lowered = text.lower()
    if item.type == "scale":
        digits = [c for c in lowered if c.isdigit()]
        return validate_value(item, digits[0]) if digits else None
    hits = [k for k, label in item.options.items() if label.lower() in lowered]
    if not hits:
        return None
    return hits if item.type == "multichoice" else (hits[0] if len(hits) == 1 else None)


class IntakeConductor:
    def __init__(self, profile: ServiceProfile, llm: LLMPort, timeout: float):
        self._profile = profile
        self._llm = llm
        self._timeout = timeout
        self._screen = SafetyScreen(profile.crisis.unambiguous, profile.crisis.ambiguous)
        self._items = {i.id: i for i in profile.assessment}
        self._schema = self._build_schema()

    # ---- checklist -----------------------------------------------------------------

    def next_item(self, state: IntakeState) -> AssessmentItem | None:
        return next((i for i in self._profile.assessment if i.id not in state.answers), None)

    def is_complete(self, state: IntakeState) -> bool:
        return self.next_item(state) is None

    def prompt_for(self, state: IntakeState, lead: list[str] | None = None) -> Reply:
        """The reply that asks for the next missing item (or closes Intake)."""
        messages = list(lead or [])
        if state.crisis_paused:
            return Reply(
                messages=[self._profile.crisis.pause_message],
                pending_item=None,
                input_kind=None,
                quick_replies=[],
            )
        if state.check_in_pending:
            messages.append(self._profile.crisis.check_in_question)
            return Reply(
                messages=messages,
                pending_item=CHECK_IN_ITEM,
                input_kind="choice",
                quick_replies=[
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No, I'm just stressed"},
                ],
            )
        item = self.next_item(state)
        if item is None:
            messages.append(
                "Thank you — that's everything I need for now. Next, we'll confirm your details."
            )
            return Reply(messages, None, None, [], complete=True)
        messages.append(item.question)
        quick = [{"value": k, "label": v} for k, v in item.options.items()]
        if item.type == "scale":
            quick = [{"value": str(n), "label": str(n)} for n in range(item.min, item.max + 1)]
        if item.declinable:
            quick.append({"value": DECLINED, "label": "Prefer not to say"})
        return Reply(messages, item.id, item.type, quick)

    # ---- the turn ------------------------------------------------------------------

    def respond(self, state: IntakeState, turn: Turn) -> tuple[IntakeState, Reply]:
        state = replace(state, answers=dict(state.answers), history=list(state.history))
        signals = Signals()

        if turn.retry_assistant:
            state.scripted_mode = False
            state.llm_failures = 0
            return state, self._with(self.prompt_for(state), signals)

        if state.crisis_paused:
            signals.crisis = True
            return state, self._with(self.prompt_for(state), signals)

        if turn.text:
            screened = self._screen.screen(turn.text)
            if screened is Screen.CRISIS:
                return self._crisis(state, signals)
            if screened is Screen.CHECK_IN and not state.check_in_pending:
                state.check_in_pending = True
                signals.check_in = True
                return state, self._with(self.prompt_for(state), signals)

        if state.check_in_pending:
            return self._answer_check_in(state, turn, signals)

        if turn.item is not None:
            return self._structured(state, turn.item, turn.value, signals)

        if not turn.text or not turn.text.strip():
            return state, self._with(self.prompt_for(state), signals)

        if state.scripted_mode:
            return self._scripted(state, turn.text, signals, lead=[])
        return self._llm_turn(state, turn.text, signals)

    # ---- paths ---------------------------------------------------------------------

    def _crisis(self, state: IntakeState, signals: Signals) -> tuple[IntakeState, Reply]:
        state.crisis_paused = True
        state.check_in_pending = False
        signals.crisis = True
        signals.intent = signals.intent or "crisis-risk"
        return state, self._with(self.prompt_for(state), signals)

    def _answer_check_in(
        self, state: IntakeState, turn: Turn, signals: Signals
    ) -> tuple[IntakeState, Reply]:
        if turn.item == CHECK_IN_ITEM:
            answer = {"yes": True, "no": False}.get(str(turn.value).lower())
        else:
            answer = parse_check_in_answer(turn.text or "")
        if answer is None:
            return state, self._with(self.prompt_for(state), signals)
        state.check_in_pending = False
        if answer:
            return self._crisis(state, signals)
        signals.high_stress = True
        lead = ["Thank you for letting me know. Let's take this one step at a time."]
        return state, self._with(self.prompt_for(state, lead), signals)

    def _store(
        self, state: IntakeState, item: AssessmentItem, value: Any, signals: Signals
    ) -> bool:
        """Store a validated value; returns True if it started a Crisis pause."""
        state.answers[item.id] = value
        if item.id == "safety" and value == "yes":
            return True
        if item.id == "distress" and isinstance(value, int) and value >= HIGH_DISTRESS:
            signals.high_stress = True
        return False

    def _structured(
        self, state: IntakeState, item_id: str, raw: Any, signals: Signals
    ) -> tuple[IntakeState, Reply]:
        item = self._items.get(item_id)
        value = validate_value(item, raw) if item else None
        if value is None:
            lead = ["Sorry, I didn't catch that. Could you choose one of the options?"]
            return state, self._with(self.prompt_for(state, lead), signals)
        signals.intent = "provide-details"
        if self._store(state, item, value, signals):
            return self._crisis(state, signals)
        return state, self._with(self.prompt_for(state), signals)

    def _scripted(
        self, state: IntakeState, text: str, signals: Signals, lead: list[str]
    ) -> tuple[IntakeState, Reply]:
        signals.fallback = True
        item = self.next_item(state)
        if item is None:
            return state, self._with(self.prompt_for(state, lead), signals)
        value = _scripted_match(item, text)
        if value is None:
            lead = lead + ["Please choose one of the options below, or type your answer."]
            return state, self._with(self.prompt_for(state, lead), signals)
        if self._store(state, item, value, signals):
            return self._crisis(state, signals)
        return state, self._with(self.prompt_for(state, lead), signals)

    def _llm_turn(
        self, state: IntakeState, text: str, signals: Signals
    ) -> tuple[IntakeState, Reply]:
        pending = self.next_item(state)
        masked = masking.mask(text)
        history = state.history[-HISTORY_TURNS:] + [ChatMessage("user", masked)]
        signals.llm_used = True
        started = time.perf_counter()
        try:
            raw = self._llm.complete(
                self._system_prompt(state, pending),
                history,
                self._schema,
                "intake_turn",
                self._timeout,
            )
            result = self._validate(raw)
        except LLMFailure as failure:
            signals.llm_ms = (time.perf_counter() - started) * 1000
            signals.llm_failure = failure.kind.value
            return self._on_failure(state, text, signals)
        signals.llm_ms = (time.perf_counter() - started) * 1000
        state.llm_failures = 0
        state.history = history
        signals.intent = result.intent
        return self._apply(state, result, signals)

    def _on_failure(
        self, state: IntakeState, text: str, signals: Signals
    ) -> tuple[IntakeState, Reply]:
        state.llm_failures += 1
        if state.llm_failures >= FAILURES_BEFORE_SCRIPTED:
            state.scripted_mode = True
        lead = ["I'm having trouble right now — let's keep going with a simple question."]
        state, reply = self._scripted(state, text, signals, lead=lead)
        reply.actions.append("offer_retry_assistant")
        return state, reply

    def _validate(self, raw: dict) -> IntakeTurn:
        try:
            result = IntakeTurn.model_validate(raw)
        except ValidationError as exc:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "schema") from exc
        if result.intent not in INTENTS:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "intent")
        known_answer = result.approved_answer_id == "none" or self._profile.approved_answer(
            result.approved_answer_id
        )
        if not known_answer:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "approved answer")
        # ISSUE-004: models sometimes invent a near-miss value ("3_6_months" for "the last
        # few months"). Failing the whole turn also threw away the valid answers and showed
        # an error. Each extracted value is checked on its own: invalid ones are dropped —
        # never saved — and the checklist simply asks for that item. A bad intent or
        # approved-answer id still fails the turn, since the reply would depend on it.
        result.answers = [
            a
            for a in result.answers
            if a.item in self._items and validate_value(self._items[a.item], a.value) is not None
        ]
        return result

    def _apply(
        self, state: IntakeState, result: IntakeTurn, signals: Signals
    ) -> tuple[IntakeState, Reply]:
        contact = self._profile.contact
        if result.intent == "crisis-risk":
            return self._crisis(state, signals)

        lead: list[str] = []
        actions: list[str] = []
        ack, tripped = output_check.check(result.reply)
        signals.output_check_tripped = tripped

        for answer in result.answers:
            item = self._items[answer.item]
            if self._store(state, item, validate_value(item, answer.value), signals):
                return self._crisis(state, signals)

        if result.intent == "provide-details":
            lead.append(ack)
        elif result.intent == "ask-question":
            approved = self._profile.approved_answer(result.approved_answer_id)
            if approved:
                lead.append(approved.answer)
            else:
                lead.append(
                    "I don't have an answer to that, but our team can help: "
                    f"{contact.phone} or {contact.email} ({contact.hours})."
                )
        elif result.intent == "request-reschedule":
            lead.append(
                "You can choose or change your appointment time on the scheduling step, "
                "which comes right after these questions."
            )
        elif result.intent == "express-distress":
            signals.high_stress = True
            lead.append(ack)
        elif result.intent == "request-human":
            lead.append(
                f"Of course. You can reach our team by phone at {contact.phone} or by email at "
                f"{contact.email} ({contact.hours})."
            )
        elif result.intent == "withdraw-consent":
            lead.append(
                "You can withdraw and delete everything at any time. I've opened that option "
                "for you — nothing is deleted unless you confirm."
            )
            actions.append("show_withdrawal")
        else:  # out-of-scope
            lead.append("I can only help with getting you set up for counseling here.")

        if result.intent != "provide-details" and not lead:
            lead.append(ack)
        reply = self.prompt_for(state, lead)
        reply.actions.extend(actions)
        if signals.llm_used:
            state.history = state.history + [ChatMessage("assistant", " ".join(reply.messages))]
        return state, self._with(reply, signals)

    # ---- prompt + schema -----------------------------------------------------------

    def _system_prompt(self, state: IntakeState, pending: AssessmentItem | None) -> str:
        lines = [
            f"You are the intake assistant for {self._profile.service.name}, an outpatient "
            "counseling service. You help an adult sign up. Be warm, brief and plain.",
            "Classify the client's latest message into exactly one intent, extract any answers "
            "it gives to the intake items, pick an approved answer id if they asked a question "
            "that one of them answers (else 'none'), and write a one-sentence acknowledgement.",
            "Rules for the reply: one short sentence; never ask a question (the system asks the "
            "next one); never diagnose or mention medication; never promise times, dates, prices "
            "or outcomes; never repeat personal details.",
            "Intents: provide-details (answers an intake item), ask-question (asks about the "
            "service), request-reschedule (wants to change or pick an appointment), "
            "express-distress (says they feel overwhelmed, anxious, upset), crisis-risk (any sign "
            "of risk of harming themselves or others), request-human (wants a real person), "
            "withdraw-consent (wants to stop or delete their data), out-of-scope (anything else).",
            "Intake items (id: question -> allowed values):",
        ]
        for item in self._profile.assessment:
            if item.type in ("choice", "multichoice"):
                allowed = ", ".join(item.options)
                if item.type == "multichoice":
                    allowed += " (comma-separated, one or more)"
            elif item.type == "scale":
                allowed = f"integer {item.min}-{item.max}"
            else:
                allowed = "the client's own words"
            if item.declinable:
                allowed += f", or {DECLINED}"
            done = " [answered]" if item.id in state.answers else ""
            lines.append(f"- {item.id}: {item.question} -> {allowed}{done}")
        lines.append("Approved answers (id: question):")
        lines += [f"- {a.id}: {a.question}" for a in self._profile.approved_answers]
        lines.append(
            "Only extract answers the client actually gave. Each value must be exactly one of "
            "the allowed values listed for that item; if what they said doesn't fit one "
            "exactly, leave that item out. Personal details appear as placeholders like [phone]."
        )
        lines.append(f"PENDING_ITEM: {pending.id if pending else 'none'}")
        return "\n".join(lines)

    def _build_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": INTENTS},
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "item": {"type": "string", "enum": list(self._items)},
                            "value": {"type": "string"},
                        },
                        "required": ["item", "value"],
                        "additionalProperties": False,
                    },
                },
                "approved_answer_id": {
                    "type": "string",
                    "enum": ["none"] + [a.id for a in self._profile.approved_answers],
                },
                "reply": {"type": "string"},
            },
            "required": ["intent", "answers", "approved_answer_id", "reply"],
            "additionalProperties": False,
        }

    @staticmethod
    def _with(reply: Reply, signals: Signals) -> Reply:
        reply.signals = signals
        return reply
