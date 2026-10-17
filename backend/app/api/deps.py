"""Request dependencies: database session, caller identity, conductor, reader."""

from functools import lru_cache

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.access import Caller, TokenVerifier, get_verifier, identify
from app.config import get_settings
from app.db.session import get_db
from app.domain.intake import IntakeConductor
from app.llm import get_llm
from app.profile import ServiceProfile, get_profile


def verifier() -> TokenVerifier:
    return get_verifier()


def caller(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
    token_verifier: TokenVerifier = Depends(verifier),
) -> Caller:
    return identify(db, token_verifier, authorization)


def profile() -> ServiceProfile:
    return get_profile()


@lru_cache
def _conductor() -> IntakeConductor:
    return IntakeConductor(get_profile(), get_llm(), get_settings().llm_timeout_seconds)


def conductor() -> IntakeConductor:
    return _conductor()
