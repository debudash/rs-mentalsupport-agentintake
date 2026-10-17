"""Safety screen: deterministic crisis-language check that runs before any LLM call.

Two tiers (from the Service profile):
- unambiguous self-harm / harm-to-others language -> "crisis" (immediate Crisis pause)
- ambiguous idioms ("this form is killing me")     -> "check_in" (ask what they meant)
It never depends on the LLM, so it keeps working when the provider is down.
"""

import re
from enum import StrEnum


class Screen(StrEnum):
    CLEAR = "clear"
    CHECK_IN = "check_in"
    CRISIS = "crisis"


def _normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = text.replace("'", "")  # "don't" and "dont" both become "dont"
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compile(phrases: list[str]) -> re.Pattern[str]:
    parts = [r"\b" + re.escape(_normalise(p)).replace(r"\ ", r"\s+") + r"\b" for p in phrases]
    return re.compile("|".join(parts))


class SafetyScreen:
    def __init__(self, unambiguous: list[str], ambiguous: list[str]):
        self._crisis = _compile(unambiguous)
        self._check_in = _compile(ambiguous)

    def screen(self, message: str) -> Screen:
        text = _normalise(message)
        if not text:
            return Screen.CLEAR
        if self._crisis.search(text):
            return Screen.CRISIS
        if self._check_in.search(text):
            return Screen.CHECK_IN
        return Screen.CLEAR


_YES = re.compile(r"^\s*(yes|yeah|yep|yup|i do|i am|sort of|kind of|maybe|sometimes)\b", re.I)
_NO = re.compile(r"^\s*(no|nope|nah|not really|not at all|i'?m fine|just stressed)\b", re.I)


def parse_check_in_answer(text: str) -> bool | None:
    """True = yes (risk), False = no, None = unclear (ask again with buttons).

    "maybe"/"sometimes" count as yes: when in doubt, offer crisis resources.
    """
    if _YES.search(text):
        return True
    if _NO.search(text):
        return False
    return None
