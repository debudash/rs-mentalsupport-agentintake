# Architecture

Written for reviewers and future maintainers. Terms in capitals (Client, Step,
Assessment…) are defined in the [glossary](GLOSSARY.md).

## High-level architecture

```mermaid
flowchart LR
  subgraph Browser
    UI[React app<br/>stepper, chat, review screen,<br/>image preparer, idle detector]
  end
  subgraph Railway["Railway — one container"]
    API[FastAPI API<br/>thin routes]
    Core[Domain modules<br/>Onboarding engine · Safety screen<br/>Intake conductor · Scheduling<br/>Support triggers · Consent & Withdrawal]
    OCR[Document reader<br/>OpenCV + Tesseract]
    Static[Built React files]
  end
  subgraph Supabase["Supabase (US East)"]
    Auth[Auth]
    PG[(Postgres<br/>RLS on every table)]
  end
  LLM[LLM provider<br/>Anthropic / OpenRouter / Ollama]

  UI -- sign in --> Auth
  UI -- HTTPS + login token --> API
  API --> Core
  Core --> OCR
  Core -- one structured call per message,<br/>masked text only --> LLM
  API -- pooler (IPv4) --> PG
  API -- verify token (JWKS/secret),<br/>delete user at Withdrawal --> Auth
  Static -.served by.- API
```

- **One container** serves the API and the built frontend, with Tesseract installed. One
  URL, no cross-origin setup, one deploy.
- **Supabase** provides sign-in and Postgres. The browser uses Supabase only to sign in;
  all data goes through the API. Row-level security is on for every table with no
  browser-facing policies, so the browser's public key reads nothing.
- **The LLM** sees only masked chat text. Identity details and images never leave the
  container.

## Low-level design: modules

Deep modules — a small interface over a lot of behaviour — each tested through its
interface. Swappable dependencies sit behind seams with a Fake adapter for tests.

| Module | Interface | Hides | Seams |
|---|---|---|---|
| Onboarding engine (`domain/onboarding.py`) | `state(facts)`, `check(facts, action)` | Step order, gating, Crisis pause, completion | none (pure) |
| Safety screen (`domain/safety.py`) | `screen(message) → clear / check_in / crisis` | two-tier phrase lists, normalisation | none (pure) |
| Intake conductor (`domain/intake.py`) | `respond(state, turn) → (state, reply)`, `prompt_for(state)` | checklist, masking, the one LLM call, validation, output check, scripted fallback | LLM port |
| LLM port (`llm/`) | `complete(system, messages, schema, timeout) → dict` or `LLMFailure` | provider wire formats, error mapping | Anthropic · OpenAI-compatible · Fake |
| Document reader (`ocr/`) | `read_identity(bytes) → fields + failure reason` | content sniffing, EXIF, card detection, deskew, Tesseract, parsing, confidence | OCR engine: Tesseract · Fake |
| Scheduling (`scheduling.py`) | `open_slots`, `book`, `current_booking`, `calendar_file` | window, filters, one active booking, reschedule transaction, unique index | database |
| Support triggers (`domain/support.py`) | `decide(event, shown, paused) → trigger / None` | three triggers, once per Step | none (pure) |
| Consent & Withdrawal (`consent.py`) | `grant`, `set_id_scan`, `withdraw → receipt` | consent log, cascade delete, auth deletion, audit-row cleanup | auth admin: Supabase · Fake |
| Access control (`access.py`) | `identify(request) → Caller`, `clinician_view` | token verification (HS256 or JWKS), roles, Access log | token verifier |
| Telemetry (`telemetry.py`) | `timed(stage)`, `note(...)`, `log(...)` | PII-free JSON logs, timing records, `Server-Timing` | — |
| Journeys (`journeys.py`) | `start`, `record`, `record_ocr_review`, `unlink` | anonymous funnel events, once per Journey, unlink at Withdrawal | database |
| Dashboard queries (`dashboard.py`) | `dashboard(db, hours)`, `funnel`, `ocr_corrections` | percentiles, funnel drop-off and medians, suppression of small counts (and nothing derived from them) | database |
| Service profile (`profile/`) | `get_profile()` | everything service-specific, validated at startup | file |

Shallow on purpose: HTTP routes (`api/routes.py`), the encrypted column type
(`db/crypto.py`), migrations and seed.

## Sequence: one Intake message

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant A as API
  participant C as Intake conductor
  participant S as Safety screen
  participant L as LLM provider
  participant D as Postgres
  B->>A: POST /api/intake/messages {text}
  A->>D: load Intake state (answers, last 6 messages, flags)
  A->>C: respond(state, turn)
  C->>S: screen(text)
  alt unambiguous crisis
    S-->>C: crisis
    C-->>A: Crisis pause + resources (no LLM call)
  else ambiguous idiom
    S-->>C: check_in
    C-->>A: "Do you mean thoughts of harming yourself?" [Yes] [No]
  else clear
    C->>C: mask phone / email / dates / addresses
    C->>L: ONE structured call: intent, answers, approved-answer id, reply
    alt timeout / 5xx / invalid output
      L-->>C: LLMFailure
      C-->>A: apology + next scripted question (+ retry option)
    else ok
      L-->>C: JSON
      C->>C: validate every value against the profile
      C->>C: output check on the reply
      C->>C: checklist picks the next question
      C-->>A: reply, quick replies, signals
    end
  end
  A->>D: save answers (encrypted where sensitive), flags, messages
  A-->>B: messages + next question (+ supportive card if high stress)
  Note over A: timing record: llm_ms, db_ms, total_ms, outcome, intent — no text
```

## Sequence: ID photo to confirmed details

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant A as API
  participant R as Document reader
  participant D as Postgres
  B->>B: resize to 2000 px, apply orientation, re-encode (drops EXIF/GPS)
  B->>A: POST /api/identity/scan (multipart)
  A->>A: require ID scan consent
  A->>R: read_identity(bytes) in a worker thread
  R->>R: sniff type from bytes, size limit, decode
  alt not an image / too big / corrupt
    R-->>A: UploadRejected(reason, message)
    A-->>B: message + "upload problem" supportive card
  else image
    R->>R: find card → flatten (or deskew), then even out contrast (CLAHE)
    R->>R: Tesseract → lines with confidence
    R->>R: parse by labels, else by shape (only if unambiguous)
    R->>R: keep fields that parse AND confidence ≥ 70, else blank
    R-->>A: fields (read / blank)
    A-->>B: pre-filled review form
  end
  Note over A,R: the image exists only in memory for this request
  B->>A: POST /api/identity/confirm (edited fields + which were changed)
  A->>A: validate fields, adults only
  A->>D: store encrypted name, DOB, address
```

## Sequence: Withdrawal

```mermaid
sequenceDiagram
  autonumber
  participant B as Browser
  participant A as API
  participant D as Postgres
  participant U as Supabase Auth
  B->>A: POST /api/withdraw {confirm: true}
  A->>D: delete booking (slot released), conversation, identity, assessment, client, account
  A->>D: consent log: "deleted" + receipt reference
  A->>U: admin delete user
  A->>D: delete auth.audit_log_entries naming the user (actor_id or traits.user_id)
  A-->>B: receipt (reference, time, what was deleted)
  Note over A: later calls with the old token → 401, and the Account is never re-created
```

## Data model

```mermaid
erDiagram
  accounts ||--o| clients : "role = client"
  clients ||--o| assessments : has
  clients ||--o{ intake_messages : "until Intake completes"
  clients ||--o| identity_details : has
  clients ||--o| bookings : "one active"
  slots ||--o| bookings : "one active"
  clinicians ||--o{ slots : offers
  accounts {
    string id PK "Supabase user id"
    string role "client | clinician | operator"
  }
  identity_details {
    text legal_name "encrypted"
    text date_of_birth "encrypted"
    text address "encrypted"
    json edited "field -> changed? (no values)"
  }
  assessments {
    json answers "structured, non-sensitive"
    text reason_text "encrypted"
    text safety "encrypted"
  }
  bookings {
    string status "partial unique index: one active per slot and per client"
  }
```

Also: `consent_log` and `access_log` (permanent, identity-light), `timing_records` and
`daily_counters` (aggregate, no account ids), `journey_links` (account → random journey,
deleted at Withdrawal) and `journey_events` (journey, step event, time, per-field OCR
flags — nothing else), `heartbeat`, `eval_reports`.

## Deployment view

See [DEPLOY.md](DEPLOY.md). Locally, `docker compose` runs the same image against
Supabase started by the Supabase CLI.
