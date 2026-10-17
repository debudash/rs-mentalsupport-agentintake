"""End-to-end smoke test against a running deployment (local or Railway).

Creates a throwaway Account in Supabase Auth, walks the whole Onboarding through the real
API (consent -> intake -> ID scan of a synthetic card -> confirm -> book -> calendar file),
checks the edge cases that need the real stack (double-booking, bad upload, crisis pause),
then withdraws and verifies the deletion.

  python scripts/smoke_test.py http://localhost:8000
Reads SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY from the environment or .env.
"""

import os
import secrets
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "evals" / "datasets" / "ocr" / "golden" / "photo_03.jpg"
ANSWERS = [
    ("reason_category", "stress"), ("reason_text", "Smoke test, synthetic"), ("duration", "1_6_months"),
    ("distress", "2"), ("safety", "no"), ("session_format", "either"),
    ("availability", "mornings,afternoons,evenings"), ("clinician_gender", "no_preference"),
    ("clinician_language", "no_preference"),
]


def env(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{name} is not set")


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{' — ' + detail if detail and not condition else ''}")
    if not condition:
        check.failures += 1


check.failures = 0


def new_account(supabase: str, anon: str) -> tuple[str, str]:
    email = f"smoke-{secrets.token_hex(4)}@riverside.test"
    password = secrets.token_urlsafe(16)
    r = httpx.post(f"{supabase}/auth/v1/signup", headers={"apikey": anon},
                   json={"email": email, "password": password}, timeout=20)
    r.raise_for_status()
    body = r.json()
    token = body.get("access_token") or body.get("session", {}).get("access_token")
    if not token:  # projects with email confirmation on: sign in instead
        r = httpx.post(f"{supabase}/auth/v1/token?grant_type=password", headers={"apikey": anon},
                       json={"email": email, "password": password}, timeout=20)
        r.raise_for_status()
        token = r.json()["access_token"]
    user_id = httpx.get(f"{supabase}/auth/v1/user", headers={"apikey": anon,
                        "Authorization": f"Bearer {token}"}, timeout=20).json()["id"]
    return token, user_id


def onboard(api: httpx.Client) -> dict:
    api.post("/api/consent", json={"onboarding": True, "id_scan": True, "age_confirmed": True}).raise_for_status()
    for item, value in ANSWERS:
        reply = api.post("/api/intake/messages", json={"item": item, "value": value})
        reply.raise_for_status()
    return reply.json()


def main() -> int:
    base = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
    supabase, anon = env("SUPABASE_URL").rstrip("/"), env("SUPABASE_ANON_KEY")
    service = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_SERVICE_ROLE_KEY")
    print(f"Smoke test against {base}")

    health = httpx.get(f"{base}/api/health", timeout=30).json()
    check("health: database ok", health.get("database") == "ok", str(health))
    check("health: OCR engine available", health.get("ocr") == "ok", str(health))

    token, user_id = new_account(supabase, anon)
    api = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=60)

    check("cannot book before finishing earlier steps", api.post("/api/bookings", json={"slot_id": "x"}).status_code in (404, 409))
    last = onboard(api)
    check("intake completes with buttons only", last.get("complete") is True, str(last))

    bad = api.post("/api/identity/scan", files={"file": ("x.pdf", b"%PDF-1.7 not an image", "application/pdf")}).json()
    check("non-image upload rejected with a message", bad.get("accepted") is False and bool(bad.get("message")))
    check("upload problem shows supportive content", (bad.get("support") or {}).get("trigger") == "upload_problem")

    scan = api.post("/api/identity/scan", files={"file": ("id.jpg", CARD.read_bytes(), "image/jpeg")})
    timing = scan.headers.get("server-timing", "")
    fields = scan.json().get("fields") or {}
    check("synthetic ID read by Tesseract", fields.get("name", {}).get("status") == "read", str(fields))
    print(f"        OCR server timing: {timing}")
    confirm = api.post("/api/identity/confirm", json={
        "legal_name": fields.get("name", {}).get("value") or "Smoke Test",
        "date_of_birth": fields.get("date_of_birth", {}).get("value") or "1990-01-01",
        "address": fields.get("address", {}).get("value") or "1 Test St, Springfield, RS 12345",
        "source": "scan", "edited": {}}).json()
    check("identity confirmed", confirm.get("confirmed") is True, str(confirm))

    slots = api.get("/api/slots", params={"tz": "America/New_York", "show_all": True}).json()["slots"]
    check("open slots listed", len(slots) > 0)
    booked = api.post("/api/bookings", json={"slot_id": slots[0]["id"], "tz": "America/New_York"})
    check("booking succeeds", booked.status_code == 200, booked.text[:200])
    print(f"        booking server timing: {booked.headers.get('server-timing', '')}")
    check("calendar file downloads", "BEGIN:VEVENT" in api.get("/api/bookings/current/ics").text)

    token2, user2 = new_account(supabase, anon)
    other = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token2}"}, timeout=60)
    other.post("/api/consent", json={"onboarding": True, "age_confirmed": True}).raise_for_status()
    crisis = other.post("/api/intake/messages", json={"text": "I want to end my life"}).json()
    check("crisis language pauses onboarding with 988", crisis.get("crisis") is True and
          any(r["href"] == "tel:988" for r in crisis.get("crisis_resources", [])))
    other.post("/api/intake/resume").raise_for_status()
    onboard(other)
    other.post("/api/identity/confirm", json={"legal_name": "Other Person", "date_of_birth": "1985-05-05",
               "address": "2 Test Ave, Springfield, RS 12345", "source": "manual"}).raise_for_status()
    taken = other.post("/api/bookings", json={"slot_id": slots[0]["id"]})
    check("double-booking rejected with alternatives", taken.status_code == 409 and
          bool(taken.json()["detail"]["alternatives"]))

    for client, uid in ((api, user_id), (other, user2)):
        receipt = client.post("/api/withdraw", json={"confirm": True}).json()
        check("withdrawal returns a receipt", bool(receipt.get("reference")))
        check("auth account deleted", receipt.get("auth_account_deleted") is True)
        check("data no longer retrievable", client.get("/api/me").status_code == 401)
        admin = httpx.get(f"{supabase}/auth/v1/admin/users/{uid}",
                          headers={"apikey": service, "Authorization": f"Bearer {service}"}, timeout=20)
        check("Supabase user gone", admin.status_code == 404, str(admin.status_code))

    print(f"\n{'All checks passed' if not check.failures else f'{check.failures} check(s) failed'}")
    return 1 if check.failures else 0


if __name__ == "__main__":
    sys.exit(main())
