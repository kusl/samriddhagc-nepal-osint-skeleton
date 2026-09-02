# Deploying the public site (nepalosint.com)

The public, read-only surface of v5 runs on the **IONOS box, `74.208.36.123`**
(`ssh mc`), sharing it with the NEPSE Quant terminal, the Minecraft server and
yetidai. First deployed 2026-09-02.

**The old AWS Lightsail host is dead** — ignore the Lightsail instructions in
`nepalosint_v5_arch` and in the README.

## Shape

```
Cloudflare (Flexible: browser<->CF is HTTPS, CF<->origin is HTTP :80)
  -> Caddy on the VPS, vhost `http://nepalosint.com`
    -> 127.0.0.1:8300  osint_frontend  (nginx, serves dist/ + proxies /api and /ws)
      -> osint_backend :8000  (FastAPI)  -> osint_postgres / osint_redis
         osint_worker          (APScheduler: news, disasters, river, flood sync)
```

Deploy dir `/opt/nepal-osint`. Compose is
`docker-compose.prod.yml` + `docker-compose.override.yml` (the override is
VPS-only and NOT in git: it moves the frontend off :80, which Caddy owns, and
sets the memory limits this shared box can afford).

`/opt/nepal-osint/.env` holds the generated `POSTGRES_PASSWORD` and
`JWT_SECRET_KEY`. It exists only there — **back it up before rebuilding the box.**

## Deploy an update

```bash
# 1. build the public bundle (flags come from frontend/.env.production)
cd frontend && docker exec -w /app nepal_v5_frontend npx tsc --noEmit \
  && docker exec -w /app nepal_v5_frontend npx vite build --mode production

# 2. ship code
cd .. && rsync -az --delete -e ssh frontend/dist/ mc:/opt/nepal-osint/frontend/dist/
rsync -az -e ssh --exclude '__pycache__/' --exclude '*.pyc' \
  backend-v5/app/ mc:/opt/nepal-osint/backend-v5/app/

# 3. rebuild + restart
ssh mc 'cd /opt/nepal-osint && \
  docker compose -f docker-compose.prod.yml -f docker-compose.override.yml build frontend backend worker && \
  docker compose -f docker-compose.prod.yml -f docker-compose.override.yml up -d frontend backend worker'
```

`worker` and `migrate` do **not** mount source — they must be rebuilt, not just
restarted, for scheduler or migration changes to take effect.

## What "public" means

`frontend/.env.production` drives `src/config/deployment.ts`:

- `VITE_PUBLIC_ONLY=true` — no account UI anywhere; `/login`, `/dev` and
  `/uitest` redirect to `/`; the first-run guide drops its "Create account" CTA
  and the tour drops its account steps. The backend's anonymous auto-login
  (`POST /auth/public`) still runs — it is invisible plumbing that mints the
  token the read APIs need, not a sign-in.
- `VITE_DISABLED_PRESETS=economy` — the Economy tab is hidden because its NRB
  macro tables are empty on this deployment (`/economy/nrb-snapshot` 503s).
  Delete the line once the NRB backfill lands.

## Gotchas

- **The `http://` prefix on the Caddy vhost is load-bearing.** A bare hostname
  makes Caddy redirect :80 -> https://, which behind Cloudflare Flexible is an
  infinite loop.
- **The vhost needs its own `handle_errors`.** The bare `:80` block in the
  Caddyfile has no host matcher, so its `handle_errors` registers against every
  host and would answer an OSINT outage with NEPSE's maintenance page.
- **NDRRMA (`ndrrma.gov.np`) refuses connections from this IP** on both :80 and
  :443 — it appears to block the IONOS range. The flood sync degrades cleanly:
  the toll still advances from the citizen bulletin, and OPMCM still works, but
  official sitreps/rescue panels/press images stay frozen. If they are needed
  live, sync them from a machine NDRRMA accepts and push via an ingest endpoint,
  the way the Claude-heavy agents already work (`LOCAL_AGENTS.md`).
- The database was seeded by restoring a `pg_dump` of the local dev DB, so the
  curated flood content came across. There is **no automated backup yet.**
