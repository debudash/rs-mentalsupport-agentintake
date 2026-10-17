# FastAPI + React instead of Rails

The PRD's examples (RSpec, RuboCop, `rake ai:eval`) hint at Rails, but it explicitly
leaves the stack to the candidate. We chose a Python FastAPI backend with a React (Vite,
TypeScript) frontend: Python has the strongest OCR and image-preprocessing tooling
(Tesseract bindings, OpenCV) for the core AI logic, explicit FastAPI code is easier to
explain under review than Rails conventions the author is new to, and React gives full
control over accessibility, Supabase sign-in and client-side pause detection.

## Considered Options

- **Rails 8 + Hotwire**: matches the PRD's wording and is one codebase, but weaker image
  preprocessing in Ruby, no official Supabase SDK, awkward on Windows, and a steep
  convention learning curve inside a 2–3 day timebox.
- **FastAPI + Jinja/htmx**: one Python codebase and simplest to explain, but a thinner
  frontend for the demo and little for ESLint to cover.

## Consequences

Two codebases and two test runners in CI. Tool equivalents: pytest (RSpec), ruff
(RuboCop), Vitest + React Testing Library (Jest), ESLint as named. The 80% coverage bar
applies to the Python core.
