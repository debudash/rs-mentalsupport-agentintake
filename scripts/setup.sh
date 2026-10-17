#!/usr/bin/env bash
# One-time local setup: .env from .env.example, an encryption key, local Supabase (auth +
# Postgres in Docker), and its keys written into .env. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

# set_var NAME VALUE: replace (or append) NAME=VALUE in .env; values are passed via the
# environment so URLs and keys need no escaping.
set_var() {
  NAME="$1" VALUE="$2" awk '
    BEGIN { n = ENVIRON["NAME"]; v = ENVIRON["VALUE"]; done = 0 }
    index($0, n "=") == 1 { print n "=" v; done = 1; next }
    { print }
    END { if (!done) print n "=" v }
  ' .env > .env.tmp && mv .env.tmp .env
}

if ! grep -qE '^FIELD_ENCRYPTION_KEY=.+' .env; then
  if command -v openssl >/dev/null; then
    key=$(openssl rand -base64 32 | tr '+/' '-_')
  else
    key=$(docker run --rm python:3.12-slim python -c \
      "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  fi
  set_var FIELD_ENCRYPTION_KEY "$key"
  echo "Generated FIELD_ENCRYPTION_KEY"
fi

echo "Starting local Supabase (Postgres + Auth). The first run downloads images..."
npx --yes supabase start \
  -x vector,logflare,realtime,storage-api,imgproxy,edge-runtime,studio,postgres-meta,supavisor

status=$(npx --yes supabase status -o env)
get() { echo "$status" | sed -n "s/^$1=\"\{0,1\}\([^\"]*\)\"\{0,1\}\r\{0,1\}$/\1/p"; }
set_var SUPABASE_URL "$(get API_URL)"
set_var SUPABASE_ANON_KEY "$(get ANON_KEY)"
set_var SUPABASE_SERVICE_ROLE_KEY "$(get SERVICE_ROLE_KEY)"
set_var SUPABASE_JWT_SECRET "$(get JWT_SECRET)"
set_var DATABASE_URL "$(get DB_URL | sed 's#^postgresql://#postgresql+psycopg://#')"
echo "Wrote local Supabase settings to .env"
echo "Next: make seed && make up   (app on http://localhost:8000)"
