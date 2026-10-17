# Deploy (Railway + hosted Supabase)

The deployed app is the same Docker image as local (`runtime` target): FastAPI serving
the built React app, with Tesseract. Supabase (US East) provides Auth and Postgres.

> Railway's push-to-deploy integration supports GitHub only. This repository lives on
> Gauntlet's GitLab, so deploys go through the **Railway CLI** — by hand (`make deploy`)
> or from the GitLab CI `deploy:railway` job once CI is enabled.

## 1. Supabase project (once)

Already created: US East (`us-east-1`), Data API **off**, auto-expose **off**, automatic
RLS **on**.

1. **Auth → Providers → Email:** turn **off** "Confirm email" for the demo (the Free plan's
   built-in email is heavily rate-limited; see Production upgrades in the README).
2. **Project Settings → API keys:** copy the **anon / publishable** key and the
   **service_role / secret** key.
3. **Connect → Connection string → Session pooler** (IPv4): copy it and change the scheme
   to `postgresql+psycopg://`. Do **not** use the direct connection (IPv6-only).
4. **JWT:** new projects sign tokens with asymmetric keys, verified through JWKS — leave
   `SUPABASE_JWT_SECRET` empty. Only projects on the legacy shared secret need it set.

## 2. Railway service (once)

```bash
railway login                      # already done on this machine
railway init                       # or: railway link, to an existing project
```

In the Railway dashboard for the service:

- **Region:** US East (Virginia), next to Supabase.
- **Serverless / app sleeping:** **off** (uptime ≥ 99%).
- **Variables** (Raw editor), from `.env.example`:

```
APP_ENV=production
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-us-east-1.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>
SUPABASE_JWT_SECRET=
LLM_PROVIDER=anthropic
LLM_MODEL=claude-opus-5-5
LLM_EFFORT=low
LLM_TIMEOUT_SECONDS=5
ANTHROPIC_API_KEY=<key>
OCR_ENGINE=tesseract
FIELD_ENCRYPTION_KEY=<new key — do not reuse the local one>
```

Generate the encryption key with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Losing it makes stored identity details unreadable; keep it in a password manager.

## 3. Deploy

```bash
make deploy          # = railway up --detach  (builds the Dockerfile on Railway)
```

The container runs `alembic upgrade head` on start, then serves on `$PORT`. Railway honours
`.gitignore`/`.dockerignore`, so the local `.env` is not uploaded — check the build log's
file list on the first deploy.

Seed the hosted database once (clinicians, slots, demo accounts), from your machine:

```bash
DATABASE_URL=<pooler url> SUPABASE_URL=https://<ref>.supabase.co \
SUPABASE_SERVICE_ROLE_KEY=<key> FIELD_ENCRYPTION_KEY=<the Railway key> \
  docker compose run --rm -e DOCKER_HOST_ALIAS= dev -m app.seed
```

Re-run the seed weekly (or on a Railway cron) to keep two weeks of open slots.

## 4. Verify

```bash
BASE_URL=https://<app>.up.railway.app make smoke   # 21 end-to-end checks
make eval-record                                   # scorecards onto the dashboard (point DATABASE_URL at the hosted DB)
```

Then `make timings` against the deployed URL and, if the Anthropic tier allows ~200
requests/min, `make load` with `BASE_URL` set — record results in
[PERFORMANCE.md](PERFORMANCE.md).

## 5. Uptime and keep-alive

Create a free UptimeRobot HTTP monitor on `https://<app>/api/health` every 5 minutes. Each
call writes a heartbeat row, which keeps the Supabase Free project from pausing after 7 idle
days, and the monitor's history is the uptime evidence for the review window.

## 6. Enable CI (when the build is stable)

1. Install GitLab Runner in Docker Desktop and register a **project runner** for
   `debudash/rs-assist` with the tag `rs-assist-local` and the Docker executor
   (privileged, for the image build job).
2. GitLab → Settings → CI/CD → Variables: `CI_ENABLED=true`, and a masked `RAILWAY_TOKEN`
   (Railway → project → Settings → Tokens).
3. Push: lint → test → build → deploy runs on the default branch.
4. Optional local guard: `make hooks` turns on the pre-push hook.
