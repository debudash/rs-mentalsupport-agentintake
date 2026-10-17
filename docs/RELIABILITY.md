# Reliability: how rs-assist degrades

Written for reviewers and whoever operates the service. The rule the whole design follows:
**a Client is never stuck.** Every dependency can fail; when one does, the Client gets a
plain message and a way to keep going, their progress is already saved, and the failure
shows up on the Operations dashboard.

## Failure-mode matrix

| Dependency | Failure | Detected by | What the Client sees | Recovery | Proof |
|---|---|---|---|---|---|
| **LLM** | Timeout (> `LLM_TIMEOUT_SECONDS`, 5 s) | Adapter timeout → `LLMFailure(timeout)`; `llm_error` log line | "I'm having trouble right now" + the next question as tap-to-answer buttons + "Try the assistant again" | Automatic per message; after **2 failures in a row**, simple questions for the rest of Intake | `test_intake.py::test_llm_failure_degrades_to_scripted_question`, `::test_two_failures_switch_to_scripted_mode_and_intake_still_completes`; `test_faults.py` |
| | 5xx, unreachable, rate-limited, bad key | Adapter maps each to a `FailureKind`; `/health` `llm: unreachable` | Same as above | Same; operator fixes key/tier ([RUNBOOK](RUNBOOK.md)) | `test_api_flow.py::test_llm_down_intake_still_completes`; adapter error-mapping tests |
| | Invalid output (bad JSON, unknown intent, invalid value) | Schema + allowed-value validation | Invalid values are dropped, never shown or saved; the turn continues ([ISSUE-004](ISSUE_LOG.md)) | None needed | `test_intake.py::test_invalid_llm_output_is_never_shown_or_saved` |
| | Unsafe reply (a promise, a time, a price, clinical language) | Output check after every reply | A safe fallback line instead | Counted on the dashboard ("Unsafe replies replaced") | `test_domain_pure.py` BLOCKED/BENIGN tables |
| | *Any* LLM failure during a crisis | — | Unaffected: the crisis check runs **before** the LLM and is deterministic | — | `test_domain_pure.py` safety tests |
| **OCR** | Engine error | Exception inside the reader → `engine_error` | "We couldn't read that photo" card, fields blank, **type the details instead** | Client types; no dead end | `test_ocr.py::test_engine_crash_degrades_to_manual_entry`; `test_faults.py` |
| | No text / unreadable photo | No confident field → `no_text` / `unreadable` | Same card and manual entry | Same | `test_api_flow.py::test_unreadable_photo_offers_manual_entry_support` |
| | Partial read | Per-field confidence below threshold | Read fields pre-filled and marked "please check"; the rest blank — **never guessed** | Client completes the blanks | `test_ocr.py::test_partial_card_leaves_missing_fields_blank`, `test_api_flow.py::test_partial_read_marks_missing_fields_blank` |
| **Upload** | Wrong type, corrupt, empty, > 8 MB | Server decodes the content (not the file name) | A plain reason ("That file isn't a photo…") + the same card | Client retries or types | `test_ocr.py::test_bad_uploads_are_rejected_with_a_reason`, `test_api_flow.py::test_bad_upload_is_rejected_with_message_and_support` |
| **Database** | Unreachable / paused (Supabase Free pauses after 7 idle days) | `/health` → `database: unreachable`, `status: degraded`; uptime monitor alerts | "Something went wrong on our side. Your progress is saved — please try again in a moment." (no stack trace) | Operator restores; the `/health` heartbeat write prevents the pause | `test_api_flow.py::test_unexpected_error_is_friendly` |
| | Slow | `db` stage in `Server-Timing` and timing records; dashboard p95 | Slower Steps; nothing breaks | Pool of 4 + 1 per worker, `pool_pre_ping` | `FAULT_INJECT=db_slow` drill below |
| | Connection limit (Supabase pooler: 15 server slots) | `unhandled_error` with `OperationalError` in logs; dashboard server errors | Under load, requests failed — found on the deployment ([ISSUE-012](ISSUE_LOG.md)) | Transaction pooler (slots held only during a transaction); app pool capped; timing records on their own pool so requests can't deadlock ([ISSUE-013](ISSUE_LOG.md)) | `test_db_pool.py`; k6 on the deployment: 0% failed |
| | Two Clients book the same slot at once | Unique index: one active Booking per Slot | "That time was just taken" + nearest alternatives | None needed | `test_postgres_concurrency.py` (20 simultaneous bookings, exactly one wins) |
| **Auth** (Supabase) | Expired or invalid token | Signature/audience check on every request | "Please sign in again"; progress is kept | Sign in again | `test_adapters_and_dashboard.py::test_verifier_accepts_valid_and_rejects_wrong_audience_or_secret` |
| | Auth service down | Sign-in call fails in the browser | Sign-in error message; signed-in Clients keep working for a few minutes (signing keys are cached for 5 min) | Supabase recovers | Not automated (third-party outage) |
| **Browser / network** | Tab closed, connection drops, phone dies | — | On return: back on the same Step, answers kept | Progress saved on the server after every answer; the app reads it on every load | `test_gentle.py::test_gentle_mode_persists_across_sessions`; e2e `gentle.mjs` "persists after reload" |
| **App container** | Crash / redeploy | `/health` stops answering; uptime monitor | Brief error; nothing lost | Railway restarts the container | Uptime monitor (after deploy) |

What is deliberately **not** handled: retries inside a request (a retry would blow the 3 s
budget; the Client gets a fast fallback instead), and multi-region failover (out of scope
for a demo; see the README's production upgrades).

## Fault injection

`FAULT_INJECT` forces these failures on a running app, so they can be demonstrated and
re-checked, not just claimed. It wraps the real dependency at its seam
([backend/app/faults.py](../backend/app/faults.py)), so fallbacks, supportive content, logs
and the dashboard react exactly as they would to a real outage. It is **refused when
`APP_ENV=production`** (the app won't start), and `/health` lists active faults and
reports `degraded` while any is on.

| `FAULT_INJECT=` | What happens | What to look for |
|---|---|---|
| `llm_down` | Every LLM call fails at once | Intake continues with tap-to-answer questions; "Try the assistant again"; `/health` `llm: unreachable`; dashboard "Fell back to scripted questions" rises |
| `llm_timeout` | Every LLM call waits the full timeout (5 s), then fails | Same, after a 5 s wait — the slowest a Client ever waits for the assistant |
| `ocr_fail` | The OCR engine errors on every photo | "We couldn't read that photo" card; blank fields; Client types and continues |
| `db_slow` | Every query waits `FAULT_DB_DELAY_MS` (1500 ms) first | Steps slow down but complete; the dashboard's p95 shows which targets break |

```bash
FAULT_INJECT=llm_down make up              # one fault
FAULT_INJECT=llm_down,ocr_fail make up     # several
curl -s localhost:8000/api/health          # "faults": [...], "status": "degraded"
make up                                    # back to normal
```

Drill result (2026-10-17, `llm_down,ocr_fail`, real stack): the smoke test's only failed
check was the one the fault targets ("synthetic ID read by Tesseract" — fields came back
blank); Intake completed on scripted questions, identity was confirmed by typing, booking,
withdrawal and deletion all passed.

## Service levels and error budgets

The client PRD's four benchmarks, restated as service levels a team would run against.
An **error budget** is how much failure the level allows before feature work stops and
reliability work starts.

| Service level indicator | Objective | Error budget (30 days) | Measured | How it's watched |
|---|---|---|---|---|
| Chat reply latency | 95% of replies < 3.0 s | 5% of replies may exceed 3 s | p95 **2.28 s** at 20 users on Claude Haiku 5.5 (k6, 290 messages) | Dashboard "Chat reply" p95 vs target; timing records |
| ID reading latency | 95% < 8.0 s | 5% may exceed 8 s | p95 **1.18 s** (20 runs) | Dashboard "ID reading" p95 |
| Booking latency | 95% < 1.0 s | 5% may exceed 1 s | p95 **85 ms** (20 runs) | Dashboard "Booking" p95 |
| Availability | ≥ 99% of 5-minute health checks succeed | ~7.2 h of downtime | Deployed 2026-10-17; monitor history from then | Uptime monitor on `/api/health` |
| Requests without a server error | ≥ 99.5% of API requests return < 500 | 0.5% | 0 server errors in 4,003 requests (local, mixed load) | Dashboard "server errors" count |
| Intake completes despite the LLM | 100% of Intakes can finish with the LLM down | **0** — this one has no budget | Drill above; `test_faults.py` | Fallback-rate panel |

**Burn policy.** If a latency budget is half spent within a week: switch to the faster
model (Opus → Haiku is a one-variable change), then look at `Server-Timing` stages for the
slow part. If the availability budget is spent: no deploys except fixes until a week of
clean checks. The "Intake completes" level is a design guarantee, so any breach is a
bug ([ISSUE_LOG](ISSUE_LOG.md)), not budget.

**Honest limits.** The latency numbers are single runs on a laptop against local Supabase,
not 30 days of production traffic; error budgets only become meaningful once the deployed
app has real traffic. The dashboard already computes the inputs (p50/p95 per endpoint,
server errors, fallback rate) over any window.
