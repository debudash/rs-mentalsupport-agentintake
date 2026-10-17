"""Double-booking under real concurrency, on real Postgres.

Twenty Clients try to book the same Slot at the same instant, each on its own connection;
the partial unique index must let exactly one win. Runs where TEST_POSTGRES_URL points at a
database migrated to head (local Supabase, or the Postgres service in CI).
"""

import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Booking, Client, Clinician, Slot
from app.profile import get_profile
from app.scheduling import Scheduling, SlotTaken

URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = [pytest.mark.postgres, pytest.mark.skipif(not URL, reason="TEST_POSTGRES_URL not set")]

RACERS = 20


@pytest.fixture
def world():
    engine = create_engine(URL, pool_size=RACERS + 5, max_overflow=0)
    make = sessionmaker(bind=engine, expire_on_commit=False)
    tag = uuid.uuid4().hex[:8]
    with make() as s:
        clinician = Clinician(name=f"Race Test {tag}", gender="woman", languages=["english"])
        s.add(clinician)
        s.flush()
        slot = Slot(
            clinician_id=clinician.id,
            format="video",
            starts_at=datetime.now(UTC) + timedelta(days=3),
        )
        s.add(slot)
        clients = [f"race-{tag}-{i:02d}" for i in range(RACERS)]
        s.add_all(Client(account_id=c, support_shown=[]) for c in clients)
        s.commit()
        ids = (clinician.id, slot.id)
    yield make, ids[1], clients
    with make() as s:
        s.execute(delete(Booking).where(Booking.slot_id == ids[1]))
        s.execute(delete(Client).where(Client.account_id.in_(clients)))
        s.execute(delete(Slot).where(Slot.id == ids[1]))
        s.execute(delete(Clinician).where(Clinician.id == ids[0]))
        s.commit()
    engine.dispose()


def test_simultaneous_bookings_for_one_slot_have_exactly_one_winner(world):
    make, slot_id, clients = world
    barrier = threading.Barrier(RACERS)
    results: dict[str, object] = {}

    def race(client_id: str) -> None:
        with make() as session:
            scheduling = Scheduling(session, get_profile())
            barrier.wait()  # release all twenty at the same instant
            results[client_id] = scheduling.book(client_id, slot_id)

    threads = [threading.Thread(target=race, args=(c,)) for c in clients]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    winners = [c for c, r in results.items() if isinstance(r, Booking)]
    losers = [c for c, r in results.items() if isinstance(r, SlotTaken)]
    assert len(results) == RACERS
    assert len(winners) == 1, winners
    assert len(losers) == RACERS - 1
    with Session(make.kw["bind"]) as s:
        active = s.scalar(
            select(func.count())
            .select_from(Booking)
            .where(Booking.slot_id == slot_id, Booking.status == "active")
        )
    assert active == 1
