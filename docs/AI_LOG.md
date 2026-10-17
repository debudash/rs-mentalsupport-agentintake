# AI log

What the AI agent (Claude Code, Claude Opus 5.5) did while building this, phase by phase,
and what a human decided. Tools and models used inside the product are in
[AI_USAGE.md](../AI_USAGE.md).

## 2026-10-16 — Design (human-led interview)

- **Agent:** connected the GitLab repository; cleaned the client brief and PRD into
  `docs/source/`; ran a one-question-at-a-time design interview (35 decisions) with a
  recommendation per question; researched industry practice when asked (Limbic, Wysa,
  Woebot, BetterHelp/Talkspace, Intercom Fin; Supabase pricing and audit logs); kept the
  glossary and ADRs current; self-critiqued the plan ("roast") and proposed scope cuts.
- **Human decided:** the service (counseling), stack (FastAPI + React, not Rails), Supabase
  in US East, Railway, Anthropic + OpenRouter via env, no LangSmith but an observability
  dashboard, Clinician view kept, GitLab-only CI kept dormant, docs at the end, and to build
  in one shot without review gates.
- **Output:** [PRD.md](PRD.md), [DECISIONS.md](DECISIONS.md), ADRs 0001–0002,
  [GLOSSARY.md](GLOSSARY.md), and a reusable `/write-prd` skill.

## 2026-10-17 — Build (agent-led, one session, no sub-agents)

| Commit | What the agent did | Verified by |
|---|---|---|
| `3688210` | Backend: 12 deep modules, API, migrations with RLS, seed | 183 tests, 94% coverage, ruff |
| `a2d5e89` | Synthetic ID generator (golden + held-out), eval harness, Dockerfile. Diagnosed the held-out failure on **separate dev cards**, not the held-out set, and added a label-free fallback that never guesses | OCR eval: golden 98.9%, held-out 93.3%, 0 fabricated |
| `441bb50` | React frontend: all Steps, clinician view, dashboard | 47 tests incl. axe and WCAG contrast |
| `671e7d1` | Local Supabase, setup/seed/up targets, Docker host alias, dual JWT verification, smoke test | 21/21 smoke checks on the real stack; public key can't read tables |
| `9cadd97` | **ISSUE-001** found by inspecting Supabase audit rows after Withdrawal: email/IP survived. Failing test first, then fix | `pytest -m postgres`; 0 rows left |
| `7281952` | **ISSUE-002** found by k6: keep-alive race dropped 0.2% of requests | k6 rerun: 0% failed |
| `23c89a5` | k6 journey and 20-run timings | chat p95 1.15 s, OCR 1.18 s, booking 85 ms |
| `00f4a69` | GitLab CI (dormant), pre-push hook (inactive) | `make ci` green locally |
| `3de810b` | **ISSUE-003** found by walking the UI in headless Chromium: Intake crashed on current Chromium | Failing test first; browser walk clean |
| `dc681d9` | Scheduling day picker (Book button was below 60 slots) | Screenshot review |
| `3751993` | Booked demo client for the clinician view; screenshots | Clinician + dashboard walk, no errors |
| (docs) | README, AI_USAGE, architecture with sequence diagrams, decisions, ADRs 0003–0004, test plan, performance, accessibility (keyboard-only walk: 16/16), deploy, runbook, users, issue log | Every number taken from a real run |

## 2026-10-17 — Dashboard layer 2 (human chose it as the next part)

- Journeys module, migration 0003 (RLS on both tables), funnel and OCR-correction queries,
  dashboard panels; review screen sends which fields the scan pre-filled.
- Tests first (11 new backend tests); 197 backend + 50 frontend pass. Verified on the real
  stack with 25 journeys (20-run timings + 5 browser walks): funnel and per-field panels
  render; withdrawn journeys remain as unlinked counts.

## 2026-10-17 — Real-model evaluation (human added the Anthropic key)

- Intent eval on Opus 5.5 and Haiku 5.5, three runs each; Haiku 100% with p95 ~2 s, Opus
  98–100% with p95 ~3 s. **Human decided:** Haiku for the demo, Opus kept as the documented
  default, both reports kept for discussion.
- k6 against real Haiku at 20 users × 60 s: chat p95 2.28 s, 0% failed, 0 LLM errors.

## 2026-10-17 — Privacy lines, CI on, real-Claude fixes

- **Human decided:** short per-Step privacy lines plus a footer (option A), kept subtle;
  no "HIPAA compliant" claim (agent advised it would be untrue and risky).
- Agent pushed to GitLab, created a project runner via the API, ran GitLab Runner in Docker,
  set `CI_ENABLED`; fixed two CI setup errors (image tag, dind TLS); pipeline green.
- Walking the UI on real Claude found ISSUE-004/005/006 (invalid value failed the turn,
  scripted matching, an outcome promise passing the output check); fixed test-first.

## 2026-10-17 — Stretch #6: sentiment-adaptive tone

- Gentle mode built test-first (11 tests): switched on by any high-stress signal, persisted
  per Client (migration 0004), shorter prompt-shaped replies trimmed to one sentence, a
  "Take a break" offer on every question; crisis handling unchanged.
- First version repeated "we can go slowly" three times (card, an extra chat line, Claude's
  reply) and mixed "Take a break" into the answers; the agent removed the extra line and
  moved the break to a quiet link after reviewing the screenshot against the user's
  "subtle, not distracting" brief. Verified on real Claude: 7/7 gentle checks, full and
  keyboard walks unchanged (17/17).

## 2026-10-17 — Self-review fixes

- Agent rated the build against the client rubric (~84/100 before deploy and video) and
  found the README claimed double-booking was "tested concurrently" when tests were
  sequential. Added a real race test (20 simultaneous bookings on Postgres, exactly one
  wins), proved it fails with the unique index dropped, and added a Postgres service job
  to CI; migrations made to run on plain Postgres (role-conditional revoke).
- README and `.env.example` now state that the chat benchmark requires Haiku.

## 2026-10-17 — Business metrics: measurable, simulated, or stated

- **Human asked** where the brief's business case (50% completion, 25–30 min, no visibility
  of drop-off) was evidenced; agent confirmed it wasn't, and on the human's direction built
  a post-booking NPS question, per-Step friction signals, and a synthetic cohort.
- 30 simulated Clients on the real system (Claude Haiku, Tesseract), paced by KLM: median
  2.8 min to complete; dashboard matched the scripted cohort exactly. First run silently
  missed NPS/friction (container predated the code; simulator didn't check responses) —
  agent made the simulator strict, rebuilt, re-ran; found and fixed ISSUE-008.
- Reported honestly that a typed form of the same information estimates at 2.4 min (no raw
  time win); the gain is in typing (0 vs 150 chars), scope and stress. docs/IMPACT.md.

## Not done by the agent (needs the human)

- **Deployment:** Railway is logged in but no project is linked, and the hosted Supabase
  keys and pooler URL weren't available. Steps in [DEPLOY.md](DEPLOY.md).
- **Enabling the pre-push hook (`make hooks`) and the demo video.** (Pushed and CI on: done.)

## 2026-10-17 — Banner from the design system cover

- The plain top bar became the Riverside Counseling cover (`1be7014`), then was fitted to
  the page column with the 988 line right under the blocks (`87fc5f5`). The user reported
  the signed-in band cropping the blocks from a screenshot: ISSUE-009 (`68ddbac`), fixed
  test-first.
- Design review afterwards: all browser walks re-run on the new banner (full journey,
  keyboard 17/17, gentle 7/7, staff, panels); no horizontal scroll at 320/375 px; the 988
  line now sits on the page background, so that colour pair joined the contrast test.
  Screenshots refreshed (sign-up screenshot added to show the full banner); stale test
  counts in the README and accessibility doc corrected.

## 2026-10-17 — Judgment and evidence pass (human-supplied "stand out" guide)

- **Human asked** how the build stacks against a guide for standing out (degradation model,
  honest evals, privacy artifacts, reviewer experience, configurable template). Agent rated
  each item against the repo; the human chose the documentation items plus fault injection,
  and held back the self-checking receipt and a second Service profile.
- Fault injection built test-first (10 tests): `FAULT_INJECT=llm_timeout|llm_down|ocr_fail|db_slow`
  wraps each dependency at its seam, refused in production, listed in `/health`. Live drill
  with `llm_down,ocr_fail`: only the targeted smoke check failed; onboarding completed.
- New docs: RELIABILITY (failure matrix, drills, service levels + error budgets),
  THREAT_MODEL, PII-boundary diagram, OCR miss categories (incl. the one wrong pre-fill the
  rule didn't stop), README rubric map, `make demo`, CI eval gates.
- Agent re-verified a claim before citing it: "public key can't read tables" had been a
  manual check, not a smoke test; re-checked live (42501 on four tables) and cited as such.
- CI paused at the human's request (`CI_ENABLED=false`) to speed up iteration.

## 2026-10-17 — OCR stress set: realistic bad captures

- **Human asked** for more realistic scans that are hard to read. Agent added a third set of
  20 synthetic captures (motion blur, low light, card far away, laminate glare, the phone's
  shadow, security print, a thumb over the address, a bent card, a photocopy, a worst case),
  on its own seed so the existing 40 cards stayed byte-identical; reviewed a contact sheet
  and fixed one mislabelled card (the thumb missed the address it was labelled as covering).
- Eval now splits misses into "left blank" (safe) and "wrong value pre-filled" (unsafe).
  Stress: 43.3%; 31 of 34 misses left blank; 3 unsafe (a label read as a name, a misread
  house number, a truncated ZIP). Not tuned against; reported separately, not gated.
