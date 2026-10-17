"""Fake LLM adapter: no network, no key.

Two uses:
- tests queue exact results or failures (FakeLLM.script / .fail_next)
- keyless graders get a keyword heuristic that behaves like a small intake model, so the
  whole flow runs end to end with LLM_PROVIDER=fake. It is deliberately simple; the real
  quality numbers come from the Anthropic run.
"""

import re
import time
from collections import deque

from app.llm.port import ChatMessage, FailureKind, LLMFailure
from app.profile import ServiceProfile

_PENDING = re.compile(r"^PENDING_ITEM: (\S+)$", re.M)

_HUMAN = re.compile(
    r"\b(real person|human|someone real|talk to (?:a|an) (?:person|someone))\b", re.I
)
_RESCHEDULE = re.compile(
    r"\b(reschedul\w*|change (?:my|the) (?:appointment|time|booking)|move my appointment)\b", re.I
)
_WITHDRAW = re.compile(
    r"\b(delete (?:my|all my) (?:data|information|account)|withdraw|stop using my data|"
    r"don'?t want (?:to do this|you to keep))\b",
    re.I,
)
_DISTRESS = re.compile(
    r"\b(overwhelm\w*|anxious|panick\w*|scared|terrified|stressed|exhausted|"
    r"so hard|too much|can'?t cope|struggling|nervous|on edge|falling apart)\b",
    re.I,
)
_OFF_TOPIC = re.compile(
    r"\b(poem|weather|joke|recipe|football|stock|bitcoin|code|homework|movie|song)\b", re.I
)
_STOP = set(
    [
        "a",
        "an",
        "the",
        "i",
        "my",
        "me",
        "is",
        "are",
        "do",
        "does",
        "can",
        "how",
        "what",
        "who",
        "when",
        "will",
        "to",
        "of",
        "for",
        "it",
        "this",
        "that",
    ]
)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']+", text.lower()) if w not in _STOP and len(w) > 2}


class HeuristicResponder:
    def __init__(self, profile: ServiceProfile):
        self._profile = profile

    def _match_option(self, item_id: str, text: str) -> str | None:
        item = self._profile.item(item_id)
        lowered = text.lower()
        if item.type == "scale":
            match = re.search(r"\b([1-5])\b", lowered)
            return match.group(1) if match else None
        if item.type == "text":
            return text.strip() or None
        hits = [
            key
            for key, label in item.options.items()
            if key.replace("_", " ") in lowered
            or label.lower() in lowered
            or any(w in lowered for w in _words(label) if len(w) > 4)
        ]
        if not hits:
            return None
        return ",".join(hits) if item.type == "multichoice" else hits[0]

    def _faq(self, text: str) -> str:
        words = _words(text)
        best, best_score = "none", 0
        for answer in self._profile.approved_answers:
            score = len(words & _words(answer.question))
            if score > best_score:
                best, best_score = answer.id, score
        return best if best_score >= 1 else "none"

    def __call__(self, system: str, messages: list[ChatMessage]) -> dict:
        text = messages[-1].content if messages else ""
        pending = _PENDING.search(system)
        result = {
            "intent": "out-of-scope",
            "answers": [],
            "approved_answer_id": "none",
            "reply": "",
        }
        if _WITHDRAW.search(text):
            result["intent"] = "withdraw-consent"
        elif _HUMAN.search(text):
            result["intent"] = "request-human"
        elif _RESCHEDULE.search(text):
            result["intent"] = "request-reschedule"
        elif "?" in text and self._faq(text) != "none":
            result.update(intent="ask-question", approved_answer_id=self._faq(text))
        elif _DISTRESS.search(text) and not (
            pending and self._match_option(pending.group(1), text)
        ):
            result.update(intent="express-distress", reply="That sounds really hard.")
        elif _OFF_TOPIC.search(text):
            result["intent"] = "out-of-scope"
        elif pending and (value := self._match_option(pending.group(1), text)):
            result.update(
                intent="provide-details",
                answers=[{"item": pending.group(1), "value": value}],
                reply="Thank you.",
            )
        elif "?" in text:
            result["intent"] = "ask-question"
        return result


class FakeLLM:
    provider = "fake"

    def __init__(self, responder=None, delay_ms: int = 0, model: str = "fake-intake-1"):
        self.model = model
        self._responder = responder
        self._delay = delay_ms / 1000
        self._queue: deque = deque()
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    def script(self, *results: dict | LLMFailure) -> "FakeLLM":
        self._queue.extend(results)
        return self

    def fail_next(self, kind: FailureKind = FailureKind.TIMEOUT, times: int = 1) -> "FakeLLM":
        self._queue.extend(LLMFailure(kind) for _ in range(times))
        return self

    def complete(
        self,
        system: str,
        messages: list[ChatMessage],
        schema: dict,
        schema_name: str,
        timeout: float,
    ) -> dict:
        self.calls.append((system, list(messages)))
        if self._delay:
            time.sleep(min(self._delay, timeout))
        if self._queue:
            item = self._queue.popleft()
            if isinstance(item, LLMFailure):
                raise item
            return item
        if self._responder is None:
            raise LLMFailure(FailureKind.INVALID_OUTPUT, "nothing scripted")
        return self._responder(system, messages)

    def ping(self) -> bool:
        return True
