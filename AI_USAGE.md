# AI usage disclosure

## AI tools used to build this

| Tool | Used for |
|---|---|
| **Claude Code** (Anthropic, model Claude Opus 5.5) | Design interview and PRD, all code (backend, frontend, tests, eval harness, generator, scripts), debugging, documentation. The author directed and reviewed the work; decisions and their reasons are in [docs/DECISIONS.md](docs/DECISIONS.md) and the [ADRs](docs/adr/). A summary of what the agent did, per phase, is in [docs/AI_LOG.md](docs/AI_LOG.md). |

No other AI tools generated code or content. Everything was built in one Claude Code
session; no sub-agents built separate parts.

## AI inside the product

| Component | Engine | Version / model | Where it runs | What it receives |
|---|---|---|---|---|
| Intake chat (intent, answer extraction, approved-answer choice, one-line acknowledgement) | Anthropic Claude via the official `anthropic` SDK | `LLM_MODEL`, default `claude-opus-5-5`, effort `low`; `claude-haiku-5-5` for the lowest latency | Anthropic API | The Client's typed chat text, **masked** (phones, emails, dates, street addresses → placeholders), the last 6 masked turns, and the list of intake items and approved-answer questions |
| Same, free alternative | OpenRouter (OpenAI-compatible API, `openai` SDK) | e.g. `meta-llama/llama-3.3-70b-instruct:free` | OpenRouter's providers | Same as above. Free providers may log prompts: **synthetic data only** |
| Same, fully local | Ollama (OpenAI-compatible) | any local model | the operator's machine | Same as above; nothing leaves the machine |
| Same, keyless default | Fake adapter (keyword heuristic, not a model) | — | in process | — |
| ID reading | Tesseract OCR + OpenCV preprocessing | Tesseract 5.5.0 (Debian package in the image), OpenCV 5.0 | in the app container | The ID image, in memory only |
| Sentiment / stress (gentle mode) | No separate model. High stress = the `express-distress` intent (from the same single LLM call), a self-rated distress of 4–5, or "No" to the Safety check-in. It then adds one line to the system prompt ("the client is finding this hard … one short, warm sentence") | — | — | — |

**Never sent to any LLM:** name, date of birth or address from the ID; the ID image; quick-reply
button answers (handled without the LLM); anything a Clinician or Operator sees.

## Prompts and configuration that shape behaviour

- **System prompt** (built in `backend/app/domain/intake.py`, `_system_prompt`): the
  assistant classifies the latest message into one of 8 intents, extracts answers for
  the listed intake items with their allowed values, picks an approved-answer id or
  `none`, and writes one short acknowledgement. Rules stated in the prompt: never ask a
  question (the server asks the next one), never diagnose or mention medication, never
  promise times, dates, prices or outcomes, never repeat personal details.
- **Structured output:** a JSON schema with `intent` (enum of 8), `answers` (item enum +
  string value), `approved_answer_id` (enum of approved ids + `none`) and `reply`. Passed
  as `output_config.format` (Anthropic) or `response_format: json_schema` (OpenAI-compatible).
- **Server-side guards around the model:**
  - the Safety screen runs **before** the model, from the phrase lists in the service profile
  - every extracted value is validated against the profile; anything invalid makes the whole turn a failure
  - the output check filters the reply
  - approved answers are shown word for word, never generated
- **Timeout** 5 s, no retries inside a request; two consecutive failures switch Intake to
  scripted questions.
- **OCR:** field confidence threshold 70 (`OCR_CONFIDENCE_THRESHOLD`); fields below it
  are left blank for the Client.

## Evaluation of the AI

`make eval` — see the README's AI evaluation section and [evals/reports](evals/reports).
The synthetic ID set and the labelled intent set are committed in [evals/datasets](evals/datasets).
