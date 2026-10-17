# Test plan

## What a good test is here

A test exercises a module through its interface and checks what a caller or a Client
would observe — never internal calls or private state. Dependencies that vary (LLM, OCR
engine, Supabase Auth admin, token verification) are swapped at their seams for Fake
adapters, not patched. Every acceptance criterion and edge case in the client PRD maps to
at least one named test below.

## Levels

| Level | Where | Runs |
|---|---|---|
| Module tests through interfaces | `backend/tests/test_domain_pure.py`, `test_intake.py`, `test_ocr.py`, `test_scheduling.py`, `test_adapters_and_dashboard.py` | `make test` (SQLite, Fake adapters) |
| API integration | `backend/tests/test_api_flow.py` (FastAPI TestClient, whole onboarding) | `make test` |
| Postgres integration | `backend/tests/test_postgres_withdrawal.py` | `pytest -m postgres` with `TEST_POSTGRES_URL` |
| Frontend components + accessibility | `frontend/src/test/*.test.tsx` (Testing Library + axe), `contrast.test.ts` (WCAG ratios) | `make test` |
| AI evals | `evals/run.py` over `evals/datasets` | `make eval` |
| End-to-end on the running stack | `scripts/smoke_test.py` (21 checks, real Supabase Auth, Tesseract) | `make smoke` |
| Performance | `k6/journey.js`, `k6/timings.py` | `make load`, `make timings` |

Coverage: backend **93%** (gate 80% on core logic, enforced in CI); frontend ~79% lines.

## PRD acceptance criteria → tests

| Requirement | Tests |
|---|---|
| Chatbot handles every intent; structured record from a scripted conversation; graceful fallback | `test_intake.py::test_each_intent_has_its_handling`, `::test_scripted_conversation_produces_a_complete_assessment`, `::test_ask_question_shows_the_approved_answer_verbatim`; intent eval |
| OCR ≥ 90% on name/DOB/address; every field confirmed before saving | OCR eval (golden 98.9%); `test_api_flow.py::test_full_onboarding_end_to_end`; `steps.test.tsx` IdentityStep tests |
| View slots, book, confirm, reject double-booking, persists | `test_scheduling.py::test_book_then_double_booking_is_rejected_with_alternatives`, `::test_reschedule_frees_the_old_slot`; `test_api_flow.py::test_double_booking_via_api`, booking persists with a fresh token; smoke test |
| Supportive content at triggers, never otherwise | `test_domain_pure.py::test_each_trigger_maps_to_its_content_and_nothing_else`, `::test_trigger_shows_once_per_step`; `test_api_flow.py::test_idle_event_shows_long_pause_once`, `::test_high_stress_shows_support_card_once` |

## Edge cases → tests

| Edge case | Tests |
|---|---|
| OCR failure → manual entry | `test_ocr.py::test_engine_crash_degrades_to_manual_entry`, `::test_no_text_is_reported`; `test_api_flow.py::test_unreadable_photo_offers_manual_entry_support` |
| Partial extraction, no fabrication | `test_ocr.py::test_partial_card_leaves_missing_fields_blank`, `::test_low_confidence_fields_are_left_blank_not_guessed`, `::test_shape_fallback_never_guesses_when_ambiguous`; eval reports 0 fabricated fields |
| Consent revocation + verifiable deletion | `test_api_flow.py::test_withdrawal_deletes_everything_and_is_verifiable`; `test_postgres_withdrawal.py` (ISSUE-001); smoke test checks the Supabase user is gone |
| Malformed / oversized / non-image upload | `test_ocr.py::test_bad_uploads_are_rejected_with_a_reason`; `test_api_flow.py::test_bad_upload_is_rejected_with_message_and_support` |
| PII never in logs | `test_api_flow.py::test_no_personal_data_in_logs_or_timing_records`; `test_unexpected_error_is_friendly` |
| LLM timeout / failure | `test_intake.py::test_llm_failure_degrades_to_scripted_question`, `::test_two_failures_switch_to_scripted_mode_and_intake_still_completes`, `::test_invalid_llm_output_is_never_shown_or_saved`; adapter error mapping tests; `test_api_flow.py::test_llm_down_intake_still_completes` |

## Safety and security

| Concern | Tests |
|---|---|
| Crisis language pauses before any LLM call | `test_intake.py::test_unambiguous_crisis_language_pauses_without_calling_the_llm`; intent eval (100%) |
| Idioms get a check-in, not a crisis screen | `test_domain_pure.py::test_ambiguous_idioms_get_a_check_in`; `test_intake.py::test_ambiguous_idiom_gets_check_in_then_no_continues_with_support` |
| Output check blocks commitments, passes benign replies | `test_domain_pure.py` BENIGN / BLOCKED tables |
| Masking before the LLM | `test_intake.py::test_text_sent_to_llm_is_masked` |
| Encryption at rest | `test_api_flow.py::test_sensitive_fields_are_encrypted_at_rest` |
| Role scoping and Access log | `test_api_flow.py::test_clinician_sees_only_own_bookings_and_views_are_logged`, `::test_roles_are_enforced` |
| Tokens | `test_adapters_and_dashboard.py::test_verifier_accepts_valid_and_rejects_wrong_audience_or_secret`; expired/garbage tokens in `test_api_flow.py` |
| Browser cannot read tables | Verified against local Supabase REST with the public key (permission denied); RLS enabled by migrations 0001–0002 |

## Gentle mode (stretch #6)

| Concern | Tests |
|---|---|
| Each high-stress signal switches it on; calm conversations stay normal | `test_gentle.py::test_each_high_stress_signal_turns_gentle_mode_on`, `::test_calm_conversation_stays_normal` |
| No repeated reassurance in the chat; break offered on every question | same file |
| Prompt asks for one short sentence; reply trimmed to one sentence | `::test_gentle_mode_shapes_the_prompt_and_trims_the_reply` |
| Crisis handling unchanged; the break value is never an answer | `::test_gentle_mode_never_changes_safety`, `::test_break_value_is_never_stored_as_an_answer` |
| Persists across sessions | `::test_gentle_mode_persists_across_sessions`; `e2e/gentle.mjs` (7 checks on real Claude) |
| Break screen pauses without sending anything | `steps.test.tsx` "IntakeStep gentle mode" |

## Funnel analytics

| Concern | Tests |
|---|---|
| Events once per Journey, in funnel order, through the real API | `test_journeys.py::test_onboarding_and_withdrawal_produce_an_unlinkable_funnel` |
| Withdrawal unlinks; analytics tables never mention the Account or its data | same test; `::test_unlink_keeps_events_but_removes_the_way_back` |
| OCR review records booleans only | `::test_ocr_review_records_booleans_only` |
| Funnel maths, suppression, nothing derived from suppressed counts | `::test_funnel_counts_drop_off_and_median_minutes`, `::test_funnel_suppresses_small_counts_and_ignores_old_journeys`, `::test_ocr_corrections_per_field` |

## Accessibility

axe on every screen (`steps.test.tsx`, `screens.test.tsx`), WCAG AA contrast for every
colour pair (`contrast.test.ts`), labelled controls and linked errors (IdentityStep
tests), and a manual keyboard checklist in [ACCESSIBILITY.md](ACCESSIBILITY.md).
