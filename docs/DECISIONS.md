# Decisions

Every significant call made while designing and building, and why. Hard-to-reverse,
surprising ones have a full ADR.

## Architecture decision records

| # | Decision |
|---|---|
| [0001](adr/0001-fastapi-react-not-rails.md) | FastAPI + React instead of Rails |
| [0002](adr/0002-no-langchain-langsmith.md) | No LangChain or LangSmith; own eval harness and dashboard |
| [0003](adr/0003-server-owned-checklist-one-llm-call.md) | Server-owned checklist; one structured LLM call per message |
| [0004](adr/0004-id-images-never-stored.md) | ID images never stored; sensitive fields encrypted in the app |

## Product and domain

| Decision | Why |
|---|---|
| Service: outpatient mental-health counseling intake | Makes supportive content central; HIPAA is the obvious regime to address |
| One Service, everything service-specific in one profile file | No multi-service engine (not asked for); re-targeting is a file swap — the reuse story |
| Stepper: Consent → Intake → Identity → Scheduling | A visible progress bar answers "uncertainty about next steps"; structured steps for paperwork, conversation where empathy matters (as Limbic and consumer platforms do) |
| Assessment is non-clinical: 8 items + one direct Safety question | No diagnosis or scored screeners (PHQ-9/GAD-7 are a production addition) |
| 8 intents (PRD's 5 + crisis-risk, request-human, withdraw-consent) | Crisis must be distinct from distress in mental health |
| Two-tier crisis check: unambiguous → pause; ambiguous idioms → check-in question | "This form is killing me" must not trigger a crisis screen, and must not be ignored |
| Answers to questions come from ~16 approved texts, shown word for word | No invented costs or promises; deterministic to evaluate |
| Output check on every LLM reply | Blocks times, prices, "confirmed", diagnoses, medication, identity-like strings |
| Supportive content: 3 triggers only (45 s pause, upload problem, high stress), once per Step | The PRD's "never shown otherwise" must be literally true |
| Two consents (onboarding required, ID scan optional) + "I'm 18 or older" on Consent | Minimisation; a minor learns it's adults-only before the sensitive conversation |
| Withdrawal deletes everything incl. the Account; keeps an identity-free consent-log entry | "Delete everything" is what someone leaving a mental-health service expects; the log proves it |
| Intake conversation deleted when Intake completes | Only the Assessment is needed |
| Initial consultation, 30 min, 3–4 fictional clinicians, 14-day window, 2 h notice | The real next step after intake; enough slots for demos |
| Clinician view: own bookings only, no DOB/address, every view in an Access log | Shows role-scoped, audited staff access |
| Operator dashboard, layer 1 (performance, AI health, AI quality) | Replaces LangSmith observability; layer 2 (funnel) designed, not built |
| Stretch #6 (sentiment-adaptive tone) and #5 (multi-language) not built | Timebox; core and edge cases first |

## Technical

| Decision | Why |
|---|---|
| Supabase (Auth + Postgres, Free plan, US East) | Auth required by the PRD; encryption at rest; one system for identity and data |
| Supabase Data API off; RLS on with no browser policies; API is the only data path | One guarded path; browser's public key reads nothing (verified) |
| Railway, one container, US East; deploy with the Railway CLI | User's platform; GitHub integration not available (GitLab only) |
| Connect via Supabase pooler (IPv4) | Supabase's direct connection is IPv6-only |
| `/health` writes a heartbeat row | Keeps the Free plan from pausing; uptime evidence |
| LLM port with Anthropic, OpenAI-compatible (OpenRouter/Ollama) and Fake adapters | "No paid API required" satisfied; graders can run keyless or fully local |
| Tesseract 5 + OpenCV, not PaddleOCR | Lighter image, faster; met 98.9% on the golden set |
| Label-free OCR fallback only when exactly one line has the field's shape | Robust to lost labels without guessing |
| Synthetic IDs from a fictional issuer; held-out layout never tuned against | No real PII; an honest generalisation number |
| Browser resizes photos to 2000 px and strips metadata | Faster uploads; GPS never leaves the device |
| Email + password sign-in, confirmation off for the demo | Supabase Free email is rate-limited; magic links are the production path |
| k6 against the Fake LLM with 800 ms simulated latency, plus real-model runs when a key is present | Repeatable and keyless; isolates our system's overhead |
| CI on GitLab, dormant until a project runner is registered; pre-push hook inactive until `make hooks` | Instance has no shared runners; user enables when ready |
| No sub-agents built separate slices (so no AGENTS.md) | One session built everything sequentially |
| Tracer bullet → vertical slices | Riskiest parts (OCR, LLM latency) learned early |
