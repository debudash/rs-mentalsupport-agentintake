# The server owns the intake; the LLM gets one narrow call per message

Intake looks like a free conversation, but the procedure is a server-held checklist of
required Assessment items: the server decides what is missing, what to ask next and when
Intake is complete. Each Client message makes exactly one structured LLM call that returns
intent, extracted answers, an approved-answer id and a one-line acknowledgement; the server
validates every value against the service profile and shows approved answers word for
word. We chose this over an agent loop or free generation because a mental-health intake
must be complete, consistent and safe (no invented costs, promises or diagnoses), must
keep working when the LLM is down, and must answer within 3 s at p95 — several LLM calls
per message would not.

## Considered options

- **Agent loop with tools**: flexible, but non-deterministic completion and more latency.
- **LLM writes answers to questions (RAG or free generation)**: warmer, but can drift into
  wrong costs or promises; mental-health platforms in production (Wysa, Limbic) constrain
  replies the same way.
- **Several specialised calls per message** (classify, extract, pick, phrase): clearer
  prompts, but 3–4× the latency.

## Consequences

The Fake adapter and scripted mode can run the whole Intake without a model. Prompt
changes are limited to interpretation and tone; adding a question is a profile edit.
