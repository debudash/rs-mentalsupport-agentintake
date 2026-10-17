# Impact: what this build does for the client's metrics

The brief's business case: *completion sits near 50%, onboarding takes 25–30 minutes, and
the Service cannot see where or why people drop off.* Targets: completion ~70%, ≤ 15
minutes, NPS 70+ (aspirational), < 3 s p95.

Without real Clients, some of this can be measured, some simulated, and some only argued.
Each claim below carries one label:

| Label | Meaning |
|---|---|
| **Measured** | The real system, real data (tests, evals, load test) |
| **Simulated** | The real system — real API, Claude, Tesseract, database, timestamps — driven by synthetic people whose *pacing* is modelled |
| **Estimated** | A model only, no system run |
| **Not shown** | Needs real people; we say what would prove it |

Source data: [evals/reports/2026-10-17-cohort.json](../evals/reports/2026-10-17-cohort.json)
(30 simulated Clients) and [2026-10-17-cohort-dashboard.json](../evals/reports/2026-10-17-cohort-dashboard.json)
(what the dashboard reported for that window). Re-run: `make cohort`.

## Summary

| Client metric | Baseline (brief) | This build | Label |
|---|---|---|---|
| See **where** people drop off | Cannot | Funnel per Step: reached, drop-off, median time | **Measured** — verified exact against a scripted cohort |
| See **why** | Cannot | Friction per Step: pauses, failed photos, stress, assistant fallbacks; ID-field corrections | **Measured** — verified exact |
| Time to complete | 25–30 min | **2.8 min median, 3.9 min p90** at modelled human pace; under 15 min even if real people are 3.8× slower (p90) or 5× slower (median) | **Simulated** |
| Typing | Re-type everything, incl. the ID | **0 characters** for the median Client vs 150 on a typed form | **Simulated** |
| Completion rate | ~50% | Every abandonment cause in the brief has a counter-measure; measured in production by the funnel | **Not shown** — needs an A/B test (~91 people per arm) |
| NPS | — | Asked once after booking; panel computes NPS | Mechanism **measured**; the score itself **not shown** |
| Response time | — | Chat p95 2.28 s at 20 users on real Claude Haiku | **Measured** |

## 1. "The Service cannot see where or why people drop off" — Measured

The dashboard now shows, per Step, how many Clients reached it, the drop-off from the
Step before, the median time it took, and the friction signals recorded there. To check
the instruments rather than assume them, 30 simulated Clients ran with **scripted**
behaviour, and the dashboard was compared with the script (raw counts for this synthetic
data; the live dashboard shows counts under 5 as "<5"):

| Scripted | Expected | Dashboard / events |
|---|---|---|
| 30 sign up | 30 | **30** ✓ |
| 2 hesitate and leave at Consent | 28 consented; 2 Consent pauses | **28**; **2** ✓ |
| 1 stalls mid-Intake | 27 finished Intake; 1 Intake pause | **27**; **1** ✓ |
| 2 have no ID to hand | 25 confirmed identity; 2 Identity pauses | **25**; **2** ✓ |
| 4 upload a wrong file first | 4 rejected uploads; 4 "photo couldn't be read" cards | **4**; **4** ✓ |
| 6 say they're struggling | 6 high-stress signals | **6** ✓ |
| 25 book | 25 booked | **25** ✓ |

Running this check found a real gap — hesitation on the Consent Step couldn't be recorded,
because the Client record only exists after consent — now fixed
([ISSUE-008](ISSUE_LOG.md)).

The ID reader's real-world error rate is visible too: for every scanned ID, whether each
field was pre-filled, left blank, or corrected by the Client. (In this run all 20 scans
read correctly, so corrections were 0%; the offline eval is 98.9% on the golden set.)

## 2. Time to complete (target ≤ 15 min) — Simulated

**How people were paced.** Keystroke-Level Model (KLM) operator times, a standard HCI
method for predicting task time, plus reading speed. All constants live in
[tools/simulate/cohort.py](../tools/simulate/cohort.py):

| Action | Time |
|---|---|
| Read | 230 words/min |
| Type | 0.30 s per character (~40 wpm) |
| Decide (KLM M) + reach (P) + tap (B) | 1.35 + 1.10 + 0.20 s |
| Fetch the ID card / take the photo | 15 s / 20 s |
| Check one pre-filled field | 2.5 s |
| A stressed Client's break | 60 s |

**Results (25 completers, real Claude Haiku and Tesseract):**

| | Median | p90 |
|---|---|---|
| All completers | **2.8 min** | **3.9 min** |
| Calm, ID photo | 2.4 min | |
| Calm, types everything (no ID scan) | 2.9 min | |
| First photo rejected, then succeeds | 2.8 min | |
| Stressed (gentle mode, takes a 60 s break) | 3.9 min | |

| Step | Median |
|---|---|
| Consent | 0.5 min |
| About you (Intake) | 0.9 min |
| Your details | 0.7 min |
| Book | 0.3 min |

**What the model leaves out.** KLM describes skilled, error-free work. Real people
re-read, hesitate, make mistakes and, in this domain, are often anxious, so real times
will be longer. How much longer can only be measured. The margin is wide:

| If real people are… | Median | p90 | Under 15 min? |
|---|---|---|---|
| as modelled | 2.8 min | 3.9 min | ✓ |
| 2× slower | 5.6 min | 7.8 min | ✓ |
| 3× slower | 8.4 min | 11.7 min | ✓ |
| 5× slower | 14.0 min | 19.5 min | median ✓, p90 ✗ |

**Compared with a typed form — honestly.** Under the same model, the *same information*
typed into a conventional form (consent, nine answers, name/DOB/address transcribed from
the card) estimates at **2.4 min** — about the same as this flow. Reading the
conversational prompts costs roughly what the buttons and the ID photo save in typing.
So the raw-keystroke time is a wash. The time advantage over the brief's 25–30 minutes
comes from three things the model can't see:

1. **Asking only what's needed** — 9 intake items + 3 identity fields, versus the long,
   document-heavy forms the brief describes (we don't know their exact content, so this
   is argued, not measured);
2. **No transcription** — **0 characters typed** for the median Client versus **150** on
   the typed form, so no transcription errors to find and fix later;
3. **The real causes of slowness the brief names** — uncertainty about next steps
   (progress bar, one line per Step), stress (supportive content, gentle mode, breaks).

**Not shown:** real completion times. They appear on the dashboard (median minutes per
Step) from the first real Client; compare against the current form's analytics.

## 3. Completion 50% → 70% — Not shown (and how it would be)

A completion rate can't be simulated honestly: any number would just restate the persona
mix we chose. (The cohort's 25/30 is the 5 drop-outs we scripted, not a prediction.)

What *can* be shown is that each cause of abandonment the brief names has a
counter-measure, and that each is instrumented:

| Cause (from the brief) | Counter-measure | Watched by |
|---|---|---|
| Long forms | 12 items; tap-to-answer; the assistant extracts several answers from one sentence | Median time per Step |
| Manual document transcription | ID photo → pre-filled, confirmed fields; typing always an equal option | OCR-corrections panel; typed characters |
| Uncertainty about next steps | Progress bar, "what to expect" per Step, progress saved | Drop-off per Step |
| Stress / anxiety | Supportive content at three trigger moments; gentle mode; crisis resources everywhere | Friction by Step; high-stress signals |
| Failure dead-ends | OCR failure → typing; assistant down → simple questions | Upload and fallback signals |

**How to prove it:** an A/B test against the current form, with completion = booked an
Initial consultation. To detect 50% → 70% at 80% power and α = 0.05 (two-sided,
two-proportion test) needs **~91 people per arm**:
n = (1.96 + 0.84)² × (0.5·0.5 + 0.7·0.3) / 0.2² ≈ 90.2. The funnel panel provides the
outcome; Journeys are anonymous, so the test needs no personal data.

## 4. NPS 70+ (aspirational) — mechanism measured, score not shown

One question after booking: *"How likely are you to recommend signing up with us to
someone who needs similar support?"* (0–10, skippable, asked once). The dashboard reports
promoters (9–10), passives (7–8), detractors (0–6) and NPS.

The cohort's scores were **assigned** (16 × 9, 5 × 8, 4 × 7) purely to check the
calculation: the dashboard reported **+64** (64% promoters, 36% passives, 0%
detractors), which is exactly right for those inputs. **It is not a result.**

**How to prove it:** real answers. For an NPS within about ±10 points (95%), plan on
~200 responses.

## 5. Response time < 3 s p95 — Measured

k6, 20 virtual users for 60 s, against real Claude Haiku 5.5: **chat p95 2.28 s**, all API
p95 1.91 s, 0% failed, 0 LLM errors in 290 messages. Details:
[PERFORMANCE.md](PERFORMANCE.md).

## What would change these conclusions

- Real Clients much slower than 3.8× the model would push the p90 past 15 minutes; the
  first weeks of real data on the dashboard answer this.
- If the current form already asks only what this flow asks, the 25–30 → < 15 minute gain
  would rest on stress and uncertainty, not length; the form's content would settle it.
- The completion uplift is a hypothesis until the A/B test runs.
