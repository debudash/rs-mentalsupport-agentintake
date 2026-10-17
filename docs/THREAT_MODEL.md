# Threat model

One page, for reviewers and a future security review. Scope: the deployed app (one
container), Supabase Auth + Postgres, the LLM provider. Data is synthetic; the model is
written as if it were real mental-health intake data, which is what HIPAA would cover.
Data flow and the PII boundary: [ARCHITECTURE.md](ARCHITECTURE.md#data-flow-and-the-pii-boundary).

## What we protect

| Asset | Why it matters | Where it lives |
|---|---|---|
| Identity details (name, DOB, address) | Identifies the person | Postgres, encrypted per field |
| Assessment, especially the free-text reason and Safety answer | Mental-health information — the most sensitive data here | Postgres; free text encrypted |
| The ID image | Full identity document | Request memory only — never stored |
| Intake conversation | May contain anything the Client typed | Postgres, encrypted; deleted when Intake completes |
| That a person is seeking counseling at all | Even the fact of an Account is sensitive | Supabase Auth; our Account row |
| `FIELD_ENCRYPTION_KEY`, service-role key, LLM key | Unlock everything above | App server environment only |

## Who might attack, and how

| Actor | Threat | Mitigation | Proof |
|---|---|---|---|
| **Another Client** | Read or change someone else's data by guessing ids | Every Client route derives the Account from the verified login token — no Client route takes an id at all, so there is nothing to guess | `test_api_flow.py::test_unauthenticated_and_bad_tokens`, `::test_roles_are_enforced` |
| **Anyone with the public (anon) key** | Query tables directly through Supabase, bypassing the API | Data API disabled; RLS on every table with **no** browser-facing policies; `anon` privileges revoked in migrations | Checked live 2026-10-17: the anon key gets "permission denied" (42501) on `clients`, `identity_details`, `assessments`, `bookings` |
| **A Clinician** | Browse Clients who aren't theirs | Clinician sees only Bookings in their own Slots, first name + Assessment only (no DOB/address); every view written to the Access log | `test_api_flow.py::test_clinician_sees_only_own_bookings_and_views_are_logged` |
| **The Operator** | Re-identify people from analytics | Dashboard is aggregate only; counts < 5 suppressed (and nothing derived from them); Journeys carry a random id, unlinked at Withdrawal; timing records carry no Account id | `test_adapters_and_dashboard.py`, `test_journeys.py` |
| **A Client (prompt injection)** | Make the assistant promise appointments, give clinical advice, or leak its instructions | The LLM has no tools and no data access; its output must match a JSON schema; extracted values must be allowed values; every reply passes an output check (times, prices, promises, clinical terms) and is replaced if it trips; Approved answers are shown verbatim from the Service profile, not generated | `test_intake.py`, `test_domain_pure.py` output-check tables, intent eval |
| **A Client in crisis** (not an attacker, but the highest-harm case) | The assistant misses self-harm language or improvises counseling | Deterministic crisis check runs **before** the LLM; two tiers (crisis pause / check-in); 988 on every screen; the assistant never counsels | Intent eval: crisis 100% incl. subtle cases |
| **Malicious upload** | Crash the server or exploit the image parser | Size limit (8 MB) checked before decoding; content decoded server-side (file name ignored); Pillow's decompression-bomb guard; image held in memory only | `test_ocr.py::test_bad_uploads_are_rejected_with_a_reason` |
| **Someone with log access** | Read personal data from logs or error traces | Logs carry endpoint, timings, outcome only; the error boundary logs the exception *type*, never the message or input | `test_api_flow.py::test_no_personal_data_in_logs_or_timing_records` (runs a full flow with seeded PII, then greps logs and timing records) |
| **Database dump / backup leak** | Read identity and Assessment text | Field-level encryption with a key that lives only on the app server, not in the database | `test_api_flow.py::test_sensitive_fields_are_encrypted_at_rest` (reads the raw row) |
| **The LLM provider** | Retain or train on what it receives | Only masked chat text is sent (phones, emails, dates, addresses replaced); never Identity details, images or button answers | README "Exactly what reaches the LLM"; masking tests |
| **Credential stuffing / brute force** | Take over a Client Account | Supabase Auth's built-in rate limits; 8-character minimum password | Supabase configuration |
| **A Client who withdraws** | (A right, not a threat) — data must actually go | Withdrawal deletes all their data, the Auth user and Supabase's auth audit rows; consent log keeps only an identity-free record | `test_api_flow.py::test_withdrawal_deletes_everything_and_is_verifiable`; `test_postgres_withdrawal.py` ([ISSUE-001](ISSUE_LOG.md)) |

## Residual risks (accepted for the demo, listed for production)

- **Names in free text** ("I'm Jane") are not reliably masked before the LLM. Production:
  a named-entity masker, or keep free text out of the prompt entirely.
- **No API rate limiting** of our own (only Supabase's on sign-in). Production: per-Account
  and per-IP limits at the edge, especially on the LLM-backed chat endpoint (cost abuse).
- **Key management:** the encryption key is an environment variable. Production: a key
  manager (KMS) with rotation and envelope encryption.
- **Supabase platform logs** (outside our database) keep sign-in metadata on Supabase's
  schedule; we can't delete them at Withdrawal.
- **No BAA** with Supabase or the LLM provider — required before any real patient data.
  The build is HIPAA-*ready*, not HIPAA-compliant (README).
- **Email sign-up without confirmation** (demo setting) means an Account doesn't prove
  email ownership. Production: confirmation or magic links via a proper email provider.
- **Fault injection** could weaken a deployment if misconfigured — the app refuses to
  start with `FAULT_INJECT` set when `APP_ENV=production` (`test_faults.py`).
