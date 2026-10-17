# rs-assist — AI-Powered Onboarding Assistant

Take-home assessment for Riverside Partners LLC (Director, AI Acceleration; technical
contact Melissa Hargis). Timebox 2–3 days from 2026-10-12.

## Source of truth

- [docs/source/client-prd.md](docs/source/client-prd.md) — the client's spec:
  acceptance criteria, edge cases, benchmarks, eval method and the 100-pt rubric
  (pass ≥ 70).
- [docs/source/client-brief.md](docs/source/client-brief.md) — client brief summary.

Where the two differ, the client PRD is the stricter and wins (e.g. `AI_USAGE.md` is
required, timebox 3 days). **Our PRD, [docs/PRD.md](docs/PRD.md), is the build source
of truth**; the decision notes below are its design history.

## Documentation layout

- `docs/adr/NNNN-slug.md` — architecture decision records ONLY.
- `docs/` — every other document: PRD, USERS, ARCHITECTURE (HLA + LLA + sequence
  diagrams), DEPLOY, TEST_PLAN, RUNBOOK, DECISIONS (index of ADRs + smaller decisions),
  AGENTS (if subagents build slices), AI_LOG (AI agent action tracking).
- `docs/source/` — client-supplied originals, unedited in substance.
- Root keeps only `README.md`, `AI_USAGE.md` (client PRD expects it beside the README;
  linked from `docs/`) and `CLAUDE.md`. Glossary is `docs/GLOSSARY.md`.
- Build method: tracer bullet first (thinnest deployed end-to-end path), then vertical
  slices.

## This is a graded submission, not a teaching demo

The global "default demo stack & philosophy" (happy-path first, light error handling,
Streamlit) does NOT apply as-is. The PRD makes edge cases, graceful degradation,
≥ 80% coverage, CI, k6 load tests, a deployed URL and PII safety pass/fail items.
The stack is open (justify in README) but these are fixed by the brief:

- Supabase Auth for per-user authN/authZ
- k6 load test script committed (20 VUs, 60 s)
- Local OCR (Tesseract or PaddleOCR); raw ID images never go to a cloud AI API
- Free-tier / self-hosted LLM acceptable; if the Claude API is used, document exactly
  which PII fields are sent
- Docker; committed migrations, seed script, synthetic 30-doc OCR golden set
- `.env.example`, no secrets, no PII in logs, health-check endpoint
- CI running tests + linter on every push
- An eval harness command that prints a scorecard (per-field OCR accuracy,
  per-intent pass/fail)

## Build status (2026-10-17)

Built and verified locally (see docs/AI_LOG.md, docs/ISSUE_LOG.md). Open items that need
the user: real-model intent eval (`LLM_PROVIDER=anthropic make eval` — no key on this
machine), Railway deploy (project not linked; hosted Supabase keys needed — docs/DEPLOY.md),
pushing to GitLab, enabling CI (`CI_ENABLED`) and the hook (`make hooks`), demo video.
Dashboard layer 2 (funnel + OCR corrections) built 2026-10-17. Not built: stretch #6,
stretch #5 — listed in the README.
Bug fixes follow the Issue/Root cause/Fix/Test commit format; log them in docs/ISSUE_LOG.md.

## Timebox and scope (2 days — user, 2026-10-16)

- **Day 1 AM:** tracer bullet — whole flow end to end with scripted Intake + manual
  Identity, deployed to Railway; timing records instrumented from the start.
- **Day 1 PM:** LLM Intake (intents, crisis check, LLM-down fallback) + intent eval.
- **Day 2 AM:** OCR (golden + held-out sets, upload, review screen, upload errors) +
  supportive content.
- **Day 2 PM:** Withdrawal/deletion, Clinician view, dashboard, k6, docs, demo video.
- **Kept by user despite cost:** Operations dashboard (it is our observability, since
  no LangSmith) and the Clinician view. **Docs are written at the end**, not up front.
- **Cut order if behind:** stretch #6 → Playwright → Journey/funnel analytics →
  field encryption.
- **Dashboard in two layers:** Layer 1 (MUST) = observability — Performance, LLM
  health, AI quality panels over the timing records + latest eval report. Layer 2
  (IF TIME, day 2) = product analytics — Onboarding funnel + OCR corrections (needs
  Journey records + unlink-at-Withdrawal). **Tracked item:** if Layer 2 is not built,
  the README must list it as planned/not delivered, with the Journey design as the
  path.
- **Fixes adopted from the self-review:** (1) exactly ONE structured LLM call per Client
  message (returns intent + extracted values + Approved-answer id + reply) to hold the
  3 s p95; (2) "I'm 18 or older" confirmation on the Consent screen, DOB check stays as
  verification; (3) a held-out OCR set (~10 IDs, different layout/fonts never tuned
  against), reported separately from the 30-ID golden set; (4) honest security claim:
  the browser cannot reach tables (Data API off, RLS on with no browser-facing
  policies) and the API enforces ownership on every request — we do NOT claim
  per-request RLS as a second layer.
- **Supabase auth audit log:** `auth.audit_log_entries` holds IP + user agent and is
  probably not purged on user deletion. Verify during the tracer bullet (create →
  delete a user → inspect). If rows remain, Withdrawal deletes that Account's rows in
  the same operation, asserted by the deletion test. Anything Supabase keeps outside
  our DB (platform logs) → README known limit.
- **Crisis check, two tiers:** unambiguous self-harm phrases ("kill myself", "end my
  life", "want to die", "hurt myself", "suicide", "don't want to be here anymore") →
  immediate Crisis pause. Ambiguous idioms ("killing me", "can't go on", "done with
  everything") → a Safety check-in ("do you mean thoughts of harming yourself?"; Yes →
  Crisis pause, No → high-stress supportive card). LLM context flag and the Safety
  question remain. Eval rule: unambiguous → pause; ambiguous → check-in; plain stress →
  neither.

## Decisions so far

- **Domain:** outpatient mental-health / counseling intake (HIPAA is the regime to
  address in the README). Assessment stays non-clinical — no diagnosis or advice.
  Crisis / self-harm messages route to emergency resources, never to the scheduler.
- **One service, swappable Service profile:** no multi-service engine; all
  service-specific content lives in one module so another service is a file swap.
- **Vocabulary:** see [docs/GLOSSARY.md](docs/GLOSSARY.md).
- **Flow:** stepper — Sign in → Consent → Intake (chat with quick-reply buttons, free
  text always allowed) → Identity (ID scan + review screen, or manual entry) → Book →
  Done. Progress saved at every step; crisis resources (988) link visible on every step.
- **The server owns the procedure, not the LLM:** a server-side state machine gates
  Steps; Intake is a server-held checklist of required Assessment items — the LLM asks
  and extracts, the server decides what's missing and when Intake is complete.
- **Assessment (option b):** reason (category + text), duration, self-rated distress
  1–5, therapist preferences, session format, availability, plus one direct Safety
  question → "yes" triggers a Crisis pause. No PHQ-9/GAD-7 (README: what a real clinic
  would add).
- **Intents (8, the eval contract):** provide-details, ask-question (approved FAQ text
  only), request-reschedule (point to Book; bot never books/promises), express-distress
  (supportive content + gentler tone), crisis-risk (Crisis pause), request-human
  (contact options), withdraw-consent (route to consent/deletion screen; LLM never
  deletes), out-of-scope (gentle redirect). Crisis detection = deterministic phrase
  check before the LLM OR LLM label OR Safety question "yes". Eval: 6–10 labeled
  utterances per intent incl. near-misses.
- **Guarded LLM ("checks before and after the LLM, approved text in the middle"):**
  (1) input check — deterministic crisis phrases before the LLM; (2) ask-question →
  LLM picks an FAQ id (or none) from ~15–20 Approved answers in the Service profile and
  the server shows the text verbatim — no RAG; (3) output check — deterministic filter
  on every LLM reply blocks commitments (dates/times, prices, "confirmed", "you will be
  seen"), clinical language (diagnoses, medication) and Identity-detail-like strings;
  a tripped reply is replaced by a safe fallback line.
- **Supportive content (3 triggers only):** long pause (45 s no interaction on an
  incomplete Step), upload problem (rejected upload or OCR failure/no usable fields →
  offer manual entry), high stress (express-distress intent or self-rated distress
  4–5). One card at a time, dismissible, non-blocking, once per trigger per Step.
  Crisis pause and the persistent 988 link are NOT supportive content. Browser reports
  events; a pure server function maps events → content id or none.
- **Consent:** two consents — Onboarding data (required) and ID scan (optional;
  declining → manual entry). Each has a version. "Withdraw and delete everything"
  (explicit confirm screen) deletes Assessment, Intake conversation, Identity details,
  progress, booking (slot freed) AND the Account; keeps only the identity-free Consent
  log (account id, action, timestamp, consent version). Shows a deletion receipt;
  data endpoints then return not-found (asserted by a test). Chat withdraw-consent only
  routes to this screen.
- **Minimization:** Intake conversation stored only while Intake is in progress (for
  resume + LLM context), deleted when Intake completes — the Assessment survives.
  Before any LLM call, deterministic masking replaces phone numbers, emails, dates and
  street addresses with placeholders. README states the limit: names in free text and
  the Assessment's free-text reason are not reliably masked.
- **Booking:** a 30-min Initial consultation with one of 3–4 fictional Clinicians;
  seeded slots for the next 14 days, ≥ 2 h notice. Slots filtered by the Assessment's
  session format + time-of-day availability ("show all times" toggle). One active
  Booking per Client; reschedule frees the old slot in the same transaction. DB
  constraint: a slot has at most one active Booking (+ friendly "just taken" with
  nearest alternatives; concurrent-booking test). Confirmation on screen + .ics
  download (no email). UTC stored, Client's local time shown with zone label.
- **Identity step:** JPEG/PNG/HEIC ≤ 8 MB, validated server-side by content (must
  decode as an image); failures → upload-problem Trigger + manual entry. A field is
  pre-filled only if it parses validly AND Tesseract confidence ≥ threshold (~70),
  else left blank — never guessed. Review screen: every field editable, status in
  text + icon (not color only); saved only on "These details are correct". DOB must
  be 18+ (adults-only service; under-18 → polite stop + resources). Track per-field
  edited true/false (no values) for an OCR correction-rate metric.
- **Mobile capture:** `<input type="file" accept="image/*" capture="environment">`
  (native camera on phones, file picker on desktop). Browser resizes to ~2000 px long
  edge, JPEG ~85%, applies EXIF orientation then strips EXIF (removes GPS). Server
  accepts HEIC via pillow-heif. No getUserMedia overlay or QR handoff (README: upgrades).
- **LLM failure:** each Assessment item has a scripted question + answer type in the
  Service profile, so Intake works without the LLM. 5 s timeout, no in-request retry.
  One failure → plain apology + next scripted question + "Try the assistant again";
  2 consecutive failures → scripted mode for the rest of Intake. Invalid LLM output
  (bad schema/intent/value) is treated as a failure — never shown or saved. Crisis
  check, Safety question, Approved answers (as buttons), Triggers keep working.
  `/health` reports LLM reachability; logs `llm_error` (provider, type, latency only).
  Tests fake timeout + 500 and assert Intake still completes.
- **Staff access:** minimal read-only Clinician view — a Clinician sees only Bookings
  in their own Slots, with the Assessment + Client first name (no DOB/address). Roles
  Client / Clinician enforced in FastAPI (see scope note on RLS). Every record view writes to an
  Access log (who, which Client, when), asserted by a test. Seed creates 3–4 Clinician
  Accounts with demo logins in README. No admin role (Operator is read-only aggregates, see below), no editing, no
  Slot-management UI.
- **Sign-in:** Supabase email + password, email confirmation OFF for the demo (free
  plan's built-in email is heavily rate-limited). Seeded demo Client + Clinician
  Accounts listed in README.
- **Performance:** k6 realistic journey (sign in → state → Intake messages with 5–10 s
  think time → list Slots → book) at 20 VUs / 60 s against real Anthropic (needs a
  higher rate tier — user to check tier / ~$40 credits); plus a repeatable k6 run with
  `LLM_PROVIDER=fake` (~800 ms simulated latency) for CI and keyless graders. OCR and
  booking: 20-run scripts timed via a `Server-Timing` header. Results committed to
  `docs/PERFORMANCE.md` with date, model, hardware.

- **No LangChain / LangSmith** ([ADR 0002](docs/adr/0002-no-langchain-langsmith.md)):
  official SDKs + Pydantic; own eval harness (`make eval`) writing
  `evals/reports/<date>.json` + markdown with raw output for failed cases; every request
  logs one PII-free JSON line with request id and stage timings (`llm_ms`, `db_ms`,
  `ocr_ms`, `total_ms`) + intent/provider/model/outcome; dev-only `LLM_DEBUG_LOG`
  (refused unless `APP_ENV=development`) writes prompts to a git-ignored file. A
  dashboard surfaces these.
- **Operations dashboard** (also covers PRD stretch #7): one page, charts refreshed on
  load, behind a new read-only **Operator** role (demo login in README; separate from
  Clinician). Panels: Performance (p50/p95 per endpoint vs 3 s / 8 s / 1 s targets),
  LLM health (calls, error types, fallback-to-scripted rate, output-check trips,
  provider/model), AI quality (latest eval scorecard), Onboarding funnel (reached /
  drop-off / median time per Step, Crisis pauses, Withdrawals), OCR corrections (per
  field: pre-filled / blank / edited). Aggregate and PII-free; timing records in a
  Postgres table; counts < 5 suppressed.
- **Analytics vs Withdrawal:** funnel events keyed by a random Journey id (no Account
  id); an Account→Journey link row is deleted on Withdrawal, leaving unlinkable events
  (step, event, timestamp, outcome only — no answers, Identity details or free text).
  Per-request timing records carry no Account or Journey id. Crisis pauses recorded
  only as a daily count with no Journey link.
- **Field-level encryption:** app-side Fernet (`cryptography`) with
  `FIELD_ENCRYPTION_KEY` held only by the app server, on Identity details (name, DOB,
  address), the Assessment's free-text reason and the Safety answer. Structured
  Assessment fields stay plain (category, distress, format, availability). Test reads
  the raw row and asserts no plaintext. README: key location + rotation via a key
  manager in production; `.env.example` has a placeholder + key-generation command.
- **Grader quick-start:** Docker + Supabase CLI only. `make setup` (copy `.env`,
  generate key, `supabase start`), `make seed`, `make up` (app on :8000), `make test`,
  `make eval`, `make load`; same targets as `scripts/*.sh` for Git Bash/WSL.
  `.env.example` defaults to `LLM_PROVIDER=fake` so it runs keyless. uv (Python) and
  npm only for local development.
- **Repo & CI (no GitHub):** remote is Gauntlet's self-hosted GitLab
  (labs.gauntletai.com) with NO shared runners. `.gitlab-ci.yml` committed from day one
  but dormant via `workflow: rules: if $CI_ENABLED == "true"`; jobs tagged
  `rs-assist-local` for the user's own project runner (GitLab Runner in Docker Desktop,
  registered later). Jobs: lint → test (coverage gate) → build → deploy (`railway up`
  on `main` with masked `RAILWAY_TOKEN`), each calling `make` targets. User enables CI
  later by registering the runner + setting `CI_ENABLED=true`.
- **Pre-push hook:** `.githooks/pre-push` runs `make ci`; inactive until the user runs
  `make hooks` (`git config core.hooksPath .githooks`) at a later stage.
- **Deploy:** Railway CLI — `make deploy` → `railway up` (after one-time `railway login`
  + `railway link`); secrets in Railway env vars. Verify `.env` is not uploaded on
  first deploy.
- **Accessibility:** WCAG 2.1 AA on sign-in, Consent, Intake, Identity review,
  Scheduling, Withdrawal, Clinician view. Keyboard-complete with visible focus +
  skip link + managed focus on Step change / card appearance; real labels; ARIA live
  region for chat messages and supportive cards; errors linked to fields; text + icon
  status; no time limits; reduced-motion respected. Proof: eslint-plugin-jsx-a11y +
  vitest-axe (zero violations per Step screen) + manual keyboard checklist in
  `docs/ACCESSIBILITY.md`. One Playwright keyboard-only happy path only if time
  remains after #6.
- **Stretch:** #7 analytics = the Operations dashboard (core plan). #6
  sentiment-adaptive tone ONLY after core + edge cases are done: high-stress signal →
  "gentle" prompt mode (shorter, more acknowledgement, one question at a time) +
  quick-reply buttons on every question + offer to pause; deterministic tests. #5
  multi-language skipped (README: production path via per-language Service profile,
  crisis phrases, eval examples).

## README must cover (collected during design)

- Stack justification (FastAPI + React; why not Rails — ADR 0001).
- HIPAA-ready, not HIPAA-compliant: synthetic data; production needs a Supabase BAA
  (paid plan + HIPAA add-on) and equivalent agreements with the LLM provider.
- Exactly what reaches the LLM: masked chat text only; never Identity details or
  images. Limits of masking (names in free text). OpenRouter `:free` models =
  synthetic data only (may log prompts); benchmarks were run on Anthropic.
- Retention: ID images never stored; Intake conversation deleted when Intake
  completes; Withdrawal deletes everything + Account, keeps identity-free Consent log.
- Production upgrades: magic-link / passwordless sign-in and email confirmation via a
  proper email provider; email booking confirmations; in-page camera with card
  overlay / desktop-to-phone QR handoff; RAG once Approved answers grow into policy
  documents; PHQ-9 / GAD-7 screeners a real clinic would add; admin console and Slot
  management; multi-language.
- Swap in a real Service profile / SOP to re-target the assistant (reuse story).
- Supabase Free-plan pausing and the heartbeat keep-alive; uptime evidence.
- GitLab limitation: Railway push-to-deploy supports GitHub only, so deployment is via
  the Railway CLI (`make deploy`) or the GitLab CI deploy job; CI runs on a
  self-registered project runner (instance has no shared runners).
- Model versions, OCR engine version and hardware used for evals and benchmarks.

## Stack decision

- **Backend:** Python, FastAPI. Tests: pytest + pytest-cov (≥80% on core), respx for
  faking LLM HTTP. Lint/format: ruff.
- **Frontend:** React, Vite, TypeScript. Tests: Vitest + React Testing Library. Lint:
  ESLint (+ jsx-a11y) + Prettier.
- **Why not Rails:** see [docs/adr/0001-fastapi-react-not-rails.md](docs/adr/0001-fastapi-react-not-rails.md).
- **Database:** Supabase Postgres (Free plan, US East / us-east-1 — host the app
  nearby) for both auth and data; local dev via
  `supabase start`. FastAPI is the only data path — Data API (PostgREST) disabled, the
  browser uses supabase-js for sign-in only. Every table has RLS enabled in the
  committed migrations with no browser-facing policies (don't rely on the hosted
  "automatic RLS" setting); ownership is enforced by the API. Free plan
  pauses after 7 idle days, so `/health` writes a heartbeat row and an uptime pinger
  hits it.
- **LLM:** one provider interface, two adapters, selected by env (`LLM_PROVIDER`,
  `LLM_MODEL`, keys, `LLM_TIMEOUT_SECONDS`): Anthropic, and an OpenAI-compatible adapter
  (OpenRouter by default; optional `LLM_BASE_URL` also reaches local Ollama). Deployed
  demo and k6 benchmarks use Anthropic. OpenRouter `:free` models satisfy "no paid API
  required" but are rate-limited and may log prompts — README: synthetic data only.
  OCR identity fields (name, DOB, address) are never sent to any LLM.
- **OCR:** Tesseract 5 + OpenCV preprocessing (deskew, crop, contrast); PaddleOCR is
  the fallback only if hard cases miss 90%. The ID image is processed in memory and
  never written to disk or storage — only extracted fields leave the request.
- **OCR golden set:** a seeded generator script (Pillow + Faker) renders 30 cards from a
  fictional issuer ("State of Riverside") — 10 clean, 10 phone-photo, 10 hard (skew,
  glare on a field, two-line address, unusual names, cut-off field). Committed with
  `labels.json`. Scoring: 90 fields, exact match after normalization (ISO dates;
  trimmed, case-insensitive text); report per-field and overall accuracy.
- **Hosting:** Railway (Hobby), US East (Virginia), one Docker container — FastAPI
  serves the built React app; Tesseract installed in the image. App sleeping OFF.
  Supabase stays managed (auth + Postgres); FastAPI connects via the Supabase
  **connection pooler** URL (IPv4), not the IPv6-only direct URL. Uptime pinger hits
  `/health`, which writes the Supabase heartbeat.
