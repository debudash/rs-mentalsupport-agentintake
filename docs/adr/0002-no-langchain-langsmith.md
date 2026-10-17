# No LangChain or LangSmith

The author's default demo stack uses LangChain and LangSmith, but this project uses thin
adapters over the official `anthropic` and `openai` SDKs with Pydantic for structured
output, and its own eval harness and metrics. The LLM's role here is a few narrow calls
inside a server-owned checklist (classify intent, extract Assessment values, pick an
Approved answer, phrase a short reply), not an agent loop, so LangChain adds more to
explain than it saves. LangSmith tracing would send mental-health chat text to a third
service, conflicting with the PRD's data boundary, and would make graders need an
account. Its useful parts are replaced cheaply: PII-free per-request timing records, a
dev-only local prompt log, committed eval reports, and an in-app metrics dashboard.

## Consequences

LangSmith can be added later as an optional, off-by-default upgrade for development with
synthetic data and masking; the README mentions it as such.
