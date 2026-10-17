# Runbook

For whoever operates the demo. Start at `/api/health` and the Operator dashboard.
What each failure should look like, and how to rehearse it with `FAULT_INJECT`:
[RELIABILITY.md](RELIABILITY.md). A `faults` list in `/api/health` means a drill is on.

## Health check

`GET /api/health` → `{"status":"ok","database":"ok","ocr":"ok","llm":"ok", ...}`

| Field | Bad value | Effect on Clients | Do |
|---|---|---|---|
| `database` | `unreachable` | Every Step fails with a friendly "try again" message | See *Database* below |
| `ocr` | `unavailable` | ID photo fails → Clients are offered manual entry | Rebuild the image (Tesseract missing) |
| `llm` | `unreachable` | Intake switches to scripted questions; onboarding still completes | See *LLM* below |

## Symptoms

**Dashboard "LLM calls" shows failures / "Fell back to scripted questions" climbing**
- Logs: `docker compose logs app | grep llm_error` (Railway: service logs) shows
  `error_type`: `timeout`, `rate_limited`, `server_error`, `config`, `invalid_output`.
- `config` → bad or missing API key / model name. `rate_limited` → usage tier too low for
  traffic; switch `LLM_MODEL` to `claude-haiku-5-5` or raise the tier. `timeout` → provider
  slow; raise `LLM_TIMEOUT_SECONDS` only if p95 allows.
- Clients are not blocked meanwhile; they see "I'm having trouble right now" and simple
  questions, with "Try the assistant again".

**Database unreachable**
- Supabase Free projects **pause after 7 days without activity**. Supabase dashboard →
  Restore project. Prevent with the 5-minute uptime monitor on `/health` (it writes a
  heartbeat).
- Check `DATABASE_URL` uses the **session pooler** host (IPv4), with `+psycopg`.

**Clients report "Please sign in again" right after signing in**
- Token verification failing. New projects need `SUPABASE_JWT_SECRET` **empty** (JWKS);
  legacy projects need it set. Check `SUPABASE_URL` matches the project.

**"No times match your preferences" for everyone**
- Slots ran out (the seed creates two weeks). Re-run the seed (DEPLOY.md §3).

**Unsafe reply replaced (output-check trips) climbing**
- The model is drifting toward times, prices or clinical terms. Check recent prompt or
  model changes; run `make eval` and look at failed cases in `evals/reports`.

**Encryption errors after a redeploy (`InvalidToken`)**
- `FIELD_ENCRYPTION_KEY` changed. Restore the previous key; data written with it cannot be
  read with another.

## Routine

| When | Do |
|---|---|
| Weekly | Re-run the seed for slots; glance at the dashboard (p95 vs targets, failure rate) |
| After changing prompts, model or profile | `make eval`; compare with the previous report in `evals/reports` |
| After changing the OCR pipeline | `make eval` — golden ≥ 90%, held-out reported, **fabricated fields = 0** |
| Before a demo | `make smoke` against the URL |

## Privacy requests

- A Client can withdraw themselves (button at the bottom of every Step; also triggered by
  "delete my data" in chat). The receipt reference is in `consent_log`.
- To confirm a deletion: `select action, receipt, at from consent_log where account_id = '<id>'`
  → a `deleted` row; no rows for that id in `clients`, `assessments`, `identity_details`,
  `bookings`; none in `auth.users` or `auth.audit_log_entries` (by actor or traits.user_id).

## Logs

JSON lines, one per request: endpoint, status, total ms, outcome. They never contain
message text, names, dates of birth, addresses, emails or tokens; unhandled errors log only
the exception type. Turning on `LLM_DEBUG_LOG` is refused outside `APP_ENV=development`.
