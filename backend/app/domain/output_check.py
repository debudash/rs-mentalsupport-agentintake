"""Output check: a deterministic filter on every LLM reply before a Client sees it.

Blocks commitments (specific times, dates, prices, "confirmed", "you will be seen"),
clinical language (diagnoses, medication) and Identity-detail-like strings. Patterns are
deliberately narrow; a table of benign sentences in the tests must keep passing.
"""

import re

from app.domain.masking import contains_identity_like

_WEEKDAY = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_MONTH = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
)

_BLOCKS = [
    # commitments: specific times, dates, prices, bookings made or promised
    re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm|a\.m\.|p\.m\.)", re.I),
    re.compile(rf"\b(?:on|this|next)\s+{_WEEKDAY}\b", re.I),
    re.compile(rf"\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?\b", re.I),
    re.compile(r"[$£€]\s?\d", re.I),
    re.compile(r"\b\d+\s?(?:dollars|usd)\b", re.I),
    re.compile(
        r"\b(?:appointment|booking|session|consultation)\s+(?:is|has been|was)\s+"
        r"(?:confirmed|booked|scheduled|reserved|cancel+ed)\b",
        re.I,
    ),
    re.compile(r"\bi(?:'ve| have| will|'ll)?\s+(?:booked|scheduled|reserved|cancel+ed)\b", re.I),
    re.compile(r"\byou(?:'ll| will) be seen\b", re.I),
    re.compile(r"\b(?:i|we) (?:guarantee|promise)\b", re.I),
    re.compile(r"\bguaranteed\b", re.I),
    # clinical language
    re.compile(r"\bdiagnos(?:e|es|ed|is|ing)\b", re.I),
    re.compile(
        r"\byou\s+(?:have|might have|may have|probably have|likely have|sound like you have)\s+"
        r"(?:clinical\s+)?(?:depression|an anxiety disorder|anxiety disorder|ptsd|bipolar|ocd|"
        r"adhd|bpd|a personality disorder|schizophrenia)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:antidepressants?|ssris?|snris?|benzodiazepines?|sertraline|fluoxetine|prozac|"
        r"zoloft|lexapro|escitalopram|xanax|alprazolam|lorazepam|ativan|bupropion|"
        r"wellbutrin|lithium|dosage|prescri(?:be|bed|ption))\b",
        re.I,
    ),
    re.compile(r"\b\d+\s?mg\b", re.I),
]

SAFE_FALLBACK_LINE = "Thank you for sharing that."


def is_safe(reply: str) -> bool:
    if contains_identity_like(reply):
        return False
    return not any(pattern.search(reply) for pattern in _BLOCKS)


def check(reply: str) -> tuple[str, bool]:
    """Return (text to show, tripped)."""
    reply = reply.strip()
    if not reply:
        return SAFE_FALLBACK_LINE, False
    if is_safe(reply):
        return reply, False
    return SAFE_FALLBACK_LINE, True
