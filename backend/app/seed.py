"""Seed: fictional Clinicians, Slots for the booking window, and demo Accounts.

Re-runnable: existing Clinicians and Accounts are kept; Slots are topped up so the next 14
days always have open times. Demo Accounts are created in Supabase Auth (email confirmed)
when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set.

Run: python -m app.seed
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db.models import (
    Account,
    Assessment,
    Booking,
    Client,
    Clinician,
    IdentityDetails,
    Slot,
)
from app.db.session import get_sessionmaker

SERVICE_TZ = ZoneInfo("America/New_York")

CLINICIANS = [
    # name, gender, languages, local hours, login email
    (
        "Ana Rivera",
        "woman",
        ["english", "spanish"],
        [9, 10, 11, 14, 15],
        "clinician.ana@riverside.test",
    ),
    ("Ben Okafor", "man", ["english"], [12, 13, 16, 17, 18], "clinician.ben@riverside.test"),
    ("Sam Lee", "nonbinary", ["english"], [8, 9, 17, 18, 19], "clinician.sam@riverside.test"),
    ("Grace Chen", "woman", ["english"], [10, 11, 13, 15, 16], "clinician.grace@riverside.test"),
]

BOOKED_DEMO = "client.booked@riverside.test"  # finished onboarding, booked with Ana

DEMO_ACCOUNTS = [
    ("client.demo@riverside.test", "DemoClient!2026", "client"),
    (BOOKED_DEMO, "DemoClient!2026", "client"),
    ("operator.demo@riverside.test", "DemoOperator!2026", "operator"),
] + [(c[4], "DemoClinician!2026", "clinician") for c in CLINICIANS]


def _supabase_user(email: str, password: str) -> str | None:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    base = settings.server_supabase_url.rstrip("/")
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    created = httpx.post(
        f"{base}/auth/v1/admin/users",
        headers=headers,
        timeout=15,
        json={"email": email, "password": password, "email_confirm": True},
    )
    if created.status_code in (200, 201):
        return created.json()["id"]
    # Already exists: find it.
    page = httpx.get(
        f"{base}/auth/v1/admin/users", headers=headers, timeout=15, params={"per_page": 1000}
    )
    page.raise_for_status()
    for user in page.json().get("users", []):
        if user.get("email") == email:
            return user["id"]
    return None


def seed(today: date | None = None) -> dict:
    session = get_sessionmaker()()
    summary = {"clinicians": 0, "slots_added": 0, "accounts": []}
    try:
        by_name = {c.name: c for c in session.scalars(select(Clinician))}
        for name, gender, languages, _, _ in CLINICIANS:
            if name not in by_name:
                clinician = Clinician(name=name, gender=gender, languages=languages)
                session.add(clinician)
                by_name[name] = clinician
                summary["clinicians"] += 1
        session.flush()

        existing = {(s.clinician_id, _aware(s.starts_at)) for s in session.scalars(select(Slot))}
        start = today or datetime.now(SERVICE_TZ).date()
        for offset in range(0, 15):
            day = start + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            for index, (name, _, _, hours, _) in enumerate(CLINICIANS):
                clinician = by_name[name]
                for n, hour in enumerate(hours):
                    starts = datetime.combine(day, time(hour), SERVICE_TZ).astimezone(UTC)
                    if (clinician.id, starts) in existing:
                        continue
                    fmt = "video" if (n + index + offset) % 3 else "in_person"
                    session.add(Slot(clinician_id=clinician.id, starts_at=starts, format=fmt))
                    summary["slots_added"] += 1

        for email, password, role in DEMO_ACCOUNTS:
            account_id = _supabase_user(email, password)
            if account_id is None:
                continue
            account = session.get(Account, account_id) or Account(id=account_id)
            account.role = role
            session.add(account)
            if role == "clinician":
                for name, _, _, _, login in CLINICIANS:
                    if login == email:
                        by_name[name].account_id = account_id
            summary["accounts"].append(email)
            if email == BOOKED_DEMO:
                session.flush()
                _booked_client(session, account_id, by_name["Ana Rivera"], start)
        session.commit()
    finally:
        session.close()
    return summary


def _booked_client(session, account_id: str, clinician: Clinician, start: date) -> None:
    """A fictional Client who completed Onboarding, so the Clinician view has data."""
    if session.get(Client, account_id) is not None:
        return
    session.add(
        Client(
            account_id=account_id,
            first_name="Sam",
            age_confirmed=True,
            onboarding_consent_version="2026-10-1",
            support_shown=[],
        )
    )
    session.flush()
    session.add(
        Assessment(
            client_id=account_id,
            answers={
                "reason_category": "stress",
                "duration": "6_12_months",
                "distress": 3,
                "session_format": "video",
                "availability": ["mornings"],
                "clinician_gender": "no_preference",
                "clinician_language": "english",
            },
            reason_text="Work pressure has been building and I'm not sleeping well.",
            safety="no",
            completed_at=datetime.now(UTC),
        )
    )
    session.add(
        IdentityDetails(
            client_id=account_id,
            legal_name="Sam Example",
            date_of_birth="1988-06-01",
            address="10 Demo St, Springfield, RS 10001",
            source="manual",
            edited={},
        )
    )
    soonest = session.scalars(
        select(Slot)
        .where(
            Slot.clinician_id == clinician.id,
            Slot.format == "video",
            Slot.starts_at >= datetime.combine(start + timedelta(days=2), time(0), SERVICE_TZ),
        )
        .order_by(Slot.starts_at)
    ).first()
    if soonest is not None:
        session.add(Booking(client_id=account_id, slot_id=soonest.id, reference="DEMO0001"))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


if __name__ == "__main__":
    result = seed()
    print(f"Clinicians added: {result['clinicians']}; slots added: {result['slots_added']}")
    if result["accounts"]:
        print("Demo accounts ready:", ", ".join(result["accounts"]))
    else:
        print("Demo accounts skipped (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set).")
