# Local Agent Architecture

## WHY: Claude-heavy agents run on YOUR Mac, not VPS

You have a Claude Max subscription ($20/month) which gives unlimited Claude CLI usage.
The VPS would use the Anthropic SDK which costs API credits per call.

**Rule: NEVER run analyst or province agents on VPS via SDK. Always run locally via CLI.**

## Architecture

```
Your Mac (Claude Max CLI = free)          VPS (API only, no Claude)
┌─────────────────────────┐               ┌──────────────────────┐
│ agents/run_local_api.py │  HTTPS+JWT    │ FastAPI backend      │
│  ├─ analyst job         │──────────────>│  ├─ GET /stories/export
│  │   └─ claude CLI      │               │  ├─ GET /twitter/export
│  │       (Sonnet, free) │               │  ├─ POST /briefs/ingest
│  └─ province job        │               │  └─ POST /province-anomalies/ingest
│      └─ claude CLI      │               │                      │
│          (Sonnet, free) │               │ Scheduler (VPS):     │
│                         │               │  ├─ Nitter scraper   │
│ agents/run_agents.sh    │               │  ├─ Story ingestion  │
│  └─ runs every 12 hrs   │               │  ├─ Weather/river    │
└─────────────────────────┘               │  └─ Elections        │
                                          │  (NO analyst/province│
                                          │   — disabled!)       │
                                          └──────────────────────┘
```

## What runs WHERE

| Agent | Where | Schedule | Cost | Why |
|-------|-------|----------|------|-----|
| Analyst Brief | LOCAL Mac | Every 12 hours (cron/manual) | FREE (Max CLI) | Claude Sonnet = free on Max |
| Province Anomaly | LOCAL Mac | Every 12 hours (cron/manual) | FREE (Max CLI) | Claude Sonnet = free on Max |
| Nitter Scraper | LOCAL Mac | Every 30 min (cron) | FREE (no Claude) | VPS IP blocked by nitter (403) |
| Story Ingestion | VPS | Every 30 min (scheduler) | FREE (no Claude) | RSS/scraping only |
| Weather/River/KPI | VPS | Various (scheduler) | FREE (no Claude) | API calls only |

## Setup (one-time)

### 1. Install cron jobs

```bash
crontab -e
```

Add these lines:

```cron
# Nepal OSINT — Local agents (Claude Max = free, Nitter = VPS blocked)
0 */12 * * * /Users/samriddhagc/Desktop/Projects/nepal_osint_v5/agents/run_agents.sh analyst >> /tmp/osint_agents.log 2>&1
30 */12 * * * /Users/samriddhagc/Desktop/Projects/nepal_osint_v5/agents/run_agents.sh province >> /tmp/osint_agents.log 2>&1
*/30 * * * * /Users/samriddhagc/Desktop/Projects/nepal_osint_v5/agents/run_agents.sh nitter >> /tmp/osint_agents.log 2>&1
```

### 2. Verify cron is allowed

macOS may block cron. Go to:
System Settings > Privacy & Security > Full Disk Access
Add `/usr/sbin/cron` (or Terminal.app)

### 3. Check it works

```bash
# Manual test
OSINT_PASSWORD=your-osint-password venv/bin/python agents/run_local_api.py analyst --hours 6
OSINT_PASSWORD=your-osint-password venv/bin/python agents/run_local_api.py province --hours 6

# Check cron logs
tail -f /tmp/osint_agents.log
```

## Manual runs

```bash
cd ~/Desktop/Projects/nepal_osint_v5

# Analyst brief (situation report)
OSINT_PASSWORD=your-osint-password venv/bin/python agents/run_local_api.py analyst --hours 6

# Province anomaly (7-province threat assessment)
OSINT_PASSWORD=your-osint-password venv/bin/python agents/run_local_api.py province --hours 6

# Both at once
./agents/run_agents.sh all
```

## VPS scheduler (these are DISABLED — run locally instead)

In `app/tasks/scheduler.py`, the following jobs are commented out:
- **Analyst Agent** — uses Claude Sonnet (costs API credits on VPS)
- **Province Anomaly Agent** — uses Claude Sonnet (costs API credits on VPS)
- **Nitter Scraper** — VPS IP (AWS Lightsail) blocked by nitter instances (403 Forbidden)

These must NEVER be re-enabled unless you have API credits AND a non-blocked IP.

The VPS still runs everything else (RSS ingestion, weather, river, elections, market, etc.) automatically.

## Files

| File | Purpose |
|------|---------|
| `agents/run_local_api.py` | Top-level wrapper for the API agent runner |
| `agents/run_agents.sh` | Top-level cron wrapper |
| `backend-v5/run_local_api.py` | Canonical API agent implementation |
| `backend-v5/run_agents.sh` | Canonical cron implementation |
| `LOCAL_AGENTS.md` | This file |
| `app/tasks/scheduler.py` | VPS scheduler (analyst/province DISABLED) |
| `app/api/v1/briefs.py` | POST /briefs/ingest endpoint |
| `app/api/v1/province_anomalies.py` | POST /province-anomalies/ingest endpoint |
| `app/api/v1/twitter.py` | GET /twitter/export endpoint |
| `app/api/v1/stories.py` | GET /stories/export endpoint |

## Troubleshooting

**"Claude Code cannot be launched inside another Claude Code session"**
→ Already handled: `backend-v5/run_local_api.py` filters `CLAUDECODE` env var from subprocess

**Cron not running**
→ Check `crontab -l` to verify entries exist
→ Check macOS Full Disk Access for cron
→ Check `/tmp/osint_agents.log` for errors

**API returns 401**
→ `OSINT_PASSWORD` env var not set or wrong
→ Check VPS backend is running: `curl https://nepalosint.com/api/v1/auth/login`

**Low province classification rate**
→ Normal — only stories/tweets mentioning specific districts/provinces get classified
→ More tweets = better classification (Nitter scraper helps)
