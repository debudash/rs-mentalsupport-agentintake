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

## Not done by the agent (needs the human)

- **Real-model intent eval:** no Anthropic key on the build machine; the committed intent
  scorecard is the keyless Fake heuristic. Run `make eval` with `LLM_PROVIDER=anthropic`.
- **Deployment:** Railway is logged in but no project is linked, and the hosted Supabase
  keys and pooler URL weren't available. Steps in [DEPLOY.md](DEPLOY.md).
- **Push to GitLab, enabling CI and the hook, the demo video.**
