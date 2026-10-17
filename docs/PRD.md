# PRD — AI-Powered Onboarding Assistant (rs-assist)

- **Client:** Riverside Partners LLC — Director, AI Acceleration (technical contact:
  Melissa Hargis)
- **Source spec:** [client PRD](source/client-prd.md) · [client brief](source/client-brief.md)
- **Vocabulary:** [GLOSSARY.md](GLOSSARY.md) — capitalised terms below are defined there
- **Decisions:** [ADRs](adr/)
- **Timebox:** 2 days · **Status:** approved for build, 2026-10-16

---

## Problem Statement

A person who decides to start counseling is often anxious, tired or overwhelmed at the
exact moment they sign up. Today's onboarding for specialized, sensitive services asks
that person to do the hardest version of paperwork: long forms, re-typing details from
an ID card, no sense of how much is left or what happens next, and no help when they
stall. About half of people who start give up. Each one who leaves is someone who wanted
help and did not get it — and, for the Service, a lost Client and wasted acquisition
spend.

From the Client's side the problem is: *"I've finally decided to reach out, and now I'm
faced with a bureaucratic process that makes me feel worse, asks me to type things I
could just show, and doesn't tell me what's going on."*

From the Service's side: completion sits near 50%, onboarding takes 25–30 minutes, and
the Service cannot see where or why people drop off.

## Solution

A guided, low-typing, supportive Onboarding for an outpatient mental-health counseling
Service, made of four Steps the Client sees on a progress bar — **Consent → Intake →
Identity → Scheduling** — ending in a booked Initial consultation.

- **Intake** is a warm conversation, not a form. The assistant asks one thing at a
  time, offers tap-able quick replies, answers common questions with Approved answers,
  notices distress and responds gently, and recognises crisis language and steps aside
  for crisis resources. Behind the conversation the server keeps a checklist, so every
  required Assessment item is captured and nothing is skipped or invented.
- **Identity** lets the Client photograph their ID instead of typing. Fields read with
  confidence are pre-filled; anything uncertain is left blank; the Client confirms
  every value before it is saved. The image is never stored. Typing is always an
  equal alternative.
- **Scheduling** shows open Slots matched to the Client's stated format and
  availability, books one with an instant confirmation and calendar file, and never
  lets two Clients take the same Slot.
- **Supportive content** appears at the three moments people tend to give up — a long
  pause, an upload problem, high stress — and at no other time. Crisis resources are
  always one tap away on every screen.
- **Privacy is part of the experience:** two plain-language consents, a "Withdraw and
  delete everything" action with a receipt, no identity details ever sent to the AI,
  and nothing personal in logs.
- **Clinicians** see only the Assessments of Clients booked with them, and every view
  is logged. **Operators** see an observability dashboard — performance, AI health,
  AI quality — with no individual's data.

Target outcomes (client PRD, illustrative): completion ~50% → ~70%; time to complete
≤ 15 minutes; NPS 70+ (aspirational); < 3 s p95 response under the stated load.

---

## User Stories

### Getting started

1. As a Client, I want to create an Account with just an email and password, so that I can start without waiting for a verification email.
2. As a Client, I want to sign back in and land on the Step I left, so that I never redo work.
3. As a Client, I want to see all four Steps and where I am on a progress bar, so that I know how much is left.
4. As a Client, I want a short "what to expect" line on each Step, so that I'm not uncertain about what's coming.
5. As a Client, I want a crisis resources link (988 and emergency services) visible on every screen, so that help is always one tap away.
6. As a Client, I want my progress saved automatically after every answer, so that closing the tab costs me nothing.
7. As a Client, I want to use the whole flow on my phone, so that I can finish wherever I am.

### Consent

8. As a Client, I want to be told plainly what is collected, why, and how long it is kept before I agree, so that I can make an informed choice.
9. As a Client, I want Onboarding consent and ID scan consent asked separately, so that I can agree to one without the other.
10. As a Client, I want to decline the ID scan and still finish Onboarding by typing my details, so that I'm never forced to share an image of my ID.
11. As a Client, I want to confirm I'm 18 or older at the start, so that I'm not halfway through a conversation before learning the Service is for adults.
12. As a Client, I want to change my mind about ID scan consent later, so that I can choose the faster path once I trust the process.
13. As the Service, I want every consent granted or withdrawn recorded with its consent version and time, so that I can prove what each Client agreed to.

### Intake conversation

14. As a Client, I want the assistant to ask me one thing at a time, so that I don't feel overwhelmed.
15. As a Client, I want quick-reply buttons for common answers, so that I can tap instead of type.
16. As a Client, I want to type freely whenever the buttons don't fit, so that I can say it my way.
17. As a Client, I want the assistant to understand an answer that covers several questions at once ("anxiety, for about three months"), so that I'm not asked things I already said.
18. As a Client, I want to answer "prefer not to say" to sensitive questions where allowed, so that I keep control over what I share.
19. As a Client, I want to rate how I'm feeling right now on a simple 1–5 scale, so that the Service understands my urgency without a clinical questionnaire.
20. As a Client, I want to state my Clinician preferences (e.g. gender, language), so that my first consultation feels safe.
21. As a Client, I want to choose video or in-person sessions, so that the format suits my life.
22. As a Client, I want to say which times of day I'm available, so that the Slots I'm offered actually work for me.
23. As a Client, I want to ask questions mid-conversation (cost, privacy, who sees my answers), so that my worries are addressed before I continue.
24. As a Client, I want answers to my questions to be accurate and consistent, so that I can trust what I'm told.
25. As a Client, I want the assistant to say honestly when it doesn't know something and tell me how to reach a person, so that I'm not misled.
26. As a Client, I want to ask for a real person and get contact options, so that I can talk to a human if I prefer.
27. As a Client, I want to ask about changing an appointment and be pointed to where I can do it, so that I'm not given promises the assistant can't keep.
28. As a Client, I want the assistant to bring me back gently when I go off-topic, so that I still finish.
29. As a Client, I want the assistant never to diagnose me or comment on medication, so that I'm not given clinical judgements by a machine.
30. As a Client, I want the assistant never to promise times, prices or outcomes, so that nothing it says turns out false.
31. As a Client, I want to be asked directly and kindly whether I'm having thoughts of harming myself or others, so that I'm offered the right help.
32. As a Client, I want the conversation to resume exactly where I left it after a break, so that I don't repeat myself.
33. As a Client, I want my Intake conversation deleted once my Assessment is complete, so that only what's needed is kept.

### Distress, crisis and support

34. As a Client who says I'm overwhelmed, I want a short, kind acknowledgement and an offer to slow down, so that I feel heard and keep going.
35. As a Client in crisis, I want the onboarding to stop pushing questions and show me crisis resources immediately, so that my safety comes first.
36. As a Client who used a figure of speech ("this form is killing me"), I want to be gently asked what I meant rather than shown a crisis screen, so that I'm treated sensibly.
37. As a Client who answers "No, just stressed" to a Safety check-in, I want to carry on with a supportive message, so that I'm not stuck.
38. As a Client in a Crisis pause, I want to be able to come back later and resume, so that I can finish onboarding when I'm ready.
39. As a Client who has gone quiet for a while, I want a reassuring note that my progress is saved and what comes next, so that I don't give up.
40. As a Client, I want supportive messages to appear only when something has actually happened, so that I'm not nagged.
41. As a Client, I want to dismiss a supportive message, so that it doesn't get in my way.
42. As a Client, I want the same supportive message not to keep reappearing on a Step, so that it stays helpful rather than annoying.

### When the AI is unavailable

43. As a Client, I want to keep going with simple scripted questions if the assistant has a problem, so that a technical issue doesn't end my onboarding.
44. As a Client, I want to be told plainly when the assistant is having trouble, with an option to try it again, so that I understand what's happening.
45. As a Client, I want the crisis check, the Safety question, Approved answers and supportive messages to keep working without the assistant, so that safety never depends on the AI.
46. As the Service, I want malformed or unsafe AI output never shown or saved, so that a bad response cannot reach a Client or the record.

### Identity

47. As a Client on a phone, I want to take a photo of my ID with my phone's camera, so that I don't have to type my details.
48. As a Client on a computer, I want to upload a photo file instead, so that the scan also works on desktop.
49. As a Client, I want brief guidance on taking a good photo, so that it works first time.
50. As a Client, I want my photo's hidden metadata (including location) removed before upload, so that I share no more than needed.
51. As a Client, I want fields read from my ID shown to me pre-filled, so that I only need to check them.
52. As a Client, I want each field clearly marked as "read from your ID — please check" or "couldn't read — please type", in words and icons and not by colour alone, so that I know exactly what to review.
53. As a Client, I want fields the system wasn't sure about left blank rather than guessed, so that wrong details never slip through.
54. As a Client, I want to edit any pre-filled value, so that I can fix misreads.
55. As a Client, I want nothing saved until I press "These details are correct", so that only details I've confirmed are stored.
56. As a Client whose photo can't be read, I want a reassuring message and a one-tap switch to typing, so that a bad photo never blocks me.
57. As a Client who uploads the wrong kind of file or one that's too large, I want a clear message saying what's accepted, so that I can fix it quickly.
58. As a Client, I want my ID image never stored anywhere, so that I'm not exposed if the system is ever breached.
59. As a Client under 18, I want a respectful explanation that the Service is for adults, together with support resources, so that I'm not simply turned away.

### Scheduling

60. As a Client, I want to see open Slots that match my preferred format and times of day, so that I only see options I can take.
61. As a Client, I want to show all times if none of the matched Slots suit me, so that I'm never stuck with no options.
62. As a Client, I want each Slot shown in my local time with the time zone labelled, so that I don't book the wrong hour.
63. As a Client, I want to book an Initial consultation in one action and see an instant confirmation, so that I know it's done.
64. As a Client, I want to download a calendar file for my Booking, so that it's in my calendar.
65. As a Client, I want to be told immediately if someone took my Slot a moment before me, with the nearest alternatives, so that I can rebook in one tap.
66. As a Client, I want my Booking still there when I sign in later or on another device, so that I can trust it.
67. As a Client, I want to reschedule by choosing a new Slot, with my old Slot released, so that changing plans is easy.
68. As the Service, I want no Slot ever to hold two active Bookings, even under simultaneous requests, so that Clinicians are never double-booked.
69. As the Service, I want Bookings limited to the next 14 days with at least 2 hours' notice, so that every Booking is realistic.

### Withdrawal and data rights

70. As a Client, I want to withdraw consent and delete everything at any time, so that I stay in control of my data.
71. As a Client, I want to see exactly what will be deleted and confirm before it happens, so that I don't delete by accident.
72. As a Client, I want a deletion receipt with a time and reference, so that I have proof it happened.
73. As a Client who withdraws, I want my Assessment, Identity details, conversation, progress, Booking and Account all removed, so that nothing about me remains.
74. As a Client who withdraws, I want my Booking's Slot released for others, so that my withdrawal doesn't waste a Clinician's time.
75. As a Client, I want to say "delete my data" in the chat and be taken to the withdrawal screen, so that I don't need to hunt for it.
76. As the Service, I want the assistant never able to delete anything itself, so that deletion only ever happens through an explicit, confirmed action.
77. As the Service, I want a permanent, identity-free Consent log entry for every Withdrawal, so that I can prove the request was honoured.
78. As an auditor, I want every data endpoint to return "not found" for a withdrawn Client, so that the deletion is verifiable.

### Clinician view

79. As a Clinician, I want to sign in and see my upcoming Initial consultations, so that I can prepare.
80. As a Clinician, I want to read each booked Client's Assessment and first name, so that I understand why they're coming.
81. As a Clinician, I want to be unable to see Clients booked with other Clinicians, so that confidentiality is respected.
82. As a Clinician, I want Identity details (date of birth, address) withheld from my preparation view, so that I see only what I need.
83. As the Service, I want every time a Clinician opens a Client's record written to the Access log, so that staff access is accountable.

### Operator dashboard

84. As an Operator, I want to see p50/p95 response times for chat, OCR and booking against their targets, so that I know whether we meet our benchmarks.
85. As an Operator, I want to see AI call volumes, error types, fallback-to-scripted rate and output-check trips, so that I can spot AI problems quickly.
86. As an Operator, I want to see the latest eval scorecard (OCR accuracy per field, pass/fail per intent), so that I know the AI's quality.
87. As an Operator, I want every figure to be aggregate and identity-free, with small counts suppressed, so that monitoring never exposes an individual.
88. As an Operator, I want (if built) to see drop-off and median time per Step and OCR correction rates, so that I can find where onboarding loses people.
89. As a Client, I want my onboarding never visible to Operators as an individual journey, so that monitoring doesn't intrude on my privacy.

### Privacy, security and trust

90. As a Client, I want my name, date of birth, address, the reason I gave and my Safety answer encrypted in storage, so that even a database leak doesn't expose them.
91. As a Client, I want phone numbers, emails, dates and street addresses I type masked before any text reaches the AI provider, so that my details stay in-house.
92. As a Client, I want my Identity details never sent to the AI at all, so that the most sensitive data never leaves the Service.
93. As the Service, I want no personal details, ID images or conversation text ever written to logs, error traces or analytics, so that operational data is safe to handle.
94. As the Service, I want only my own API able to read or write data, with the browser limited to signing in, so that there's one guarded path to the data.
95. As the Service, I want every request checked for ownership, so that a Client can only reach their own record.
96. As the Service, I want the service-specific content (procedure, questions, answers, support copy, crisis resources) held in one Service profile, so that the assistant can be re-targeted to another Service by swapping it.

### Accessibility

97. As a keyboard-only Client, I want to complete every Step without a mouse, with a visible focus outline, so that the flow works for me.
98. As a screen-reader Client, I want every field labelled and new chat messages and supportive messages announced, so that I can follow along.
99. As a Client with low vision, I want sufficient contrast and status that never relies on colour alone, so that I can read everything.
100. As a Client, I want no time limits on any Step and motion that respects my reduce-motion setting, so that I can go at my own pace comfortably.

### Grader and operations

101. As a grader, I want to run the app, seed data, tests and evals from a clean checkout in minutes with only Docker and the Supabase CLI, so that I can assess the work quickly.
102. As a grader without an AI key, I want the app to run with a built-in fake provider and a one-line switch to a free model, so that I can see both the safe fallback and the real experience.
103. As a grader, I want demo Client, Clinician and Operator logins, so that I can see every role.
104. As a grader, I want one command that prints the OCR and intent scorecards, so that I can verify the AI quality thresholds.
105. As a grader, I want committed load-test scripts and recorded results, so that I can verify the performance benchmarks.
106. As an operator of the deployment, I want a health check that reports the database, OCR and AI provider, so that I can tell what's broken.
107. As an operator of the deployment, I want the database kept awake on the free plan by the health check, so that the demo stays up during review.
108. As a developer, I want every request to produce one identity-free timing record, so that I can explain any slow response.

---

## Implementation Decisions

### Shape and stack

- **Service and domain:** outpatient mental-health counseling intake. HIPAA is the
  regime the documentation addresses; the build is *HIPAA-ready, not HIPAA-compliant*
  (synthetic data only; production needs a Supabase BAA and equivalent agreements with
  the LLM provider).
- **Stack:** Python FastAPI backend; React + Vite + TypeScript frontend, built and
  served by the same container ([ADR 0001](adr/0001-fastapi-react-not-rails.md)).
- **Data and auth:** Supabase (Free plan, US East) for both sign-in and Postgres.
  Supabase's Data API is disabled; the browser uses Supabase only to sign in. The API
  is the only path to data, and it enforces ownership on every request. Every table
  has row-level security enabled with no browser-facing policies, so the browser cannot
  reach tables even with its public key. We do **not** claim per-request RLS as a
  second authorization layer.
- **Hosting:** Railway, US East, one always-on container (FastAPI + built React +
  Tesseract), connecting to Supabase via its IPv4 connection pooler. Deployed with the
  Railway CLI (Railway's push-to-deploy integration is GitHub-only; the repository is
  on GitLab).
- **No LangChain or LangSmith** ([ADR 0002](adr/0002-no-langchain-langsmith.md)):
  official provider SDKs with typed, validated structured output; observability comes
  from our own timing records and dashboard.
- **Sign-in:** email + password, email confirmation off for the demo (the free plan's
  built-in email is heavily rate-limited). Magic links and email confirmation are the
  documented production upgrade.

### Modules

Deep modules (small interface, substantial behaviour, tested through the interface):

1. **Onboarding engine** — `state(client)`, `apply(client, action) → new state or
   rejection`. Owns Step order, each Step's required items, gating (no Scheduling
   before Identity is confirmed), Crisis pause and resume, and what "complete" means.
   Pure logic over stored state.
2. **Safety screen** — `screen(message) → clear | check-in | crisis`. Two tiers of
   phrases from the Service profile: unambiguous self-harm language → crisis;
   ambiguous idioms ("killing me", "can't go on") → Safety check-in. Runs before any
   LLM call and works with no LLM.
3. **Intake conductor** — `respond(intake, message) → reply + updated Assessment +
   signals` (intent, distress, crisis, fallback used). Pipeline per message: Safety
   screen → masking → **exactly one structured LLM call** returning intent, extracted
   Assessment values, an Approved-answer id (or none) and a short reply → validation of
   every extracted value → output check → reply. The server-held checklist, not the
   LLM, decides the next missing item and when Intake is complete. Counts consecutive
   LLM failures and switches to scripted mode after two.
4. **LLM port** — `complete(conversation, output schema, timeout) → validated result or
   LLM failure`. Three adapters: Anthropic; OpenAI-compatible (OpenRouter by default, or
   local Ollama via a base URL); Fake (scripted results, configurable delay and
   failures). Selected by configuration. 5-second timeout, no retry inside a request.
   Invalid output is a failure.
5. **Document reader** — `read_identity(image bytes) → for each of name, DOB, address:
   value or blank, with confidence; plus a failure reason`. Hides upload validation
   (type detected by content, ≤ 8 MB, must decode; JPEG/PNG/HEIC), EXIF orientation,
   OpenCV straightening and contrast, Tesseract, field parsing, and the rule that a
   field is filled only if it parses validly *and* its confidence clears the threshold
   (≈ 70) — never guessed. OCR engine is a seam with Tesseract and Fake adapters. The
   image lives only in memory for the duration of the request.
6. **Scheduling** — `open_slots(client, filters)`, `book(client, slot) → Booking or
   "slot taken" with nearest alternatives`, `current_booking(client)`,
   `calendar_file(booking)`. One active Booking per Client; reschedule frees the old
   Slot in the same transaction; a database constraint guarantees at most one active
   Booking per Slot; 14-day window, 2-hour minimum notice; stored in UTC, shown in the
   Client's local zone.
7. **Support triggers** — `decide(events, already shown) → content id or none`. Pure
   function. Triggers: long pause (45 s with no interaction on an incomplete Step),
   upload problem (rejected upload or no usable OCR fields), high stress
   (express-distress intent, self-rated distress 4–5, or "No" to a Safety check-in).
   One card at a time, dismissible, non-blocking, once per Trigger per Step. A Crisis
   pause overrides any card; the persistent crisis link is not Supportive content.
8. **Consent & Withdrawal** — `grant(client, consent, version)`, `withdraw(client) →
   deletion receipt`. Two consents (Onboarding — required; ID scan — optional). The
   Consent screen also captures the 18+ confirmation. Withdrawal deletes the
   Assessment, Intake conversation, Identity details, progress and Booking (freeing
   the Slot), deletes the Account through the auth admin seam (Supabase and Fake
   adapters), deletes that Account's rows from Supabase's auth audit log if they
   persist (to be verified during the tracer bullet), unlinks the Journey if analytics
   exist, and writes the identity-free Consent log entry.
9. **Access control** — `who(request) → Client | Clinician | Operator`,
   `clinician_view(clinician, booking)`. Verifies the Supabase login token (token
   verifier seam with Supabase and test adapters), resolves the role, enforces
   ownership and Clinician scope, and writes the Access log on every Clinician record
   view.
10. **Telemetry recorder** — `timed(stage)`, `record(outcome)`. One identity-free record
    per request: request id, endpoint, stage timings (LLM, database, OCR, total),
    outcome, intent label, provider and model. No Account id, no text. Also exposed as
    a response timing header for the benchmark scripts. Writes `llm_error` records
    with provider, error type and latency only.
11. **Dashboard queries** — `dashboard(window) → panels`. Layer 1 (must): Performance,
    LLM health, AI quality. Layer 2 (if time): Onboarding funnel and OCR corrections,
    built on Journey records. Counts under 5 are suppressed.
12. **Service profile** — one validated, typed object loaded at startup: Steps and
    required items; each Assessment item's scripted question, answer type and whether
    it is declinable; intent examples; 15–20 Approved answers; Supportive content
    copy; the two crisis phrase tiers; crisis resources and contact details. A broken
    profile stops the app at startup.

Deliberately shallow layers:

- **HTTP API** — translates requests into module calls; includes the health check,
  which reports database, OCR and LLM reachability and writes a heartbeat row so the
  Supabase Free plan does not pause.
- **Encrypted text field** — a column type that encrypts on write and decrypts on read
  with an app-held key (Fernet). Applied to Identity details, the Assessment's
  free-text reason and the Safety answer. Structured Assessment fields stay plain.
- **Migrations and seed** — schema, RLS enablement, 3–4 fictional Clinicians, Slots for
  the next 14 days, demo Client / Clinician / Operator Accounts.

Frontend:

- **Stepper shell** (progress, persistent crisis link, focus management on Step change),
  **Consent**, **Intake chat** (quick replies, live region for new messages),
  **Identity capture + review**, **Scheduling**, **Withdrawal**, **Clinician view**,
  **Dashboard**, **Support card**, and an **idle detector** that reports events to the
  server.
- **Image preparer** — `prepare(file) → resized JPEG`: long edge ≈ 2000 px, quality ≈
  85%, orientation applied, then all metadata (including GPS) stripped. Capture uses
  the phone's native camera via the file input's capture attribute; a file picker on
  desktop.

Tooling:

- **Golden-set generator** — seeded synthetic ID cards from a fictional issuer ("State
  of Riverside"): 30 golden (10 clean, 10 phone-photo, 10 hard: skew, glare on a field,
  two-line address, unusual names, a cut-off field) plus ~10 **held-out** cards in a
  different layout and fonts that are never tuned against. Labels generated alongside.
- **Eval harness** — one command runs the OCR sets through the Document reader and the
  intent set through the Intake conductor, prints the scorecard and writes a dated
  report including raw model output for failed cases.
- **Load and timing scripts** — k6 scenario and 20-run OCR and booking timing scripts.

### Assessment contract

Required items: reason for seeking help (category + free text), how long it has been
going on, self-rated distress (1–5), Clinician preferences (e.g. gender, language),
session format (video / in person), availability (mornings / afternoons / evenings), and
the Safety question. Items the profile marks declinable accept "prefer not to say". No
diagnosis, no scored screeners (PHQ-9 / GAD-7 are a documented production addition).

### Intent contract (the eval list)

| Intent | Handling |
|---|---|
| provide-details | Fill Assessment item(s); ask the next missing one |
| ask-question | Show an Approved answer verbatim, or "I don't have that answer" + contact route; return to the checklist |
| request-reschedule | Acknowledge and point to Scheduling; never book or promise |
| express-distress | High-stress Trigger + gentler reply; continue |
| crisis-risk | Crisis pause |
| request-human | Show contact options |
| withdraw-consent | Route to the Withdrawal screen; never delete |
| out-of-scope | Gentle redirect to Intake |

Crisis detection is the union of the Safety screen, the LLM's crisis label and the
Safety question. Output check (on every LLM reply, before display): blocks commitments
(specific dates/times, prices, "confirmed", "you will be seen"), clinical language
(diagnoses, medication) and Identity-detail-like strings, using narrow patterns with a
table of benign sentences that must pass. A tripped reply is replaced by a safe line
plus the next scripted question.

### Data handling

- **What reaches the LLM:** the Client's typed chat text with phone numbers, emails,
  dates and street addresses masked. Never Identity details, never images. Known
  limit: names in free text and the Assessment's free-text reason are not reliably
  masked.
- **Retention:** ID images never stored. Intake conversation kept only while Intake is
  in progress, deleted on completion. Withdrawal deletes everything listed above.
  Consent log and Access log are identity-light and permanent.
- **Analytics (Layer 2):** funnel events keyed by a random Journey id with an
  Account→Journey link deleted at Withdrawal; events hold only Step, event, time and
  outcome. Crisis pauses are recorded only as a daily count with no Journey link.
- **Logs:** structured JSON, identity-free; a development-only switch (refused outside
  development) writes full prompts to a git-ignored local file for synthetic-data
  debugging.

### Configuration

All configuration comes from the environment, documented in the committed example
environment file: LLM provider, model, keys, base URL and timeout; Supabase URL, keys
and pooler connection string; field encryption key (with a key-generation command);
application environment. The example file defaults the LLM provider to Fake, so the app
runs with no key.

### Delivery

- **Build method:** tracer bullet first — Sign in → Consent → one scripted Intake
  question → manual Identity → book a seeded Slot → Done, deployed to Railway, with
  timing records — then vertical slices that each thicken one path end to end.
- **Two-day plan:** Day 1 AM tracer bullet; Day 1 PM LLM Intake + intent eval; Day 2 AM
  OCR + supportive content; Day 2 PM Withdrawal, Clinician view, dashboard Layer 1,
  k6, documentation, demo video.
- **Cut order if behind:** sentiment-adaptive tone (stretch #6) → Playwright test →
  dashboard Layer 2 → field encryption. Anything cut is listed in the README as
  planned and not delivered.
- **CI:** GitLab CI configuration committed from the start but dormant until the user
  registers their own runner and enables it (the instance has no shared runners): lint
  → test with coverage gate → build → deploy. A pre-push hook running lint and tests is
  committed but switched on later by the user.
- **Grader quick-start:** Docker + Supabase CLI only; make targets for setup, seed, run,
  test, eval, load and deploy, mirrored as shell scripts.

---

## Testing Decisions

**What makes a good test here:** it exercises a module only through its interface and
asserts on externally visible behaviour — what a caller or Client would observe — never
on internal calls or private state. Swappable dependencies are replaced at their seams
by Fake adapters (LLM, OCR engine, auth admin, token verifier), not by patching
internals. Each PRD acceptance criterion and each edge case maps to at least one named
test.

**Coverage bar:** ≥ 80% on core logic (Document reader, Intake conductor, Scheduling,
plus the other deep modules), enforced in CI.

**Every module is tested; the level differs:**

| Level | Modules / areas |
|---|---|
| Through the interface | Onboarding engine, Safety screen, Intake conductor, LLM port (each adapter against faked HTTP), Document reader, Scheduling, Support triggers, Consent & Withdrawal, Access control, Telemetry recorder, Dashboard queries, Service profile (broken profile fails at startup), Encrypted text field |
| Integration (real HTTP, real local Supabase) | API end to end, RLS blocks browser access, concurrent double-booking (two simultaneous requests → exactly one wins), Withdrawal → every endpoint "not found" + audit-log rows gone, health check |
| AI evals with thresholds | Document reader on the golden set (≥ 90% field-level) and the held-out set (reported separately); Intake conductor on the intent set (every intent passes; unambiguous crisis → pause, ambiguous → check-in, plain stress → neither; out-of-scope → no commitment) |
| Frontend component + accessibility | Every Step screen with Testing Library and axe (zero violations), image preparer, idle detector, review-screen status text |
| Smoke | Golden-set generator, load and timing scripts |

**Named behaviours that must have tests** (non-exhaustive): LLM timeout and 5xx → Intake
still completes with a full Assessment; invalid LLM output never shown or saved; output
check trips on commitments and passes the benign table; partial OCR → read fields
pre-filled, missing fields blank, nothing fabricated; non-image / oversized / corrupt
upload rejected with a message; no personal data in captured log output across a full
scripted onboarding; encrypted fields unreadable in the raw database row; Clinician
cannot read another Clinician's Client; every Clinician view writes an Access log entry;
Support triggers table (each Trigger → its content; no Trigger → none; once per Step);
Scheduling rejects outside the window and under 2 hours' notice; reschedule frees the old
Slot.

**Prior art:** none — new repository. Conventions to establish: pytest with FastAPI's
test client and respx for faked provider HTTP; Vitest + React Testing Library +
vitest-axe on the frontend; the eval harness writes committed, dated reports so run-to-run
changes show in diffs.

**Benchmarks (recorded, not unit tests):** k6 realistic journey at 20 VUs for 60 s
against the real Anthropic model (needs a higher Anthropic rate tier) and a repeatable
run against the Fake provider (~800 ms simulated latency); OCR and booking timed over
20 runs each from the response timing header. Targets: chat/API < 3.0 s p95, OCR
< 8.0 s p95, booking < 1.0 s p95; results committed with date, model and hardware.

---

## Out of Scope

- Multiple Services or tenants (one Service, with a swappable Service profile).
- Clinical assessment: diagnosis, scored screeners (PHQ-9, GAD-7), medication.
- Therapist matching beyond filtering Slots by format and availability.
- Live human handoff or live chat with staff (contact options only).
- Email or SMS (booking confirmations, magic links, email verification).
- Payments, insurance verification, PCI scope.
- Minors or guardian consent (adults only).
- In-page camera with card overlay, auto-capture, desktop-to-phone QR handoff.
- RAG or document retrieval (Approved answers only).
- Admin console, Clinician or Slot management UI, staff editing of records.
- Multi-language (stretch #5).
- LangChain, LangSmith or any third-party tracing.
- GitHub, GitHub Actions or Railway's GitHub integration.
- Real ID documents or any real personal data anywhere in the repository.
- Formal HIPAA compliance (BAA, risk assessment, policies) — documented as the
  production path.

## Further Notes

- **Stretch #6 (sentiment-adaptive tone)** — built 2026-10-17 as "gentle mode" (see README); originally planned only after the core and edge cases
  are done: a high-stress signal switches replies to a "gentle" mode (shorter, more
  acknowledgement, one question at a time), shows quick replies on every question and
  offers to pause; tested deterministically.
- **Dashboard Layer 2** (funnel, OCR corrections) is a tracked item: if not built, the
  README lists it as planned with the Journey design as the path.
- **Open verification items for the tracer bullet:** what Supabase's auth audit log
  keeps after a user is deleted; that the Railway CLI upload excludes the local
  environment file; the Anthropic account's rate tier for the k6 run.
- **README must also cover:** stack justification; exactly what reaches the LLM and the
  masking limits; OpenRouter free models are for synthetic data only and the benchmarks
  ran on Anthropic; retention policy; Supabase Free-plan pausing and the heartbeat;
  the GitLab/Railway deployment limitation; model, OCR engine and hardware versions; the
  production upgrade list (magic links, email, in-page capture, RAG, screeners, admin
  console, multi-language, LangSmith with masking); how to re-target the assistant with
  a different Service profile.
- **Documentation set** (written at the end, from the built system): README and
  AI_USAGE at the root; USERS, ARCHITECTURE (high- and low-level design with sequence
  diagrams), DEPLOY, TEST_PLAN, RUNBOOK, DECISIONS, PERFORMANCE, ACCESSIBILITY, AGENTS
  (if subagents build slices), AI_LOG and ISSUE_LOG in the docs folder; ADRs in the ADR
  folder.
