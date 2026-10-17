# ruff: noqa: E501  (long report and log strings in a one-off tool)
"""Synthetic cohort: simulated Clients walk the real onboarding, paced like people.

Everything the system does is real — sign-up in Supabase Auth, the API, Claude, Tesseract,
the database, the timestamps. The only modelled part is how long a person takes between
actions, using Keystroke-Level Model (KLM) operator times and reading speed (constants below).

What this shows, and what it doesn't (see docs/IMPACT.md):
- time to complete, per persona and per Step, for this flow at human pace  -> simulated
- the same information entered on a conventional all-typed form            -> estimated (same model)
- that the funnel, friction, OCR-correction and NPS panels measure correctly -> verified
- real completion uplift or real NPS                                         -> NOT shown: needs real people

Run against a running app (make up), with LLM_PROVIDER=anthropic for the real model:
    python tools/simulate/cohort.py --base http://localhost:8000 [--personas 30]
Writes evals/reports/<date>-cohort.json and prints a summary.
"""

import argparse
import json
import random
import secrets
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_test import env  # noqa: E402

# ---- human pacing model (KLM + reading) ----------------------------------------------
READ_WPM = 230  # silent reading, adults (Brysbaert 2019: ~238 wpm)
TYPE_S_PER_CHAR = 0.30  # ~40 wpm average typist (KLM "K", average non-secretary)
MENTAL_S = 1.35  # KLM "M": deciding / preparing an action
POINT_S = 1.10  # KLM "P": reaching a control
TAP_S = 0.20  # KLM "B": press + release
PHOTO_S = 20.0  # open camera, frame the card, shoot, accept (assumption)
FIND_ID_S = 15.0  # fetch the ID card (both paths need it)
CHECK_FIELD_S = 2.5  # read one pre-filled field against the card
SCAN_LIST_S = 10.0  # look over available times
BREAK_S = 60.0  # a stressed client's "Take a break"
IDLE_S = 50.0  # a client who stalls before leaving (triggers the 45 s pause signal)


def read_s(text: str) -> float:
    return len(text.split()) / READ_WPM * 60


def type_s(text: str) -> float:
    return MENTAL_S + POINT_S + len(text) * TYPE_S_PER_CHAR


def choose_s() -> float:
    return MENTAL_S + POINT_S + TAP_S


# ---- personas ------------------------------------------------------------------------
LABELS = {
    item["file"]: item["expected"]
    for item in json.loads((ROOT / "evals/datasets/ocr/labels.json").read_text(encoding="utf-8"))
}
CLEAN_CARDS = [f for f in LABELS if "/clean_" in f or "/photo_" in f]
HARD_CARDS = [f for f in LABELS if "/hard_" in f and "cut_off" not in f]


@dataclass
class Persona:
    name: str
    kind: str  # calm_scan | calm_typist | stressed | photo_trouble | drop_consent | drop_intake | drop_identity
    id_scan: bool = True
    first_text: str | None = None
    card: str | None = None
    nps: int | None = None
    timeline: list = field(default_factory=list)
    steps_s: dict = field(default_factory=dict)
    counts: dict = field(default_factory=lambda: {"taps": 0, "typed_chars": 0, "llm_messages": 0})
    outcome: str = "started"
    notes: list = field(default_factory=list)


def make_cohort(n: int, seed: int = 7) -> list[Persona]:
    rng = random.Random(seed)
    mix = (
        ["calm_scan"] * 10
        + ["calm_typist"] * 5
        + ["stressed"] * 6
        + ["photo_trouble"] * 4
        + ["drop_consent"] * 2
        + ["drop_intake"] * 1
        + ["drop_identity"] * 2
    )
    while len(mix) < n:
        mix.append("calm_scan")
    people = []
    for i, kind in enumerate(mix[:n]):
        p = Persona(name=f"{kind}-{i:02d}", kind=kind)
        if kind == "calm_typist":
            p.id_scan = False
            p.first_text = rng.choice(
                [
                    "It's mostly anxiety, for about four months now",
                    "low mood mostly, it's been over a year",
                    "work stress, burnout really, the last couple of months",
                ]
            )
        if kind == "stressed":
            p.first_text = rng.choice(
                [
                    "honestly I'm really overwhelmed, I nearly didn't do this",
                    "I'm so anxious about all of this, sorry",
                ]
            )
        p.card = rng.choice(HARD_CARDS if kind == "photo_trouble" else CLEAN_CARDS)
        # Synthetic scores, only to exercise the NPS calculation end to end (not a result).
        p.nps = {"calm_scan": 9, "calm_typist": 8, "stressed": 9, "photo_trouble": 7}.get(kind)
        people.append(p)
    return people


# ---- one simulated client --------------------------------------------------------------
NORM = str.maketrans("", "", ".,'")


def norm(v):
    return " ".join(str(v or "").lower().translate(NORM).split())


class Run:
    def __init__(self, base: str, supabase: str, anon: str, p: Persona, t0: float):
        self.p, self.t0 = p, t0
        email = f"cohort-{secrets.token_hex(4)}@riverside.test"
        password = secrets.token_urlsafe(14)
        r = httpx.post(
            f"{supabase}/auth/v1/signup",
            headers={"apikey": anon},
            json={"email": email, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        self.api = httpx.Client(
            base_url=base,
            timeout=60,
            headers={"Authorization": f"Bearer {r.json()['access_token']}"},
        )
        self.step_started = time.monotonic()

    def wait(self, seconds: float, why: str) -> None:
        time.sleep(seconds)

    def mark(self, event: str) -> None:
        self.p.timeline.append((round(time.monotonic() - self.t0, 1), event))

    def end_step(self, step: str) -> None:
        now = time.monotonic()
        self.p.steps_s[step] = round(now - self.step_started, 1)
        self.step_started = now
        self.mark(f"{step} done")

    def stall_and_leave(self, step: str, why: str) -> None:
        self.wait(IDLE_S, "stall")
        self.api.post(
            "/api/support/events", json={"kind": "idle", "step": step, "idle_seconds": IDLE_S}
        ).raise_for_status()
        self.p.outcome = f"left at {step}"
        self.p.notes.append(why)
        self.mark(f"left at {step}")

    def tap(self, path, body):
        self.p.counts["taps"] += 1
        return self.api.post(path, json=body)

    # -- steps --
    def consent(self, profile) -> bool:
        text = " ".join(c["text"] for c in profile["consents"].values())
        self.wait(read_s(text) + 3 * choose_s() + choose_s(), "consent")
        if self.p.kind == "drop_consent":
            self.stall_and_leave("consent", "changed their mind at consent (scripted)")
            return False
        self.tap(
            "/api/consent", {"onboarding": True, "id_scan": self.p.id_scan, "age_confirmed": True}
        ).raise_for_status()
        self.end_step("consent")
        return True

    def intake(self) -> bool:
        reply = self.api.get("/api/intake").json()
        if self.p.first_text:
            self.wait(read_s(" ".join(reply["messages"])) + type_s(self.p.first_text), "type")
            self.p.counts["typed_chars"] += len(self.p.first_text)
            self.p.counts["llm_messages"] += 1
            reply = self.api.post("/api/intake/messages", json={"text": self.p.first_text}).json()
        breaks_taken, answered = 0, 0
        for _ in range(30):
            if reply.get("complete"):
                self.end_step("intake")
                return True
            if reply.get("crisis"):
                self.p.outcome = "crisis pause"
                return False
            self.wait(read_s(" ".join(reply["messages"])), "read")
            options = [q for q in reply["quick_replies"] if q["value"] != "__break__"]
            if self.p.kind == "stressed" and reply.get("gentle") and not breaks_taken:
                breaks_taken += 1
                self.p.notes.append("took a break")
                self.wait(BREAK_S, "break")
            if self.p.kind == "drop_intake" and answered == 3:
                self.stall_and_leave("intake", "stalled mid-intake (scripted)")
                return False
            item = reply["pending_item"]
            if item == "reason_text" and self.p.kind in ("calm_typist",):
                text = "It's been affecting my sleep and work"
                self.wait(type_s(text), "type")
                self.p.counts["typed_chars"] += len(text)
                self.p.counts["llm_messages"] += 1
                reply = self.api.post("/api/intake/messages", json={"text": text}).json()
            else:
                value = self.choose(item, options)
                self.wait(choose_s() * (2 if reply["input_kind"] == "multichoice" else 1), "tap")
                reply = self.tap("/api/intake/messages", {"item": item, "value": value}).json()
            answered += 1
        self.p.notes.append("intake did not complete in 30 turns")
        return False

    def choose(self, item, options):
        prefs = {
            "distress": "5" if self.p.kind == "stressed" else "3",
            "safety": "no",
            "availability": "mornings,afternoons,evenings",
            "session_format": "either",
            "clinician_gender": "no_preference",
            "clinician_language": "no_preference",
            "reason_text": "prefer_not_to_say",
        }
        return prefs.get(item, options[0]["value"] if options else "prefer_not_to_say")

    def identity(self) -> bool:
        truth = LABELS[self.p.card]
        if self.p.kind == "drop_identity":
            self.wait(FIND_ID_S, "look for ID")
            self.stall_and_leave("identity", "no ID to hand (scripted)")
            return False
        self.wait(FIND_ID_S, "find ID")
        values = {"legal_name": "", "date_of_birth": "", "address": ""}
        prefilled = dict.fromkeys(values, False)
        source = "manual"
        if self.p.id_scan:
            if self.p.kind == "photo_trouble":
                self.wait(PHOTO_S, "photo")
                bad = self.api.post(
                    "/api/identity/scan",
                    files={"file": ("id.pdf", b"%PDF-1.7 not a photo", "application/pdf")},
                )
                self.p.notes.append(f"first upload rejected: {bad.json().get('reason')}")
            self.wait(PHOTO_S, "photo")
            card = (ROOT / "evals/datasets/ocr" / self.p.card).read_bytes()
            scan = self.api.post(
                "/api/identity/scan", files={"file": ("id.jpg", card, "image/jpeg")}
            )
            fields = (scan.json() or {}).get("fields") or {}
            mapping = {"name": "legal_name", "date_of_birth": "date_of_birth", "address": "address"}
            for api_name, ours in mapping.items():
                got = (fields.get(api_name) or {}).get("value")
                if got:
                    values[ours], prefilled[ours] = got, True
            source = "scan"
        edited = dict.fromkeys(values, False)
        for ours, expected_key in (
            ("legal_name", "name"),
            ("date_of_birth", "date_of_birth"),
            ("address", "address"),
        ):
            expected = truth[expected_key] or ""
            if prefilled[ours]:
                self.wait(CHECK_FIELD_S, "check field")
                if norm(values[ours]) != norm(expected):
                    values[ours], edited[ours] = expected, True
                    self.wait(type_s(expected), "fix field")
                    self.p.counts["typed_chars"] += len(expected)
            else:
                values[ours] = expected
                self.wait(type_s(expected), "type field")
                self.p.counts["typed_chars"] += len(expected)
        r = self.tap(
            "/api/identity/confirm",
            {**values, "source": source, "edited": edited, "prefilled": prefilled},
        )
        if not r.json().get("confirmed"):
            self.p.notes.append(f"identity not confirmed: {r.text[:120]}")
            return False
        self.p.notes.append(
            f"OCR edits: {[k for k, v in edited.items() if v]}"
            if source == "scan"
            else "typed identity"
        )
        self.end_step("identity")
        return True

    def schedule(self) -> bool:
        slots = self.api.get("/api/slots", params={"tz": "America/New_York"}).json()["slots"]
        if not slots:
            slots = self.api.get("/api/slots", params={"show_all": True}).json()["slots"]
        self.wait(SCAN_LIST_S + 2 * choose_s(), "choose time")
        for slot in random.sample(slots, min(len(slots), 8)):
            r = self.tap("/api/bookings", {"slot_id": slot["id"], "tz": "America/New_York"})
            if r.status_code == 200:
                self.end_step("scheduling")
                return True
            self.wait(choose_s(), "pick another")
        self.p.notes.append("could not book")
        return False

    def feedback(self) -> None:
        if self.p.nps is None:
            return
        self.wait(read_s("How likely are you to recommend signing up with us") + choose_s(), "nps")
        self.tap("/api/feedback", {"score": self.p.nps}).raise_for_status()

    def go(self) -> None:
        try:
            self.mark("start")
            profile = self.api.get("/api/me").json()["profile"]
            PROFILE.update(profile)
            if self.consent(profile) and self.intake() and self.identity() and self.schedule():
                self.p.outcome = "booked"
                self.feedback()
        except Exception as exc:  # noqa: BLE001 - recorded, the cohort goes on
            self.p.outcome = f"error: {type(exc).__name__}"
            self.p.notes.append(str(exc)[:200])


# ---- conventional form, same information, same model ------------------------------------
def conventional_form_estimate(profile: dict) -> dict:
    """The same information on an all-typed form: consent text, nine intake answers typed,
    identity details transcribed from the card. KLM per field: M + P + typing."""
    typical = {
        "reason (category)": "Anxiety",
        "reason (own words)": "affecting sleep and work",
        "duration": "4 months",
        "distress 1-5": "3",
        "safety question": "No",
        "format": "Video",
        "availability": "Mornings, evenings",
        "clinician gender": "No preference",
        "language": "English",
        "legal name": "Melanie L Sanchez",
        "date of birth": "05/22/1997",
        "address": "2120 Cherry Ct, Aaronchester, RS 29112",
    }
    consent = " ".join(c["text"] for c in profile["consents"].values())
    labels_read = sum(read_s(k) for k in typical)
    seconds = (
        read_s(consent)
        + 4 * choose_s()
        + labels_read
        + FIND_ID_S
        + sum(type_s(v) for v in typical.values())
        + SCAN_LIST_S
        + 3 * choose_s()
    )
    chars = sum(len(v) for v in typical.values())
    return {"seconds": round(seconds, 1), "typed_chars": chars, "fields_typed": len(typical)}


# ---- main ------------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--personas", type=int, default=30)
    args = ap.parse_args()
    supabase, anon = env("SUPABASE_URL").rstrip("/"), env("SUPABASE_ANON_KEY")
    people = make_cohort(args.personas)
    t0 = time.monotonic()
    started = datetime.now(UTC)
    print(f"Running {len(people)} simulated clients in parallel against {args.base} ...")
    lock = threading.Lock()

    def one(p: Persona):
        Run(args.base, supabase, anon, p, t0).go()
        with lock:
            print(
                f"  {p.name:18} {p.outcome:24} {sum(p.steps_s.values()) / 60:5.1f} min  {'; '.join(p.notes)}"
            )

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        list(pool.map(one, people))

    booked = [p for p in people if p.outcome == "booked"]
    totals = [sum(p.steps_s.values()) / 60 for p in booked]
    by_kind: dict[str, list[float]] = {}
    for p in booked:
        by_kind.setdefault(p.kind, []).append(sum(p.steps_s.values()) / 60)
    step_medians = {
        s: round(statistics.median([p.steps_s[s] for p in booked if s in p.steps_s]) / 60, 2)
        for s in ("consent", "intake", "identity", "scheduling")
    }
    conventional = conventional_form_estimate(PROFILE)
    ours_typed = statistics.median([p.counts["typed_chars"] for p in booked]) if booked else None
    report = {
        "generated_at": started.isoformat(),
        "label": "SYNTHETIC COHORT — simulated people on the real system; not field data",
        "pacing_model": {
            "read_wpm": READ_WPM,
            "type_s_per_char": TYPE_S_PER_CHAR,
            "mental_s": MENTAL_S,
            "point_s": POINT_S,
            "tap_s": TAP_S,
            "photo_s": PHOTO_S,
            "find_id_s": FIND_ID_S,
            "break_s": BREAK_S,
        },
        "cohort": {
            "size": len(people),
            "booked": len(booked),
            "scripted_drop_outs": sum(1 for p in people if p.kind.startswith("drop_")),
            "outcomes": {p.name: p.outcome for p in people},
        },
        "time_to_complete_min": {
            "median_all_completers": round(statistics.median(totals), 1) if totals else None,
            "p90_all_completers": round(sorted(totals)[int(0.9 * (len(totals) - 1))], 1)
            if totals
            else None,
            "median_by_persona": {k: round(statistics.median(v), 1) for k, v in by_kind.items()},
            "median_by_step": step_medians,
        },
        "effort": {"median_typed_chars_ours": ours_typed, "conventional_form": conventional},
        "people": [
            {
                "name": p.name,
                "kind": p.kind,
                "outcome": p.outcome,
                "steps_s": p.steps_s,
                "counts": p.counts,
                "notes": p.notes,
            }
            for p in people
        ],
    }
    out = ROOT / "evals/reports" / f"{started:%Y-%m-%d}-cohort.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    t = report["time_to_complete_min"]
    print(
        f"\nBooked {len(booked)}/{len(people)} (scripted drop-outs: {report['cohort']['scripted_drop_outs']})"
    )
    print(
        f"Time to complete (simulated human pace): median {t['median_all_completers']} min, "
        f"p90 {t['p90_all_completers']} min; by step {t['median_by_step']}"
    )
    print(f"By persona: {t['median_by_persona']}")
    print(
        f"Typed characters: ours median {ours_typed} vs conventional form {conventional['typed_chars']}; "
        f"conventional form estimate {conventional['seconds'] / 60:.1f} min for the same information"
    )
    print(f"Report: {out.relative_to(ROOT)}")
    return 0


PROFILE: dict = {}  # the Service profile, as served to the first simulated client


if __name__ == "__main__":
    sys.exit(main())
