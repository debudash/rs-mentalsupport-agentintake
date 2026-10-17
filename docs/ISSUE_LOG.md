# Issue log

Every bug found during the build: what, why, the fix, and the regression test.
Each fix site carries a comment with the issue id.

| ID | Found by | Issue | Root cause | Fix | Regression test | Commit |
|---|---|---|---|---|---|---|
| ISSUE-001 | Inspecting Supabase's `auth.audit_log_entries` after a Withdrawal on the real local stack | Sign-up and deletion events, with the user's email and IP, survived "delete everything" while the receipt said they were gone | Deletion matched `payload.actor_id` only; GoTrue names the affected user in `payload.traits.user_id`, with the system as actor | Match `actor_id` **or** `traits.user_id`; runs after the auth user is deleted so the deletion event is caught too | `backend/tests/test_postgres_withdrawal.py` (`pytest -m postgres` with `TEST_POSTGRES_URL`) | `9cadd97` |
| ISSUE-002 | k6 load test (20 VUs, 60 s) | 1 in 500 requests failed before reaching the app | uvicorn's 5 s keep-alive vs. 2–5 s client pauses: a reused connection was being closed as a request was sent | `--timeout-keep-alive 75` | k6 threshold `http_req_failed < 1%`; rerun: 0% | `7281952` |
| ISSUE-003 | Walking the real UI in headless Chromium | Intake crashed into the error boundary right after consent | Expression-bodied effects returned the Promise that current Chromium's `scrollIntoView()`/`focus()` return; React called it as a cleanup | Block bodies for every effect | `frontend/src/test/effects.test.tsx` | `3de810b` |
