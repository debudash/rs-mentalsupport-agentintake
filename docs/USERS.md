# Users

## Client — the person signing up

An adult reaching out to a counseling service, often anxious, tired or overwhelmed at the
moment they sign up, frequently on a phone. They want to finish quickly with as little
typing as possible, to understand what happens next, and to feel safe sharing.

What the product does for them:
- **Fewer things to decide or type:** one question at a time, tap-to-answer buttons, an ID
  photo instead of typing their details.
- **Always knowing where they are:** a four-step progress bar with a one-line "what to
  expect" for each Step; progress saved at every answer.
- **Support at hard moments:** reassurance after a long pause, after a failed photo, or when
  they say they're struggling — and only then.
- **Safety first:** crisis resources on every screen; crisis language stops the sign-up and
  shows help instead.
- **Control:** separate consents, honest answers about who sees what, and "withdraw and
  delete everything" at any time.

Stories: [PRD § User Stories](PRD.md#user-stories) 1–78, 90–100.

## Clinician — a counselor at the Service

Prepares for Initial consultations. Needs to know why each booked Client is coming,
without seeing more personal data than that.

- Sees only Clients booked with them; their Assessment and first name; never date of
  birth or address.
- Every time they open a Client's answers, it's recorded in the Access log.

Stories: PRD 79–83.

## Operator — someone at the Service monitoring onboarding

Wants to know whether onboarding is fast and the AI is healthy, without looking at any
individual.

- Dashboard: response times against targets, LLM failures and fallbacks, unsafe replies
  replaced, latest eval scorecards, crisis pauses and withdrawals — aggregate only, small
  counts shown as "<5".

Stories: PRD 84–89.

## Grader — the reviewer of this submission

Wants to run everything from a clean checkout in minutes and check every claim.

- `make setup && make seed && make up`, demo logins for every role, `make test`,
  `make eval`, `make smoke`, `make load`. See the [README](../README.md).

Stories: PRD 101–108.
