# Project Brief — AI-Powered Onboarding Assistant

- **Client:** Riverside Partners LLC (The Riverside Company, Operating Team)
- **Sponsor:** Director, AI Acceleration
- **Technical contact:** Melissa Hargis
- **Tier:** Silver · Version 1 · Category: AI solution
- **Time constraint:** 2–3 days
- **Last updated:** 2026-10-12
- **Full spec:** [PRD.md](client-prd.md)

## Summary

Build an AI-powered onboarding assistant for users registering for specialized,
potentially sensitive services. It must reduce friction from complex data entry and
emotional stress via an LLM chatbot for guided assessment, an image-to-text step for
document data extraction, an appointment scheduler, and supportive content surfaced at
high-abandonment moments.

## Business context

Specialized-service onboarding suffers high abandonment due to long forms, manual
document transcription, and uncertainty about next steps, compounded by user anxiety.
Reducing drop-off directly improves conversion and lowers customer acquisition cost,
while a guided, low-typing, supportive flow is a differentiator in a trust-sensitive
domain.

## Impact metrics

- Onboarding completion rate: ~50% baseline → ~70% (+20 pts, ~40% relative)
- Completion time: ≤ 15 min (from 25–30 min baseline)
- NPS 70+ for the onboarding experience (aspirational)
- < 3 s p95 system response time under stated load

## Functional requirements

**Core**
1. LLM assessment chatbot that handles all defined intents and produces structured
   assessment records, with graceful fallback for unrecognized input.
2. Image-to-text data entry extracting name, DOB and address at ≥ 90% field-level
   accuracy, with user confirmation before saving.
3. Appointment scheduling: view slots, book, confirm, reject double-booking, persist
   across sessions.
4. Supportive content surfaced at defined triggers (long pause, upload failure,
   high-stress intent) and never shown otherwise.

**Edge cases (must handle):** OCR failure → manual entry; partial extraction confirmed
without fabrication; consent revocation and verifiable data deletion; rejection of
malformed / oversized / non-image uploads; PII never logged; graceful LLM timeout /
failure handling.

**Stretch:** multi-language support, sentiment-adaptive tone, advanced analytics
dashboard.

## Performance benchmarks

- Chatbot / API response < 3.0 s p95 under 20 VUs for 60 s (k6)
- OCR extraction latency < 8.0 s p95 (20 runs)
- Scheduling / booking action < 1.0 s p95 (20 runs)
- Deployed demo uptime ≥ 99% over the evaluation window

## Code quality expectations

Test coverage ≥ 80% on core logic (OCR extraction, chatbot orchestration, scheduling
state); graceful degradation for all external dependency failures with no unhandled
500s; structured PII-free logging and a health-check endpoint; committed DB migrations
and seed script / fixtures; no secrets in repo, with `.env.example`; input validation on
uploads; baseline accessibility (keyboard nav, labeled controls, color contrast); CI
running tests and linter (RuboCop / ESLint) on every push.

## Technology

- **Languages:** candidate's choice (justify in README).
- **LLM:** Claude (Anthropic API) suggested; Groq free tier, Gemini free tier, Ollama
  (local) or OpenAI acceptable substitutes.
- **OCR:** Tesseract or PaddleOCR (free, self-hostable); cloud OCR optional.
- **Dev tools:** Git, Docker, RSpec (or Jest for frontend).
- **Hosting:** candidate's choice; no paid API required.
- **Other required:** Supabase Auth for per-user authN/authZ; k6 for load testing;
  committed seed script / fixtures including a synthetic OCR golden set; `.env.example`.

## Off-limits

No paid API required. Raw ID images must not be sent to third-party cloud AI services
without disclosure and justification. Prefer local / self-hosted OCR and free-tier /
self-hosted LLMs to keep PII on-infrastructure.

## Deliverables

- Technical documentation
- Demo video
- AI usage documentation (optional per brief; **required** per PRD as `AI_USAGE.md`)
