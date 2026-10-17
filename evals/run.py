"""AI eval harness: OCR golden + held-out sets, and the intent set. Prints a scorecard and
writes a dated report (JSON + Markdown) to evals/reports/.

  python evals/run.py ocr      # needs tesseract (run in the dev image: make eval)
  python evals/run.py intent   # uses LLM_PROVIDER from the environment
  python evals/run.py all [--record]   # --record also stores scorecards for the dashboard

Thresholds (client PRD): OCR >= 90% field-level accuracy on the golden set; every intent
handled; unambiguous crisis language always pauses.
"""

import argparse
import json
import os
import platform
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "eval-only-not-used-for-storage-0000000000=")

import yaml  # noqa: E402

DATASETS = ROOT / "evals" / "datasets"
REPORTS = ROOT / "evals" / "reports"
OCR_THRESHOLD = 0.90
INTENT_MIN_PASS = 0.80


def norm(value: str | None) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKD", value)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    return " ".join(text.split())


# ---- OCR -------------------------------------------------------------------------------


def run_ocr() -> dict:
    from app.ocr import DocumentReader
    from app.ocr.engines import TesseractEngine

    engine = TesseractEngine()
    if not engine.available():
        sys.exit("tesseract is not installed here; run `make eval` (uses the dev image)")
    threshold = float(os.environ.get("OCR_CONFIDENCE_THRESHOLD", 70))
    reader = DocumentReader(engine, threshold, 8 * 1024 * 1024)
    labels = json.loads((DATASETS / "ocr" / "labels.json").read_text(encoding="utf-8"))
    cases, latencies = [], []
    for label in labels:
        data = (DATASETS / "ocr" / label["file"]).read_bytes()
        started = time.perf_counter()
        result = reader.read_identity(data)
        latencies.append((time.perf_counter() - started) * 1000)
        fields = {}
        for field, expected in label["expected"].items():
            got = result.fields[field].value
            if field == "date_of_birth":
                correct = got == expected
            else:
                correct = norm(got) == norm(expected)
            fields[field] = {"expected": expected, "got": got, "correct": correct,
                             "fabricated": expected is None and got is not None,
                             "blank": got is None,
                             # the unsafe miss: a wrong value pre-filled for the Client to confirm
                             "wrong_prefill": got is not None and not correct}
        cases.append({"file": label["file"], "set": label["set"], "variant": label["variant"],
                      "fields": fields, "ms": round(latencies[-1], 1)})

    def score(subset):
        per_field = defaultdict(lambda: [0, 0])
        for case in subset:
            for field, f in case["fields"].items():
                per_field[field][0] += f["correct"]
                per_field[field][1] += 1
        total_ok = sum(v[0] for v in per_field.values())
        total = sum(v[1] for v in per_field.values())
        missed = [f for c in subset for f in c["fields"].values() if not f["correct"]]
        return {
            "overall_accuracy": round(total_ok / total, 4) if total else None,
            "per_field": {k: round(v[0] / v[1], 4) for k, v in per_field.items()},
            "fields_correct": total_ok,
            "fields_total": total,
            "missed_left_blank": sum(f["blank"] for f in missed),
            "missed_wrong_prefill": sum(f["wrong_prefill"] for f in missed),
        }

    golden = [c for c in cases if c["set"] == "golden"]
    held = [c for c in cases if c["set"] == "held_out"]
    stress = [c for c in cases if c["set"] == "stress"]
    stress_by_kind = defaultdict(list)
    for case in stress:
        stress_by_kind[case["variant"]].append(case)
    by_variant = defaultdict(list)
    for case in golden:
        by_variant[case["variant"].split("_")[0] if case["variant"].startswith("hard")
                   else case["variant"]].append(case)
    # The gate covers the sets the reader was built for; stress is reported, not gated.
    fabricated = sum(f["fabricated"] for c in golden + held for f in c["fields"].values())
    summary = {
        "engine": f"tesseract {engine.version()}",
        "confidence_threshold": threshold,
        "golden": score(golden),
        "held_out": score(held),
        "stress": score(stress),
        "stress_by_kind": {k: score(v) for k, v in stress_by_kind.items()},
        "by_variant": {k: score(v)["overall_accuracy"] for k, v in by_variant.items()},
        "fabricated_fields": fabricated,
        "latency_ms": {"p50": round(statistics.median(latencies), 1),
                       "p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))], 1),
                       "runs": len(latencies)},
        "passes": (score(golden)["overall_accuracy"] or 0) >= OCR_THRESHOLD and fabricated == 0,
    }
    return {"summary": summary, "cases": cases}


# ---- intents ---------------------------------------------------------------------------


def run_intents() -> dict:
    from app.config import get_settings
    from app.domain.intake import IntakeConductor, IntakeState, Turn
    from app.llm import build_llm
    from app.profile import get_profile

    settings = get_settings()
    profile = get_profile()
    llm = build_llm(settings)
    conductor = IntakeConductor(profile, llm, settings.llm_timeout_seconds)
    data = yaml.safe_load((DATASETS / "intents.yaml").read_text(encoding="utf-8"))
    cases = []
    for case in data["cases"]:
        answered = {i.id: _sample_answer(i) for i in profile.assessment[: case.get("answered", 0)]}
        state = IntakeState(answers=answered)
        started = time.perf_counter()
        new_state, reply = conductor.respond(state, Turn(text=case["text"]))
        ms = (time.perf_counter() - started) * 1000
        s = reply.signals
        expect = case["expect"]
        if expect == "crisis":
            ok, got = s.crisis, "crisis" if s.crisis else (s.intent or "none")
        elif expect == "check_in":
            ok, got = s.check_in and not s.crisis, "check_in" if s.check_in else (s.intent or "none")
        else:
            got = "crisis" if s.crisis else "check_in" if s.check_in else (s.intent or "none")
            ok = got == expect and not s.llm_failure
            if ok and case.get("answers"):
                for item, value in case["answers"].items():
                    if str(new_state.answers.get(item)) != str(value):
                        ok = False
                        got = f"{got} (answers {_new_answers(state, new_state)})"
            if ok and case.get("approved"):
                approved = profile.approved_answer(case["approved"])
                ok = approved is not None and approved.answer in reply.messages
                if not ok:
                    got = f"{got} (wrong/no approved answer)"
            if expect in ("express-distress",) and not s.high_stress:
                ok = False
        commitment = any(word in " ".join(reply.messages).lower()
                         for word in ("confirmed", "i've booked", "guarantee"))
        cases.append({"text": case["text"], "expect": expect, "got": got, "pass": ok and not
                      commitment, "llm_failure": s.llm_failure, "ms": round(ms, 1),
                      "subtle": bool(case.get("subtle"))})

    per_intent = defaultdict(lambda: [0, 0])
    for c in cases:
        per_intent[c["expect"]][0] += c["pass"]
        per_intent[c["expect"]][1] += 1
    rates = {k: round(v[0] / v[1], 3) for k, v in sorted(per_intent.items())}
    unambiguous = [c for c in cases if c["expect"] == "crisis" and not c["subtle"]]
    crisis_rate = sum(c["pass"] for c in unambiguous) / len(unambiguous) if unambiguous else 0
    llm_ms = [c["ms"] for c in cases]
    summary = {
        "provider": llm.provider,
        "model": llm.model,
        "cases": len(cases),
        "overall_pass_rate": round(sum(c["pass"] for c in cases) / len(cases), 3),
        "per_intent": rates,
        "every_intent_handled": all(r >= INTENT_MIN_PASS for r in rates.values()),
        "unambiguous_crisis_always_pauses": crisis_rate == 1.0,
        "llm_failures": sum(1 for c in cases if c["llm_failure"]),
        "latency_ms": {"p50": round(statistics.median(llm_ms), 1),
                       "p95": round(sorted(llm_ms)[int(0.95 * (len(llm_ms) - 1))], 1)},
    }
    summary["passes"] = summary["every_intent_handled"] and crisis_rate == 1.0
    return {"summary": summary, "cases": cases}


def _sample_answer(item):
    if item.type == "scale":
        return item.min
    if item.type == "text":
        return "sample"
    first = next(iter(item.options))
    return [first] if item.type == "multichoice" else first


def _new_answers(before, after):
    return {k: v for k, v in after.answers.items() if k not in before.answers}


# ---- output ----------------------------------------------------------------------------


def print_scorecard(kind: str, report: dict) -> None:
    s = report["summary"]
    print(f"\n=== {kind.upper()} scorecard ===")
    if kind == "ocr":
        print(f"engine: {s['engine']}  confidence threshold: {s['confidence_threshold']}")
        for name in ("golden", "held_out", "stress"):
            sc = s.get(name)
            if not sc or sc["overall_accuracy"] is None:
                continue
            fields = "  ".join(f"{k}={v:.0%}" for k, v in sc["per_field"].items())
            print(f"{name:9} {sc['overall_accuracy']:.1%} ({sc['fields_correct']}/"
                  f"{sc['fields_total']})  {fields}  misses: {sc['missed_left_blank']} left blank,"
                  f" {sc['missed_wrong_prefill']} wrong pre-filled")
        if s.get("stress_by_kind"):
            print("stress by kind: " + "  ".join(
                f"{k}={v['overall_accuracy']:.0%}" for k, v in s["stress_by_kind"].items()))
        print("golden by variant: " + "  ".join(f"{k}={v:.0%}" for k, v in s["by_variant"].items()))
        print(f"fabricated fields: {s['fabricated_fields']}   latency p50={s['latency_ms']['p50']}ms"
              f" p95={s['latency_ms']['p95']}ms")
        print(f"threshold >= {OCR_THRESHOLD:.0%} on golden: {'PASS' if s['passes'] else 'FAIL'}")
        for case in report["cases"]:
            for field, f in case["fields"].items():
                if not f["correct"]:
                    print(f"  miss {case['file']} {field}: expected {f['expected']!r} got {f['got']!r}")
    else:
        print(f"provider: {s['provider']}  model: {s['model']}  cases: {s['cases']}")
        for intent, rate in s["per_intent"].items():
            mark = "PASS" if rate >= INTENT_MIN_PASS else "FAIL"
            print(f"  {intent:20} {rate:.0%}  {mark}")
        print(f"overall {s['overall_pass_rate']:.0%}  llm failures: {s['llm_failures']}  "
              f"latency p50={s['latency_ms']['p50']}ms p95={s['latency_ms']['p95']}ms")
        print(f"unambiguous crisis always pauses: {s['unambiguous_crisis_always_pauses']}")
        print(f"every intent handled: {'PASS' if s['passes'] else 'FAIL'}")
        for case in report["cases"]:
            if not case["pass"]:
                print(f"  miss [{case['expect']}] {case['text']!r} -> {case['got']}")


def write_report(kind: str, report: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    report["meta"] = {"generated_at": datetime.now(UTC).isoformat(), "python": platform.python_version(),
                      "machine": f"{platform.system()} {platform.machine()}"}
    # Intent runs are per model, so runs on different models sit side by side.
    suffix = f"-{report['summary']['model']}" if kind == "intent" else ""
    path = REPORTS / f"{stamp}-{kind}{suffix}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPORTS / f"latest-{kind}{suffix}.json").write_text(
        json.dumps(report["summary"], indent=2) + "\n", encoding="utf-8"
    )
    return path


def record(kind: str, report: dict) -> None:
    from app.db.models import EvalReport
    from app.db.session import get_sessionmaker

    session = get_sessionmaker()()
    try:
        session.add(EvalReport(kind=kind, summary=report["summary"]))
        session.commit()
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("which", choices=["ocr", "intent", "all"], nargs="?", default="all")
    parser.add_argument("--record", action="store_true", help="store scorecards in the database")
    args = parser.parse_args()
    ok = True
    for kind, fn in (("ocr", run_ocr), ("intent", run_intents)):
        if args.which not in (kind, "all"):
            continue
        report = fn()
        print_scorecard(kind, report)
        print(f"report: {write_report(kind, report).relative_to(ROOT)}")
        if args.record:
            record(kind, report)
        ok = ok and report["summary"]["passes"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
