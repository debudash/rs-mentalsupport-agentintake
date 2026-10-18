"""Access control: who is calling, with which role, and what they may see.

Verifies the Supabase login token (JWKS for asymmetric keys, or the legacy HS256 secret),
creates our Account row on first sight (role: client), and scopes Clinician reads to
Bookings in their own Slots — writing the Access log for every Clinician record view.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import journeys
from app.config import Settings, get_settings
from app.db.models import (
    AccessLogEntry,
    Account,
    Assessment,
    Booking,
    Client,
    Clinician,
    ConsentLogEntry,
    Slot,
)


class Unauthenticated(Exception):
    pass


class Forbidden(Exception):
    pass


class Withdrawn(Exception):
    """A still-valid token for an Account that withdrew and was deleted."""


class TokenVerifier(Protocol):
    def verify(self, token: str) -> str: ...  # returns the Account id (JWT "sub")


class SupabaseTokenVerifier:
    def __init__(self, supabase_url: str, jwt_secret: str = ""):
        self._secret = jwt_secret
        self._jwks = (
            jwt.PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")
            if supabase_url
            else None
        )

    def verify(self, token: str) -> str:
        try:
            # Legacy / local projects sign with a shared HS256 secret; newer projects use
            # asymmetric keys published as JWKS. The token's header says which.
            algorithm = jwt.get_unverified_header(token).get("alg")
            if algorithm == "HS256":
                if not self._secret:
                    raise Unauthenticated("HS256 token but no SUPABASE_JWT_SECRET configured")
                claims = jwt.decode(
                    token, self._secret, algorithms=["HS256"], audience="authenticated"
                )
            elif self._jwks is not None:
                key = self._jwks.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    key.key,
                    algorithms=["ES256", "RS256", "EdDSA"],
                    audience="authenticated",
                )
            else:
                raise Unauthenticated("auth is not configured")
        except jwt.PyJWTError as exc:
            raise Unauthenticated("invalid token") from exc
        sub = claims.get("sub")
        if not sub:
            raise Unauthenticated("token has no subject")
        return sub


class StaticSecretVerifier(SupabaseTokenVerifier):
    """Test adapter: HS256 tokens signed with a known secret."""

    def __init__(self, secret: str):
        super().__init__("", secret)


@lru_cache
def get_verifier() -> TokenVerifier:
    settings: Settings = get_settings()
    return SupabaseTokenVerifier(settings.server_supabase_url, settings.supabase_jwt_secret)


@dataclass(frozen=True)
class Caller:
    account_id: str
    role: str  # client | clinician | operator


def identify(db: Session, verifier: TokenVerifier, authorization: str | None) -> Caller:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("missing bearer token")
    account_id = verifier.verify(authorization.split(" ", 1)[1].strip())
    account = db.get(Account, account_id)
    if account is None:
        withdrawn = db.scalars(
            select(ConsentLogEntry.id).where(
                ConsentLogEntry.account_id == account_id, ConsentLogEntry.action == "deleted"
            )
        ).first()
        if withdrawn:
            # A still-unexpired token for an Account that withdrew: never recreate it.
            # ISSUE-016: this raised Unauthenticated (401), but PRD story 78 asks every data
            # endpoint to answer "not found" for a withdrawn Client. A separate exception
            # lets main.py map it to 404 while bad or expired tokens stay 401.
            raise Withdrawn()
        account = Account(id=account_id, role="client")
        db.add(account)
        journeys.start(db, account_id)
        db.commit()
    return Caller(account_id=account.id, role=account.role)


def require(caller: Caller, *roles: str) -> None:
    if caller.role not in roles:
        raise Forbidden(f"requires role {' or '.join(roles)}")


@dataclass(frozen=True)
class ClinicianBooking:
    booking_id: str
    starts_at: object
    format: str
    reference: str
    client_first_name: str | None
    assessment: dict | None


def _clinician_for(db: Session, caller: Caller) -> Clinician:
    require(caller, "clinician")
    clinician = db.scalars(
        select(Clinician).where(Clinician.account_id == caller.account_id)
    ).first()
    if clinician is None:
        raise Forbidden("no clinician profile for this account")
    return clinician


def clinician_bookings(db: Session, caller: Caller) -> list[tuple[Booking, Slot]]:
    """The Clinician's upcoming Initial consultations, soonest first."""
    clinician = _clinician_for(db, caller)
    # ISSUE-017: the list used to filter on "active" only, so past consultations stayed
    # listed. PRD story 79 asks for upcoming ones; a consultation drops off once it starts.
    rows = db.execute(
        select(Booking, Slot)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(
            Slot.clinician_id == clinician.id,
            Booking.status == "active",
            Slot.starts_at >= datetime.now(UTC),
        )
        .order_by(Slot.starts_at)
    ).all()
    return [tuple(r) for r in rows]


def clinician_view(db: Session, caller: Caller, booking_id: str) -> ClinicianBooking:
    """One booked Client's preparation view. Writes the Access log. Never DOB or address."""
    clinician = _clinician_for(db, caller)
    row = db.execute(
        select(Booking, Slot)
        .join(Slot, Slot.id == Booking.slot_id)
        .where(Booking.id == booking_id, Booking.status == "active")
    ).first()
    if row is None or row[1].clinician_id != clinician.id:
        # Same answer for "does not exist" and "not yours": no probing other Clinicians' Clients.
        raise Forbidden("booking not found")
    booking, slot = row
    client = db.get(Client, booking.client_id)
    assessment = db.get(Assessment, booking.client_id)
    db.add(
        AccessLogEntry(
            clinician_account_id=caller.account_id,
            client_account_id=booking.client_id,
            booking_id=booking.id,
        )
    )
    db.commit()
    view = None
    if assessment is not None:
        view = dict(assessment.answers)
        view["reason_text"] = assessment.reason_text
        # ISSUE-015: the Safety answer used to be dropped here, so a Client who answered
        # "yes", resumed after the Crisis pause and booked reached the Clinician with no risk
        # flag. It is part of the Assessment the spec gives the Clinician; the route also
        # raises it as a flag above the answers.
        view["safety"] = assessment.safety
    return ClinicianBooking(
        booking_id=booking.id,
        starts_at=slot.starts_at,
        format=slot.format,
        reference=booking.reference,
        client_first_name=client.first_name if client else None,
        assessment=view,
    )
