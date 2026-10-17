"""20-run timings for OCR extraction and booking, from the server's own timing header.

  make timings             (against http://host.docker.internal:8000 from the dev container)
  python k6/timings.py http://localhost:8000

OCR: time from upload receipt to extracted-fields response (target p95 < 8 s).
Booking: server time for the booking action (target p95 < 1 s).
Creates throwaway Accounts, withdraws them at the end.
"""

import os
import re
import secrets
import statistics
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_test import ANSWERS, env, new_account  # noqa: E402

RUNS = 20
CARDS = sorted((ROOT / "evals" / "datasets" / "ocr" / "golden").glob("*.jpg"))


def server_ms(response: httpx.Response, stage: str = "total") -> float:
    match = re.search(rf"{stage};dur=([\d.]+)", response.headers.get("server-timing", ""))
    return float(match.group(1)) if match else float("nan")


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASE_URL", "http://localhost:8000")).rstrip("/")
    supabase = env("SUPABASE_URL").rstrip("/")
    if os.environ.get("DOCKER_HOST_ALIAS"):
        supabase = supabase.replace("127.0.0.1", os.environ["DOCKER_HOST_ALIAS"])
        base = base.replace("localhost", os.environ["DOCKER_HOST_ALIAS"])
    anon = env("SUPABASE_ANON_KEY")

    ocr, booking, clients = [], [], []
    for i in range(RUNS):
        token, _ = new_account(supabase, anon)
        api = httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        clients.append(api)
        api.post("/api/consent", json={"onboarding": True, "id_scan": True, "age_confirmed": True}).raise_for_status()
        for item, value in ANSWERS:
            api.post("/api/intake/messages", json={"item": item, "value": value}).raise_for_status()
        card = CARDS[i % len(CARDS)]
        scan = api.post("/api/identity/scan", files={"file": (card.name, card.read_bytes(), "image/jpeg")})
        scan.raise_for_status()
        ocr.append(server_ms(scan))
        api.post("/api/identity/confirm", json={
            "legal_name": f"Timing Run {secrets.token_hex(2)}", "date_of_birth": "1990-01-01",
            "address": "1 Test St, Springfield, RS 12345", "source": "manual"}).raise_for_status()

    slots = clients[0].get("/api/slots", params={"show_all": True}).json()["slots"]
    for i, api in enumerate(clients):
        res = api.post("/api/bookings", json={"slot_id": slots[i]["id"]})
        res.raise_for_status()
        booking.append(server_ms(res))

    for api in clients:
        api.post("/api/withdraw", json={"confirm": True})

    print(f"OCR extraction   n={len(ocr)}  p50={statistics.median(ocr):.0f} ms  p95={p95(ocr):.0f} ms"
          f"  max={max(ocr):.0f} ms  target p95 < 8000 ms  {'PASS' if p95(ocr) < 8000 else 'FAIL'}")
    print(f"Booking action   n={len(booking)}  p50={statistics.median(booking):.0f} ms  p95={p95(booking):.0f} ms"
          f"  max={max(booking):.0f} ms  target p95 < 1000 ms  {'PASS' if p95(booking) < 1000 else 'FAIL'}")
    return 0 if p95(ocr) < 8000 and p95(booking) < 1000 else 1


if __name__ == "__main__":
    sys.exit(main())
