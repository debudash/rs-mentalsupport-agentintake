"""Scheduling: open Slots, Booking with the double-booking guarantee, calendar file.

The database guarantees at most one active Booking per Slot (partial unique index), so two
simultaneous requests for the same Slot cannot both succeed; the loser gets "slot taken"
with the nearest alternatives. Rescheduling replaces the Client's Booking in one
transaction.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Booking, Clinician, Slot
from app.profile import ServiceProfile

TIME_OF_DAY = {"mornings": range(0, 12), "afternoons": range(12, 17), "evenings": range(17, 24)}


@dataclass(frozen=True)
class SlotFilters:
    session_format: str | None = None  # video | in_person | either
    availability: tuple[str, ...] = ()  # mornings | afternoons | evenings
    clinician_gender: str | None = None
    clinician_language: str | None = None
    show_all: bool = False


@dataclass(frozen=True)
class OpenSlot:
    id: str
    starts_at: datetime
    format: str
    clinician_id: str
    clinician_name: str


@dataclass(frozen=True)
class SlotTaken:
    alternatives: list[OpenSlot]


@dataclass(frozen=True)
class OutsideWindow:
    reason: str


def zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def filters_from_assessment(answers: dict, show_all: bool = False) -> SlotFilters:
    def pref(value):
        return None if value in (None, "no_preference", "prefer_not_to_say", "either") else value

    availability = answers.get("availability") or []
    return SlotFilters(
        session_format=pref(answers.get("session_format")),
        availability=tuple(availability if isinstance(availability, list) else [availability]),
        clinician_gender=pref(answers.get("clinician_gender")),
        clinician_language=pref(answers.get("clinician_language")),
        show_all=show_all,
    )


class Scheduling:
    def __init__(self, db: Session, profile: ServiceProfile, clock=lambda: datetime.now(UTC)):
        self._db = db
        self._service = profile.service
        self._clock = clock

    def _window(self) -> tuple[datetime, datetime]:
        now = self._clock()
        return (
            now + timedelta(hours=self._service.booking_min_notice_hours),
            now + timedelta(days=self._service.booking_window_days),
        )

    def _all_open(self, exclude_client: str | None = None) -> list[OpenSlot]:
        start, end = self._window()
        taken = select(Booking.slot_id).where(Booking.status == "active")
        if exclude_client:
            taken = taken.where(Booking.client_id != exclude_client)
        rows = self._db.execute(
            select(Slot, Clinician)
            .join(Clinician, Clinician.id == Slot.clinician_id)
            .where(Slot.starts_at >= start, Slot.starts_at <= end, Slot.id.not_in(taken))
            .order_by(Slot.starts_at)
        ).all()
        return [OpenSlot(s.id, _aware(s.starts_at), s.format, c.id, c.name) for s, c in rows]

    def open_slots(self, filters: SlotFilters, tz_name: str | None) -> list[OpenSlot]:
        slots = self._all_open()
        if filters.show_all:
            return slots
        tz = zone(tz_name)
        clinicians = {c.id: c for c in self._db.scalars(select(Clinician))}

        def keep(slot: OpenSlot) -> bool:
            if filters.session_format and slot.format != filters.session_format:
                return False
            if filters.availability:
                hour = slot.starts_at.astimezone(tz).hour
                if not any(hour in TIME_OF_DAY.get(b, ()) for b in filters.availability):
                    return False
            clinician = clinicians[slot.clinician_id]
            if filters.clinician_gender and clinician.gender != filters.clinician_gender:
                return False
            wanted_language = filters.clinician_language
            return not wanted_language or wanted_language in clinician.languages

        return [s for s in slots if keep(s)]

    def current_booking(self, client_id: str) -> tuple[Booking, Slot, Clinician] | None:
        row = self._db.execute(
            select(Booking, Slot, Clinician)
            .join(Slot, Slot.id == Booking.slot_id)
            .join(Clinician, Clinician.id == Slot.clinician_id)
            .where(Booking.client_id == client_id, Booking.status == "active")
        ).first()
        return tuple(row) if row else None

    def book(self, client_id: str, slot_id: str) -> Booking | SlotTaken | OutsideWindow:
        slot = self._db.get(Slot, slot_id)
        if slot is None:
            return OutsideWindow("That time is no longer available.")
        start, end = self._window()
        if not start <= _aware(slot.starts_at) <= end:
            return OutsideWindow(
                f"Please choose a time at least {self._service.booking_min_notice_hours} hours "
                f"from now and within the next {self._service.booking_window_days} days."
            )
        try:
            previous = self._db.scalars(
                select(Booking).where(Booking.client_id == client_id, Booking.status == "active")
            ).first()
            if previous is not None:
                if previous.slot_id == slot_id:
                    return previous
                previous.status = "replaced"
                self._db.flush()
            booking = Booking(
                client_id=client_id, slot_id=slot_id, reference=secrets.token_hex(4).upper()
            )
            self._db.add(booking)
            self._db.commit()
            return booking
        except IntegrityError:
            self._db.rollback()
            return SlotTaken(self._nearest(slot, client_id))

    def _nearest(self, slot: Slot, client_id: str, count: int = 3) -> list[OpenSlot]:
        target = _aware(slot.starts_at)
        candidates = [s for s in self._all_open(exclude_client=client_id) if s.id != slot.id]
        candidates.sort(key=lambda s: abs((s.starts_at - target).total_seconds()))
        return sorted(candidates[:count], key=lambda s: s.starts_at)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def calendar_file(
    booking: Booking, slot: Slot, clinician: Clinician, profile: ServiceProfile
) -> str:
    start = _aware(slot.starts_at).astimezone(UTC)
    end = start + timedelta(minutes=profile.service.consultation_minutes)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    fmt = "%Y%m%dT%H%M%SZ"
    where = "Video (link sent by your clinician)" if slot.format == "video" else "In person"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//rs-assist//onboarding//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{booking.id}@rs-assist",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:Initial consultation — {profile.service.name}",
        f"DESCRIPTION:With {clinician.name}. Reference {booking.reference}.",
        f"LOCATION:{where}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
