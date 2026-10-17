# rs-assist: one image — FastAPI API + built React app + Tesseract.
# Targets: runtime (default, deployed), dev (tests, evals, golden-set generation).

# ---- frontend build ---------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- shared base: Python + Tesseract ----------------------------------------------------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
WORKDIR /app/backend

# ---- dev: tests, evals, generator (fonts for synthetic IDs) -----------------------------
FROM base AS dev
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen
COPY backend/ ./
ENV PATH="/app/backend/.venv/bin:$PATH"

# ---- runtime ----------------------------------------------------------------------------
FROM base AS runtime
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV PATH="/app/backend/.venv/bin:$PATH" FRONTEND_DIST=/app/frontend/dist APP_ENV=production
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --no-access-log"]
