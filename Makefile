# rs-assist — grader quick-start. Needs only Docker (and npx for the Supabase CLI).
# The same commands exist as scripts/*.sh for shells without make.

COMPOSE := docker compose
DEV := $(COMPOSE) run --rm dev

.PHONY: help setup seed up down test test-backend test-frontend eval eval-record load \
        load-real timings lint ci hooks deploy golden-set

help:
	@echo "make setup        .env + encryption key + local Supabase (first run downloads images)"
	@echo "make seed         migrations + clinicians, slots and demo accounts"
	@echo "make up           run the app on http://localhost:8000"
	@echo "make test         backend (pytest, coverage gate) + frontend (vitest + axe)"
	@echo "make eval         OCR + intent scorecards (LLM_PROVIDER from .env)"
	@echo "make load         k6, 20 VUs for 60 s against the running app"
	@echo "make timings      20-run OCR and booking timings"
	@echo "make deploy       railway up"

setup:
	bash scripts/setup.sh

seed:
	$(DEV) -m alembic upgrade head
	$(DEV) -m app.seed

up:
	$(COMPOSE) up --build app

down:
	$(COMPOSE) down

test: test-backend test-frontend

test-backend:
	$(COMPOSE) run --rm -e DATABASE_URL=sqlite:// -e OCR_ENGINE=fake -e LLM_PROVIDER=fake \
		--entrypoint /app/backend/.venv/bin/pytest dev --cov --cov-report=term --cov-fail-under=80

test-frontend:
	docker run --rm -v "$(CURDIR)/frontend:/app" -w /app node:22-slim \
		sh -c "npm ci --no-audit --no-fund && npm run lint && npx tsc -b && npm test"

eval:
	$(DEV) ../evals/run.py all

eval-record:
	$(DEV) ../evals/run.py all --record

golden-set:
	$(DEV) ../tools/golden_set/generate.py

load:
	docker run --rm -i --add-host host.docker.internal:host-gateway \
		-e BASE_URL=http://host.docker.internal:8000 \
		-e SUPABASE_URL=http://host.docker.internal:54321 \
		--env-file .env -v "$(CURDIR)/k6:/k6" grafana/k6 run /k6/journey.js

timings:
	$(DEV) ../k6/timings.py

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run lint && npx tsc -b

# What CI and the pre-push hook run (local toolchain: uv + npm).
ci: lint
	cd backend && uv run pytest --cov --cov-fail-under=80 -q
	cd frontend && npm test

hooks:
	git config core.hooksPath .githooks
	@echo "pre-push hook enabled (disable: git config --unset core.hooksPath)"

deploy:
	railway up --detach
