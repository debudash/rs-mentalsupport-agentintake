# AI-Powered Onboarding Assistant

## Difficulty & Timebox
**Tier:** Mid–Senior · **Timebox:** 3 days · **Format:** take-home assessment
**Target industry:** Sensitive-service onboarding

*(Raised from 2 days: the +1 day is justified by the combined scope of OCR/document
extraction and an LLM chatbot, plus first-class handling of sensitive PII.)*

## Problem Statement
Build an AI-powered onboarding assistant for users registering for specialized
services. Onboarding today fails for two reasons: registration involves complex,
error-prone data entry (re-typing details from ID and other documents), and users
often arrive under emotional stress, which raises the friction of every extra step.
The assistant reduces both: an LLM chatbot guides the user and performs an initial
assessment, an image-to-text step lets the user photograph a document instead of
typing, an appointment scheduler books the right next step, and supportive content
is surfaced at the moments users are most likely to abandon.
Target user: a person signing up for a specialized (and potentially sensitive)
service who wants to finish onboarding quickly, with minimal typing and minimal stress.

## Business Context
Specialized-service onboarding has high abandonment because it front-loads friction —
long forms, manual document transcription, and uncertainty about next steps — on
users who may already be anxious. Every abandoned registration is a lost customer
plus wasted acquisition spend, so reducing drop-off directly improves conversion and
lowers customer-acquisition cost. Turning a bureaucratic form into a guided, low-typing,
supportive flow is also a durable differentiator in a domain where the emotional quality
of the first interaction shapes long-term trust and retention.

## Illustrative Business Case / Impact Metrics
*Illustrative — assumptions stated inline; validate against real analytics.*
- **Onboarding completion rate:** raise completion from an assumed baseline of
  **~50%** to **~70%** (**+20 pts, ~+40% relative**), by removing manual data entry
  and next-step uncertainty. *(Assumption: 50% baseline is typical for a long,
  document-heavy flow; confirm against product analytics before quoting externally.)*
- **Process efficiency:** a motivated user completes onboarding in **≤ 15 minutes**
  (baseline assumed 25–30 min for a manual, multi-form flow).
- **User satisfaction:** **NPS 70+** target for the onboarding experience.
  *(Note: NPS 70 is ambitious — world-class territory; treat as an aspirational
  target, not a pass condition, and measure the direction of travel.)*
- **Response time (product guardrail):** **< 3 s p95** system response under a stated
  load — see Performance Benchmarks; slow responses re-introduce the friction the
  product exists to remove.

## Tech Stack
Candidates pick their own languages, frontend, and hosting, and briefly justify the
choice in the README; benchmarks must still be met.
**No paid API is required.**
- **AI Frameworks:**
  - **LLM (chatbot + assessment):** **Claude** (Anthropic API) is the suggested LLM.
    **Groq free tier**, **Google Gemini free tier**, **Ollama (local)**, or OpenAI are
    acceptable substitutes if justified.
  - **OCR / document processing:** **Tesseract** or **PaddleOCR** (both free,
    self-hostable). Cloud OCR is an optional substitute, not required.
- **Development Tools:** Git, Docker, RSpec (or Jest for the frontend).

## Functional Requirements
Each Core item has an observable acceptance criterion (pass/fail). Golden sets and
thresholds are defined in **AI Metrics & Test Method**.

### Core (must-have)
1. **LLM assessment chatbot** — a conversational flow gathers the required onboarding
   information and produces a structured assessment/summary.
   *Accept:* the chatbot correctly handles every intent in the defined intent list
   (see AI Metrics) and, given a scripted conversation, emits a structured record
   with all required fields populated; unrecognized inputs get a graceful fallback
   rather than an error.
2. **Image-to-text data entry** — the user uploads a photo of an ID/document and the
   system pre-fills the form.
   *Accept:* on the OCR golden set, the system extracts **name, date of birth, and
   address** at **≥ 90% field-level accuracy**, and every extracted field is shown
   to the user for confirmation/edit before it is saved.
3. **Appointment scheduling** — the user books a next-step appointment from available
   slots.
   *Accept:* a user can view open slots, book one, receive a confirmation, and a
   double-booking of the same slot is rejected; the booking persists across sessions.
4. **Supportive content surfacing** — relevant reassurance/help content is shown at
   friction points.
   *Accept:* given a defined set of trigger conditions (e.g. long pause, upload
   failure, high-stress intent detected), the correct supportive content is surfaced
   for each trigger, and content is never shown when no trigger condition is met.

### Stretch (bonus)
5. **Multi-language support** — chatbot and content available in ≥ 2 languages.
6. **Sentiment-adaptive tone** — the assistant detects user stress/sentiment and
   adapts tone and pacing accordingly.
7. **Advanced analytics** — a dashboard of funnel drop-off, per-step completion time,
   and OCR correction rates.

### Edge Cases & Failure Modes
The solution **must** handle the following; each is an observable expectation, not a
"nice to have". Happy-path-only submissions that skip these should visibly fail review.
- **OCR failure → manual-entry fallback.** When OCR returns no result, low confidence,
  or errors on an image, the flow does not dead-end: the user is offered manual field
  entry and can complete onboarding without the photo step — never an unhandled 500.
- **Partial extraction shown for confirmation.** When OCR extracts only some fields
  (e.g. name + DOB but not address), the successfully read fields are pre-filled and
  clearly marked for confirmation/edit, and the missing fields are left blank for the
  user to complete — the system never silently drops or fabricates a field.
- **Consent revocation + data deletion honored.** A user who withdraws consent, or
  requests deletion, has their document image and extracted PII purged, and processing
  stops; the revocation is logged and the deletion is verifiable (record no longer
  retrievable).
- **Malformed / oversized / non-image upload rejected.** Uploads are validated
  server-side for file type and size; a non-image, corrupt, or over-limit file is
  rejected with a clear user-facing message rather than crashing or being processed.
- **PII never in logs.** Extracted identity fields, raw document images, and chatbot
  transcripts containing PII are never written to application logs, error traces, or
  analytics events — only non-identifying metadata (e.g. field-level success/failure).
- **LLM timeout / failure fallback.** When the LLM provider times out, returns a 5xx,
  or is unreachable, the chatbot degrades gracefully — a clear "try again / continue
  manually" path — never a hang, an unhandled error, or a hallucinated commitment.

## Performance Benchmarks
Load is defined explicitly so results are comparable across candidates.
**Stated load:** 20 concurrent virtual users for 60 s, generated with **k6**
(script committed to the repo).

| Target | Value | Measurement method |
|--------|-------|--------------------|
| Chatbot / API response | < 3.0 s p95 | k6 run at the stated load (20 VUs, 60 s); report p95 |
| OCR extraction latency | < 8.0 s p95 | API timing from image upload receipt to extracted-fields response, 20 runs |
| Scheduling / booking action | < 1.0 s p95 | Server log timing, 20 runs |
| Uptime (deployed demo) | ≥ 99% over the eval window | Uptime check (e.g. cron ping) across the review period |

## AI Metrics & Test Method
- **OCR golden set:** **30 labeled sample ID/documents**, each with expected fields
  (name, DOB, address), spanning clean scans, phone photos, and mild skew/glare;
  includes at least a few near-miss/hard cases. *Threshold:* **≥ 90% field-level
  accuracy** across the extracted fields.
- **Chatbot intent-coverage set:** a defined **intent list** (e.g. provide-details,
  ask-question, request-reschedule, express-distress, out-of-scope) with labeled
  example utterances per intent. *Threshold:* the chatbot routes/handles **every
  intent in the list**, and out-of-scope inputs get a graceful fallback (no crash,
  no hallucinated commitment).
- **Method:** a committed test harness (e.g. `rake ai:eval`) runs both sets and prints
  a scorecard (per-field OCR accuracy, per-intent pass/fail). Model versions, OCR
  engine version, and hardware are recorded in the README. **Sample IDs in the golden
  set must be synthetic/dummy documents — never real user PII.**

## Security, Privacy & Compliance
This domain is explicitly sensitive: it involves emotional stress, specialized
services, and image-to-text of ID/documents (heavy PII). Sensitive-data handling is
**first-class**, not an add-on.
- **Consent capture:** explicit, logged user consent is required before any document
  image is uploaded or processed; the user is told what is collected and why.
- **PII data minimization:** collect and retain only the fields the flow needs;
  do not store the raw document image longer than required to extract and confirm
  fields (extract → confirm → discard image by default).
- **Encryption:** TLS/HTTPS in transit; encryption at rest for the database and any
  stored documents/images.
- **Secure handling of uploaded IDs:** private storage only (signed URLs, never public
  buckets); a stated **retention and deletion policy** (default: purge the source
  image after successful extraction/confirmation), and the user can request deletion
  of their data on demand.
- **Access control:** per-user authN/authZ (Supabase Auth); a user can only access
  their own onboarding record; any staff/admin access is role-scoped and audit-logged.
- **Model/data boundary:** prefer local OCR (Tesseract/PaddleOCR) and a self-hosted or
  free-tier LLM so PII need not leave your infrastructure; if a cloud AI API is used,
  disclose it and avoid sending raw ID images to third parties. Candidates using the
  Claude API must document exactly which PII fields are sent to it and keep that to
  the minimum needed for the chatbot and assessment.
- **Regulatory note:** if the specialized service is **healthcare or financial**, the
  corresponding compliance regime applies (**HIPAA** for health data, **PCI DSS** for
  payment data) — candidates should note which regime applies to their assumed domain
  and how the design supports it.

## Code Quality & Engineering Practices
- **Test coverage ≥ 80%** on core logic (OCR extraction/mapping service, chatbot
  orchestration, scheduling state).
- **Error handling & graceful degradation:** every primary external dependency failing
  (OCR engine, LLM provider, database, network) degrades gracefully with a clear
  user-facing message — graceful fallbacks for failed OCR (offer manual entry) and
  failed LLM calls (retry/queue or manual path); no unhandled 500s and no silent wrong
  results in the demo flow.
- **Observability baseline:** structured error logging (PII-free) and a **health-check
  endpoint** for the API that reports app and dependency (DB/OCR/LLM) reachability.
- **Database migrations & seed:** schema managed via committed migrations, and a
  committed **seed script / fixtures** (including the OCR golden set of synthetic
  documents) so the app runs and is gradeable from a clean checkout.
- **Secure coding for PII:** no secrets in the repo — configuration via environment
  only, with a committed **`.env.example`** documenting every required variable; no PII
  in logs; input validation and file-type/size checks on uploads.
- **Accessibility:** the frontend meets a baseline — keyboard navigation, labeled form
  controls, sufficient color contrast, and status conveyed by more than color alone.
- **CI:** runs tests + linter (RuboCop / ESLint) on every push; README documents
  setup, env vars, and the AI eval harness.

## AI Usage Disclosure
**Required.** Document, in `AI_USAGE.md`: which AI tools were used and for what
(codegen, OCR, chatbot/assessment, sentiment), which LLM/OCR engines and versions,
and any prompts or configuration that materially shaped the solution.

## Submission Requirements
- GitHub repository (with README + `AI_USAGE.md`)
- Committed **seed script / fixtures** and the synthetic OCR golden set, plus a
  `.env.example`, so the app runs and is gradeable from a clean checkout with no real PII.
- **Grader quick-start:** the README must let a reviewer run the app, seed data, and the
  test + AI eval harness **in minutes** — setup steps, environment variables, seed
  command, demo credentials (if any), and how to run the committed test suite.
- Deployed application URL
- Documentation
- Video demo (showing the chatbot flow, image-to-text data entry with confirmation,
  a booking, and supportive-content surfacing)

## Evaluation Rubric (100 pts; pass ≥ 70)
| Criterion | Weight | Adequate → Excellent |
|-----------|:------:|----------------------|
| Core functional requirements work | 30 | 1–2 flows → all 4 flawless with confirmation UX, incl. edge cases & failure modes |
| AI quality (OCR + chatbot meet thresholds) | 20 | Meets OCR OR chatbot → both, incl. hard cases |
| Security, privacy & compliance | 20 | Basic auth → consent, minimization, retention/deletion, scoped access |
| Code quality & architecture | 15 | Works but coupled → clean services, ≥80% coverage, CI |
| Performance (meets benchmarks) | 10 | Sluggish → all p95 targets met under stated load |
| Docs, AI disclosure & demo | 5 | Sparse → clear README, eval harness, crisp demo |
