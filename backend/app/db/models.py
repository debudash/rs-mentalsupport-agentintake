"""Database schema. Portable across Postgres (deployed) and SQLite (tests).

Sensitive values use EncryptedText. Logs and telemetry tables hold no personal data.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.crypto import EncryptedText


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Account(Base):
    """Our view of a Supabase Auth user: just the role."""

    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="client")  # client|clinician|operator
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Client(Base):
    __tablename__ = "clients"
    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    first_name: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    age_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    onboarding_consent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    id_scan_consent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    crisis_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    check_in_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_failures: Mapped[int] = mapped_column(Integer, default=0)
    scripted_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    gentle_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    support_shown: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Assessment(Base):
    __tablename__ = "assessments"
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.account_id", ondelete="CASCADE"), primary_key=True
    )
    # Non-sensitive structured answers (category, duration, distress, format, availability...)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    reason_text: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    safety: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IntakeMessage(Base):
    """The Intake conversation. Deleted when Intake completes."""

    __tablename__ = "intake_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.account_id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # client|client_choice|assistant
    body: Mapped[str] = mapped_column(EncryptedText)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdentityDetails(Base):
    __tablename__ = "identity_details"
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.account_id", ondelete="CASCADE"), primary_key=True
    )
    legal_name: Mapped[str] = mapped_column(EncryptedText)
    date_of_birth: Mapped[str] = mapped_column(EncryptedText)  # ISO date
    address: Mapped[str] = mapped_column(EncryptedText)
    source: Mapped[str] = mapped_column(String(16))  # scan|manual
    edited: Mapped[dict] = mapped_column(JSON, default=dict)  # field -> bool, no values
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Clinician(Base):
    __tablename__ = "clinicians"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(80))
    gender: Mapped[str] = mapped_column(String(16))
    languages: Mapped[list] = mapped_column(JSON, default=list)


class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    clinician_id: Mapped[str] = mapped_column(String(36), ForeignKey("clinicians.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    format: Mapped[str] = mapped_column(String(16))  # video|in_person


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clients.account_id", ondelete="CASCADE"), index=True
    )
    slot_id: Mapped[str] = mapped_column(String(36), ForeignKey("slots.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|replaced
    reference: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    __table_args__ = (
        # The double-booking guarantee: at most one active Booking per Slot...
        Index(
            "uq_bookings_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        # ...and at most one active Booking per Client.
        Index(
            "uq_bookings_active_client",
            "client_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )


class ConsentLogEntry(Base):
    """Permanent and identity-free: proof of what was granted, withdrawn or deleted."""

    __tablename__ = "consent_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    consent: Mapped[str] = mapped_column(String(16))  # onboarding|id_scan|all
    action: Mapped[str] = mapped_column(String(16))  # granted|withdrawn|deleted
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    receipt: Mapped[str | None] = mapped_column(String(16), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AccessLogEntry(Base):
    __tablename__ = "access_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    clinician_account_id: Mapped[str] = mapped_column(String(36), index=True)
    client_account_id: Mapped[str] = mapped_column(String(36))
    booking_id: Mapped[str] = mapped_column(String(36))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TimingRecord(Base):
    """One identity-free record per request: no account, no text."""

    __tablename__ = "timing_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    endpoint: Mapped[str] = mapped_column(String(64), index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    total_ms: Mapped[float] = mapped_column()
    llm_ms: Mapped[float | None] = mapped_column(nullable=True)
    db_ms: Mapped[float | None] = mapped_column(nullable=True)
    ocr_ms: Mapped[float | None] = mapped_column(nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DailyCounter(Base):
    """Aggregate-only counts (Crisis pauses, Withdrawals) with no link to anyone."""

    __tablename__ = "daily_counters"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class JourneyLink(Base):
    """Account -> anonymous Journey. Deleted at Withdrawal, which leaves the Journey's
    events with no way back to the person."""

    __tablename__ = "journey_links"
    account_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    journey_id: Mapped[str] = mapped_column(String(36), unique=True, default=new_id)


class JourneyEvent(Base):
    """Funnel analytics: Step, event and time only. No answers, no Identity details."""

    __tablename__ = "journey_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    journey_id: Mapped[str] = mapped_column(String(36), index=True)
    event: Mapped[str] = mapped_column(String(32), index=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # booleans/labels only
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Heartbeat(Base):
    __tablename__ = "heartbeat"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvalReport(Base):
    """Latest eval scorecards, so the dashboard can show AI quality in deployment."""

    __tablename__ = "eval_reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16))  # ocr|intent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    summary: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
