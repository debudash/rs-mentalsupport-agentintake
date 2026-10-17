"""Encrypted text column: encrypts on write, decrypts on read, with an app-held key.

The key lives only in the app server's environment (FIELD_ENCRYPTION_KEY), never in the
database, so a database dump or backup alone does not expose these values.
"""

from functools import lru_cache

from cryptography.fernet import Fernet
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class EncryptionKeyMissing(RuntimeError):
    pass


@lru_cache
def _fernet(key: str) -> Fernet:
    if not key:
        raise EncryptionKeyMissing(
            "FIELD_ENCRYPTION_KEY is not set. Generate one with: python -c "
            '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode())


def fernet() -> Fernet:
    return _fernet(get_settings().field_encryption_key)


class EncryptedText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return fernet().encrypt(str(value).encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return fernet().decrypt(value.encode()).decode()
