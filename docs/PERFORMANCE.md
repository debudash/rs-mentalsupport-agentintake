# Performance

## Results

Measured 2026-10-17 on the local stack: Windows 11 laptop, Docker (Rancher Desktop),
production image (`runtime` target, 2 uvicorn workers), local Supabase in Docker.

| Target (client PRD) | Result | Method |
|---|---|---|
| Chatbot / API p95 < 3.0 s at 20 VUs × 60 s | **chat 2.28 s, all API 1.91 s, 0% failed** (310/310 checks), 0 LLM errors in 290 messages | `make load` — k6 against **real Claude Haiku 5.5** (effort low) |
| (same, repeatable without a key) | chat 1.15 s, all API 1.07 s, 0% failed | k6 with the Fake LLM at a fixed 800 ms |
| OCR extraction p95 < 8.0 s, 20 runs | **1.18 s** (p50 856 ms, max 1.66 s) | `make timings` — server `Server-Timing` (upload receipt → fields response) |
| Booking action p95 < 1.0 s, 20 runs | **85 ms** (p50 49 ms) | same |
| Uptime ≥ 99% | pending deployment | UptimeRobot on `/health` every 5 min |

OCR eval latency (40 synthetic IDs, Tesseract 5.5.0): p50 872 ms, p95 1.42 s.

## Model latency (intent eval, 65 calls per run, 3 runs each)

| Model | LLM p50 | LLM p95 | Quality |
|---|---|---|---|
| Claude Haiku 5.5 | ~1.0 s | 1.76–2.02 s | 100% every run |
| Claude Opus 5.5 | ~2.2 s | 2.94–3.21 s | 98–100% |

Opus alone uses nearly all of the 3 s chat budget before any of our own work; Haiku
leaves about a second of headroom, which the load test confirms (chat p95 2.28 s).
**The published chat number therefore requires `LLM_MODEL=claude-haiku-5-5`;** with
`.env.example`'s default (Opus 5.5) the chat target would be missed.

## The keyless run

Graders without a key can reproduce the system's own overhead with the Fake adapter at a
fixed 800 ms delay: chat p95 1.15 s, i.e. about 350 ms on top of the model.

## Where the time goes

Every API response carries a `Server-Timing` header (`llm`, `db`, `ocr`, `total`) and
writes one identity-free timing record. The Operator dashboard shows p50/p95 per endpoint
against these targets.

## Issues found by load testing

- [ISSUE-002](ISSUE_LOG.md): a keep-alive race dropped 1 in 500 requests; fixed with a
  75 s server keep-alive.
