# Performance

## Results

Measured 2026-10-17 on the local stack: Windows 11 laptop, Docker (Rancher Desktop),
production image (`runtime` target, 2 uvicorn workers), local Supabase in Docker.

| Target (client PRD) | Result | Method |
|---|---|---|
| Chatbot / API p95 < 3.0 s at 20 VUs × 60 s | **chat 1.15 s, all API 1.07 s, 0% failed** (320/320 checks) | `make load` — k6, Fake LLM with 800 ms simulated model latency |
| OCR extraction p95 < 8.0 s, 20 runs | **1.18 s** (p50 856 ms, max 1.66 s) | `make timings` — server `Server-Timing` (upload receipt → fields response) |
| Booking action p95 < 1.0 s, 20 runs | **85 ms** (p50 49 ms) | same |
| Uptime ≥ 99% | pending deployment | UptimeRobot on `/health` every 5 min |

OCR eval latency (40 synthetic IDs, Tesseract 5.5.0): p50 872 ms, p95 1.42 s.

## Why the chat number uses a simulated model

With 20 virtual users each sending a message every few seconds, a real-model run issues
roughly 200 LLM calls per minute. On Anthropic's lowest usage tier the rate limit is
about 50 per minute, so the run would measure throttling, not this system. The
repeatable run therefore uses the Fake adapter with a fixed 800 ms delay, which isolates
our overhead: chat p95 1.15 s means about 350 ms on top of the model.

**Real-model run** (needs a higher Anthropic tier): set `LLM_PROVIDER=anthropic`,
`FAKE_LLM_DELAY_MS=0`, restart, `make load`. With `claude-haiku-5-5` at effort `low`,
expect the model's own latency plus ~350 ms. The dashboard's LLM p95 shows the model share
on live traffic.

## Where the time goes

Every API response carries a `Server-Timing` header (`llm`, `db`, `ocr`, `total`) and
writes one identity-free timing record. The Operator dashboard shows p50/p95 per endpoint
against these targets.

## Issues found by load testing

- [ISSUE-002](ISSUE_LOG.md): a keep-alive race dropped 1 in 500 requests; fixed with a
  75 s server keep-alive.
