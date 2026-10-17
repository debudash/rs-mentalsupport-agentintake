"""Scheduling through its interface: window, filters, double-booking, reschedule, .ics."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import Booking, Client, Clinician, Slot
from app.scheduling import (
    OutsideWindow,
    Scheduling,
    SlotFilters,
    SlotTaken,
    calendar_file,
    filters_from_assessment,
)

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)  # a Monday


@pytest.fixture
def world(db):
    ana = Clinician(name="Ana Rivera", gender="woman", languages=["english", "spanish"])
    ben = Clinician(name="Ben Okafor", gender="man", languages=["english"])
    db.add_all([ana, ben])
    db.flush()
    slots = {
        "soon": Slot(clinician_id=ana.id, starts_at=NOW + timedelta(hours=1), format="video"),
        "morning_video": Slot(
            clinician_id=ana.id, starts_at=NOW + timedelta(days=1, hours=2), format="video"
        ),  # 14:00 UTC = 10:00 ET
        "evening_person": Slot(
            clinician_id=ben.id, starts_at=NOW + timedelta(days=2, hours=10), format="in_person"
        ),  # 22:00 UTC = 18:00 ET
        "far": Slot(clinician_id=ben.id, starts_at=NOW + timedelta(days=20), format="video"),
    }
    db.add_all(slots.values())
    for cid in ("c1", "c2"):
        db.add(Client(account_id=cid, support_shown=[]))
    db.commit()
    return slots


@pytest.fixture
def sched(db, profile):
    return Scheduling(db, profile, clock=lambda: NOW)


def ids(found):
    return {s.id for s in found}


def test_window_excludes_short_notice_and_far_future(sched, world):
    found = ids(sched.open_slots(SlotFilters(show_all=True), "UTC"))
    assert world["morning_video"].id in found and world["evening_person"].id in found
    assert world["soon"].id not in found and world["far"].id not in found


def test_filters_by_format_time_of_day_gender_language(sched, world):
    morning = sched.open_slots(SlotFilters(availability=("mornings",)), "America/New_York")
    assert ids(morning) == {world["morning_video"].id}
    in_person = sched.open_slots(SlotFilters(session_format="in_person"), "UTC")
    assert ids(in_person) == {world["evening_person"].id}
    spanish = sched.open_slots(SlotFilters(clinician_language="spanish"), "UTC")
    assert ids(spanish) == {world["morning_video"].id}
    man = sched.open_slots(SlotFilters(clinician_gender="man"), "UTC")
    assert ids(man) == {world["evening_person"].id}


def test_filters_from_assessment_ignores_no_preference():
    f = filters_from_assessment(
        {
            "session_format": "either",
            "availability": ["evenings"],
            "clinician_gender": "prefer_not_to_say",
            "clinician_language": "no_preference",
        }
    )
    assert f.session_format is None and f.availability == ("evenings",)
    assert f.clinician_gender is None and f.clinician_language is None


def test_book_then_double_booking_is_rejected_with_alternatives(sched, world):
    slot = world["morning_video"]
    booking = sched.book("c1", slot.id)
    assert isinstance(booking, Booking) and booking.reference
    taken = sched.book("c2", slot.id)
    assert isinstance(taken, SlotTaken)
    assert world["evening_person"].id in ids(taken.alternatives)
    assert slot.id not in ids(taken.alternatives)


def test_booked_slot_is_no_longer_open(sched, world):
    sched.book("c1", world["morning_video"].id)
    assert world["morning_video"].id not in ids(sched.open_slots(SlotFilters(show_all=True), "UTC"))


def test_reschedule_frees_the_old_slot(sched, world, db):
    sched.book("c1", world["morning_video"].id)
    sched.book("c1", world["evening_person"].id)
    active = db.scalars(select(Booking).where(Booking.status == "active")).all()
    assert [b.slot_id for b in active] == [world["evening_person"].id]
    assert isinstance(sched.book("c2", world["morning_video"].id), Booking)


def test_rebooking_same_slot_is_idempotent(sched, world):
    first = sched.book("c1", world["morning_video"].id)
    again = sched.book("c1", world["morning_video"].id)
    assert again.id == first.id


@pytest.mark.parametrize("key", ["soon", "far"])
def test_booking_outside_window_is_rejected(sched, world, key):
    assert isinstance(sched.book("c1", world[key].id), OutsideWindow)


def test_unknown_slot_is_rejected(sched, world):
    assert isinstance(sched.book("c1", "nope"), OutsideWindow)


def test_failed_booking_keeps_the_previous_one(sched, world):
    sched.book("c2", world["evening_person"].id)
    sched.book("c1", world["morning_video"].id)
    assert isinstance(sched.book("c1", world["evening_person"].id), SlotTaken)
    current = sched.current_booking("c1")
    assert current[0].slot_id == world["morning_video"].id


def test_calendar_file(sched, world, profile):
    sched.book("c1", world["morning_video"].id)
    booking, slot, clinician = sched.current_booking("c1")
    ics = calendar_file(booking, slot, clinician, profile)
    assert ics.startswith("BEGIN:VCALENDAR") and "DTSTART:20261020T140000Z" in ics
    assert "DTEND:20261020T143000Z" in ics and "Ana Rivera" in ics


def test_seed_tops_up_slots_idempotently(db):
    from app.seed import seed

    first = seed()
    second = seed()
    assert first["slots_added"] > 50 and second["slots_added"] == 0
    assert len(db.scalars(select(Clinician)).all()) == 4
