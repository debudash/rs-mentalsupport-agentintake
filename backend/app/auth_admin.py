"""Auth admin seam: deleting a Supabase Auth user at Withdrawal. Supabase and Fake adapters."""

from functools import lru_cache
from typing import Protocol

import httpx

from app.config import get_settings


class AuthAdmin(Protocol):
    def delete_user(self, account_id: str) -> bool: ...


class SupabaseAuthAdmin:
    def __init__(self, supabase_url: str, service_role_key: str):
        self._url = supabase_url.rstrip("/")
        self._key = service_role_key

    def delete_user(self, account_id: str) -> bool:
        if not self._url or not self._key:
            return False
        response = httpx.delete(
            f"{self._url}/auth/v1/admin/users/{account_id}",
            headers={"apikey": self._key, "Authorization": f"Bearer {self._key}"},
            timeout=10.0,
        )
        return response.status_code in (200, 204, 404)


class FakeAuthAdmin:
    def __init__(self):
        self.deleted: list[str] = []

    def delete_user(self, account_id: str) -> bool:
        self.deleted.append(account_id)
        return True


@lru_cache
def get_auth_admin() -> AuthAdmin:
    settings = get_settings()
    return SupabaseAuthAdmin(settings.supabase_url, settings.supabase_service_role_key)
