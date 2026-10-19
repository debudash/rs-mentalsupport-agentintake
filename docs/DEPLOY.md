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
3. **Connect → Connection string → Session pooler** (IPv4): copy it, change the scheme to
   `postgresql+psycopg://` and the port from **5432 to 6543** — that is the **transaction
   pooler** on the same host. Do **not** use the direct connection (IPv6-only).
   Why 6543: the Free session pooler admits only 15 clients and pins a slot per open
   connection, idle or orphaned by a redeploy; under load the app was refused connections
   ([ISSUE-012](ISSUE_LOG.md)). The transaction pooler holds a slot only during a
   transaction; the app disables prepared statements, which it doesn't support.
4. **JWT:** new projects sign tokens with asymmetric keys, verified through JWKS — leave
   `SUPABASE_JWT_SECRET` empty. Only projects on the legacy shared secret need it set.

## 2. Railway service (once)

```bash
railway login
railway link --project rs-assist --environment production
railway add --service app          # first time only; the project's single service
```

Keep the hosted Supabase values in `.env.production` (git-ignored, from the template
there) and set variables from it with `railway variable set NAME --stdin --service app`, so
secrets never appear on a command line. New Supabase projects issue `sb_publishable_…` /
`sb_secret_…` keys; both work as-is (verified 2026-10-17).

In the Railway dashboard for the service:

- **Region:** US East (Virginia), next to Supabase. From the CLI:
  `railway scale --service app us-east=1 sfo=0` (name every other region with `=0`, by the
  id `railway status --json` shows, or a replica stays there).
- **Serverless / app sleeping:** **off** (uptime ≥ 99%).
- **Variables** (Raw editor), from `.env.example`:

```
APP_ENV=production
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@aws-0-us-east-1.pooler.supabase.com:6543/postgres
DB_POOL_SIZE=4                      # per worker; defaults fit either pooler
DB_MAX_OVERFLOW=1
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>
SUPABASE_JWT_SECRET=
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-5-5          # Opus misses the 3 s chat target (PERFORMANCE.md)
LLM_EFFORT=low
LLM_TIMEOUT_SECONDS=5
ANTHROPIC_API_KEY=<key>
OCR_ENGINE=tesseract
OCR_CONFIDENCE_THRESHOLD=70
UPLOAD_MAX_BYTES=8388608
FIELD_ENCRYPTION_KEY=<new key — do not reuse the local one>
```

Generate the encryption key with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
Losing it makes stored identity details unreadable; keep it in a password manager.

## 3. Deploy

```bash
railway up --service app --ci      # builds the Dockerfile on Railway, streams the build log
railway domain --service app       # first time: the public *.up.railway.app URL
```

The container runs `alembic upgrade head` on start, then serves on `$PORT`. Railway honours
`.gitignore`/`.dockerignore`, so the local `.env` is not uploaded — check the build log's
file list on the first deploy.

Seed the hosted database once (clinicians, slots, demo accounts), from your machine:

```bash
set -a && . ./.env.production && set +a     # incl. the FIELD_ENCRYPTION_KEY set on Railway
docker compose --profile tools run --rm -e DOCKER_HOST_ALIAS= -e APP_ENV=production \
  -e DATABASE_URL="${DATABASE_URL/postgresql:/postgresql+psycopg:}" -e SUPABASE_URL \
  -e SUPABASE_SERVICE_ROLE_KEY -e SUPABASE_ANON_KEY -e FIELD_ENCRYPTION_KEY dev -m app.seed
```

Re-run the seed weekly (or on a Railway cron) to keep two weeks of open slots.

## 4. Verify

With `.env.production` loaded (as above), from `backend/`:

```bash
uv run python ../scripts/smoke_test.py https://<app>.up.railway.app   # 21 end-to-end checks
uv run python ../k6/timings.py https://<app>.up.railway.app           # 20-run OCR + booking
docker run --rm -i -e BASE_URL=https://<app>.up.railway.app -e SUPABASE_URL \
  -e SUPABASE_ANON_KEY -v "$PWD/../k6:/k6" grafana/k6 run /k6/journey.js   # 20 users, 60 s
```

Wait for `/api/health` to answer `ok` a few times in a row after a deploy before load
testing: a run that starts mid-rollout measures the rollout. Record results in
[PERFORMANCE.md](PERFORMANCE.md).

### Deployed 2026-10-17

- https://app-production-2fdf.up.railway.app: Railway `rs-assist` / service `app`, US East,
  1 replica, sleeping off; Supabase us-east-1 through the transaction pooler.
- Smoke 21/21; k6 0% failed, chat p95 2.03 s; OCR p95 698 ms; booking p95 239 ms.
- Supabase auth audit rows (ISSUE-001): this project's `auth.audit_log_entries` holds no
  rows at all, so Withdrawal has none to remove; sign-in metadata lives in Supabase's
  platform logs instead (README known limit).

## 5. Uptime and keep-alive

Create a free UptimeRobot HTTP monitor on `https://<app>/api/health` every 5 minutes. Each
call writes a heartbeat row, which keeps the Supabase Free project from pausing after 7 idle
days, and the monitor's history is the uptime evidence for the review window.

**Submitted demo:** no monitor was set up (owner's choice). Uptime is not measured, and
the Supabase project pauses after 7 days without traffic; restore it from the Supabase
dashboard ([RUNBOOK](RUNBOOK.md)).

## 6. Enable CI (when the build is stable)

1. Install GitLab Runner in Docker Desktop and register a **project runner** for
   `debudash/rs-assist` with the tag `rs-assist-local` and the Docker executor
   (privileged, for the image build job).
2. GitLab → Settings → CI/CD → Variables: `CI_ENABLED=true`, and a masked `RAILWAY_TOKEN`
   (Railway → project → Settings → Tokens).
3. Push: lint → test → build → deploy runs on the default branch.
4. Optional local guard: `make hooks` turns on the pre-push hook.
