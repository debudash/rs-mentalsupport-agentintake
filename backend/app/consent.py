"""Consent & Withdrawal.

grant(): records Onboarding consent (required), ID scan consent (optional) and the 18+
confirmation, each in the identity-free Consent log.
withdraw(): deletes everything about the Client — Assessment, Intake conversation, Identity
details, progress, Booking (freeing the Slot) — deletes the Account in Supabase Auth and our
Account row, removes Supabase's auth audit-log rows for that Account where we can, and
writes the Consent log entry that proves it happened.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app import journeys
from app.auth_admin import AuthAdmin
from app.db.models import (
    Account,
    Assessment,
    Booking,
    Client,
    ConsentLogEntry,
    DailyCounter,
    IdentityDetails,
    IntakeMessage,
)
from app.domain import identity
from app.profile import ServiceProfile
from app.telemetry import log


@dataclass(frozen=True)
class ConsentRejected:
    reason: str


@dataclass(frozen=True)
class DeletionReceipt:
    reference: str
    deleted_at: datetime
    auth_account_deleted: bool
    auth_audit_rows_deleted: bool


def bump_counter(db: Session, name: str) -> None:
    day = datetime.now(UTC).date().isoformat()
    counter = db.get(DailyCounter, (day, name))
    if counter is None:
        db.add(DailyCounter(day=day, name=name, count=1))
    else:
        counter.count += 1


def get_or_create_client(db: Session, account_id: str) -> Client:
    client = db.get(Client, account_id)
    if client is None:
        client = Client(account_id=account_id, support_shown=[])
        db.add(client)
        db.flush()
    return client


def grant(
    db: Session,
    profile: ServiceProfile,
    account_id: str,
    onboarding: bool,
    id_scan: bool,
    age_confirmed: bool,
) -> Client | ConsentRejected:
    if not age_confirmed:
        return ConsentRejected(identity.adults_only(profile.service.minimum_age))
    if not onboarding:
        return ConsentRejected("Onboarding consent is needed to arrange your consultation.")
    client = get_or_create_client(db, account_id)
    client.age_confirmed = True
    versions = profile.consents
    if client.onboarding_consent_version != versions["onboarding"].version:
        client.onboarding_consent_version = versions["onboarding"].version
        db.add(
            ConsentLogEntry(
                account_id=account_id,
                consent="onboarding",
                action="granted",
                version=versions["onboarding"].version,
            )
        )
    set_id_scan(db, profile, client, id_scan)
    journeys.record(db, account_id, "consent_completed")
    db.commit()
    return client


def set_id_scan(db: Session, profile: ServiceProfile, client: Client, allowed: bool) -> None:
    version = profile.consents["id_scan"].version
    if allowed and client.id_scan_consent_version != version:
        client.id_scan_consent_version = version
        db.add(
            ConsentLogEntry(
                account_id=client.account_id, consent="id_scan", action="granted", version=version
            )
        )
    elif not allowed and client.id_scan_consent_version:
        client.id_scan_consent_version = None
        db.add(
            ConsentLogEntry(
                account_id=client.account_id, consent="id_scan", action="withdrawn", version=version
            )
        )


def _delete_auth_audit_rows(db: Session, account_id: str) -> bool:
    """Supabase keeps auth events (with email, IP and user agent) in auth.audit_log_entries.

    Only meaningful on the Supabase Postgres; elsewhere there is nothing to delete.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return True
    try:
        with db.begin_nested():
            # ISSUE-001: sign-up and admin-deletion events name the user in
            # payload.traits.user_id, with the system (00000000-...) as actor_id. Matching
            # actor_id alone left those rows — including the user's email — behind after
            # Withdrawal. Match the user in either place.
            db.execute(
                text(
                    "delete from auth.audit_log_entries "
                    "where payload->>'actor_id' = :id or payload->'traits'->>'user_id' = :id"
                ),
                {"id": account_id},
            )
        return True
    except Exception as exc:  # noqa: BLE001 - reported in the receipt, never fatal
        log("withdrawal_audit_rows_not_deleted", error_type=type(exc).__name__)
        return False


def withdraw(db: Session, auth_admin: AuthAdmin, account_id: str) -> DeletionReceipt:
    reference = secrets.token_hex(5).upper()
    journeys.unlink(db, account_id)
    for model in (Booking, IntakeMessage, IdentityDetails, Assessment):
        db.execute(delete(model).where(model.client_id == account_id))
    db.execute(delete(Client).where(Client.account_id == account_id))
    db.execute(delete(Account).where(Account.id == account_id))
    db.add(
        ConsentLogEntry(account_id=account_id, consent="all", action="deleted", receipt=reference)
    )
    bump_counter(db, "withdrawals")
    db.commit()

    auth_deleted = auth_admin.delete_user(account_id)
    audit_deleted = _delete_auth_audit_rows(db, account_id)
    db.commit()
    log("withdrawal_completed", auth_deleted=auth_deleted, audit_rows_deleted=audit_deleted)
    return DeletionReceipt(
        reference=reference,
        deleted_at=datetime.now(UTC),
        auth_account_deleted=auth_deleted,
        auth_audit_rows_deleted=audit_deleted,
    )
