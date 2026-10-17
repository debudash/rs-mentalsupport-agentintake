"""Deterministic masking of contact-type details before any text reaches an LLM provider.

Masks emails, phone numbers, dates and street addresses. Known limit (documented in the
README): names typed in free text are not reliably masked.
"""

import re

_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)")
DATE = re.compile(
    r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    + _MONTHS
    + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{1,2}(?:st|nd|rd|th)?\s+"
    + _MONTHS
    + r"\.?,?\s+\d{4})\b",
    re.I,
)
ADDRESS = re.compile(
    r"\b\d{1,6}\s+(?:[A-Za-z0-9.'-]+\s+){0,4}"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way|place|pl|"
    r"terrace|ter|circle|cir|highway|hwy|parkway|pkwy)\b\.?",
    re.I,
)

_RULES = ((EMAIL, "[email]"), (PHONE, "[phone]"), (DATE, "[date]"), (ADDRESS, "[address]"))


def mask(text: str) -> str:
    for pattern, placeholder in _RULES:
        text = pattern.sub(placeholder, text)
    return text


def contains_identity_like(text: str) -> bool:
    return any(pattern.search(text) for pattern, _ in _RULES)
