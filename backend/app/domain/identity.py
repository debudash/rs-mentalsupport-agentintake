"""Identity details the Client confirms on the review screen: validation and the adults-only
rule. Pure functions, no I/O."""

from dataclasses import dataclass
from datetime import date

from app.ocr.parse import clean_name, parse_date

FIELDS = ("legal_name", "date_of_birth", "address")


@dataclass(frozen=True)
class Confirmed:
    legal_name: str
    date_of_birth: str  # ISO
    address: str


def validate(legal_name: str, date_of_birth: str, address: str) -> Confirmed | dict[str, str]:
    """The cleaned details, or a message per invalid field."""
    errors = {}
    name = clean_name(legal_name) or (
        legal_name.strip() if len(legal_name.strip().split()) >= 2 else None
    )
    if not name:
        errors["legal_name"] = "Please enter your full legal name (first and last)."
    iso = parse_date(date_of_birth)
    if not iso:
        errors["date_of_birth"] = "Please enter a valid date of birth, for example 1990-03-14."
    address = " ".join(address.split())
    if len(address) < 8 or not any(c.isdigit() for c in address):
        errors["address"] = "Please enter your full address, including the street number."
    if errors:
        return errors
    return Confirmed(legal_name=name, date_of_birth=iso, address=address)


def age(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def is_adult(iso_dob: str, minimum_age: int, today: date) -> bool:
    return age(date.fromisoformat(iso_dob), today) >= minimum_age


def adults_only(minimum_age: int) -> str:
    """The one wording of the adults-only rule (Consent and Identity both use it)."""
    return f"This service is for adults aged {minimum_age} and over."


def adults_only_stop(minimum_age: int) -> str:
    """The polite stop when the date of birth shows an under-age Client."""
    return (
        f"{adults_only(minimum_age)[:-1]}, so we can't continue your sign-up. A school "
        "counselor or family doctor is a good place to start, and 988 is free and available "
        "to everyone, any time."
    )


def edited_flags(edited: dict[str, bool]) -> dict[str, bool]:
    """Per-field edited true/false for the OCR correction metric; unknown keys dropped."""
    return {k: bool(v) for k, v in edited.items() if k in FIELDS}
