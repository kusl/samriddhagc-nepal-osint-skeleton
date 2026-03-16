#!/usr/bin/env python3
"""Local Promise Tracker Agent — runs nightly via cron.

Architecture:
  1. Authenticate with VPS API (JWT)
  2. GET /stories/export — recent Nepal news stories
  3. GET /announcements/summary — government decisions
  4. GET /promises — current promise statuses
  5. Run Claude Sonnet locally (Max subscription = free)
  6. POST /promises/ingest — update changed statuses

Schedule: Once daily at 11 PM NPT (5:15 PM UTC)
Cron:     15 17 * * * /path/to/run_agents.sh promises >> /tmp/osint_agents.log 2>&1

Prerequisites:
  - claude CLI installed and authenticated (Max subscription)
  - Set OSINT_PASSWORD env var
"""
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ──
API_URL = os.environ.get("OSINT_API_URL", "https://nepalosint.com/api/v1")
EMAIL = os.environ.get("OSINT_EMAIL", "dev@narada.dev")
PASSWORD = os.environ.get("OSINT_PASSWORD", "")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", shutil.which("claude") or "claude")


async def authenticate(client: httpx.AsyncClient) -> str:
    """Login and return JWT token."""
    resp = await client.post(f"{API_URL}/auth/login", json={
        "email": EMAIL, "password": PASSWORD,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


async def fetch_recent_news(client: httpx.AsyncClient, token: str, hours: int = 48) -> list[dict]:
    """Fetch recent news stories from last N hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    resp = await client.get(
        f"{API_URL}/stories/export",
        params={"since": since, "limit": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    stories = resp.json().get("stories", [])
    # Filter for political/governance/economy stories
    political_keywords = [
        "parliament", "bill", "cabinet", "minister", "government", "reform",
        "corruption", "judiciary", "court", "digital", "tax", "budget",
        "election", "rsp", "swatantra", "manifesto", "promise",
        "hydropower", "broadband", "education", "health", "nepse",
        "cooperative", "procurement", "diaspora", "cartel", "monopoly",
        "constitution", "amendment", "prime minister", "PM",
        "संसद", "विधेयक", "मन्त्री", "सरकार", "सुधार", "भ्रष्टाचार",
        "न्यायालय", "डिजिटल", "कर", "बजेट", "निर्वाचन", "स्वतन्त्र",
    ]
    relevant = []
    for s in stories:
        text = (s.get("title", "") + " " + s.get("summary", "")).lower()
        if any(kw.lower() in text for kw in political_keywords):
            relevant.append(s)
    return relevant[:60]  # cap to avoid huge prompts


async def fetch_announcements(client: httpx.AsyncClient, token: str) -> list[dict]:
    """Fetch recent government announcements."""
    resp = await client.get(
        f"{API_URL}/announcements/summary",
        params={"limit": 30},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("latest", [])[:20]


async def fetch_current_promises(client: httpx.AsyncClient, token: str) -> list[dict]:
    """Fetch current promise statuses."""
    resp = await client.get(
        f"{API_URL}/promises/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json().get("promises", [])


def run_claude_analysis(promises: list[dict], news: list[dict], announcements: list[dict]) -> list[dict]:
    """Run Claude Sonnet to analyze promises against news."""
    promise_text = json.dumps([{
        "id": p["promise_id"],
        "promise": p["promise"],
        "category": p["category"],
        "current_status": p["status"],
        "current_detail": p.get("status_detail", ""),
    } for p in promises], indent=2)

    news_text = "\n".join([
        f"- [{s.get('source', 'unknown')}] {s.get('title', 'Untitled')}: {s.get('summary', '')[:200]}"
        for s in news
    ])

    ann_text = "\n".join([
        f"- [{a.get('source', 'unknown')}] {a.get('title', 'Untitled')}: {a.get('content', '')[:200]}"
        for a in announcements
    ])

    prompt = f"""You are an expert political analyst tracking Nepal's RSP (Rastriya Swatantra Party) manifesto promises from the 2082 election.

CURRENT PROMISE STATUSES:
{promise_text}

RECENT NEWS (last 48 hours):
{news_text if news_text.strip() else "No relevant political news in last 48 hours."}

RECENT GOVERNMENT ANNOUNCEMENTS:
{ann_text if ann_text.strip() else "No recent government announcements."}

TASK: Analyze the news and announcements against each promise. Determine if any promise status should change.

STATUS OPTIONS:
- not_started: No action taken on this promise
- in_progress: Government/parliament has started working on this (bill introduced, committee formed, public discussion started)
- partially_fulfilled: Some concrete action taken but not fully delivered
- fulfilled: Promise substantially delivered
- stalled: Was in progress but has stopped or been abandoned

RULES:
1. Only change status if there is CLEAR evidence in the news/announcements
2. Be conservative — don't change status on speculation
3. Provide specific evidence (which news story, what action)
4. If no changes needed, return empty updates array
5. Nepal's new parliament (2082) was recently elected — many promises will still be "not_started"

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "analysis_date": "YYYY-MM-DD",
  "changes_found": true/false,
  "updates": [
    {{
      "promise_id": "G1",
      "status": "in_progress",
      "status_detail": "Brief explanation of what happened and why status changed",
      "evidence_urls": "[]"
    }}
  ]
}}

If no changes, return: {{"analysis_date": "YYYY-MM-DD", "changes_found": false, "updates": []}}"""

    logger.info(f"Running Claude analysis on {len(promises)} promises against {len(news)} news + {len(announcements)} announcements...")

    # Filter CLAUDECODE env to avoid nested session error
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        result = subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--model", "sonnet", "--output-format", "json"],
            capture_output=True, text=True, timeout=120, env=env,
        )

        if result.returncode != 0:
            logger.error(f"Claude CLI failed: {result.stderr}")
            return []

        # Parse Claude output — extract JSON from response
        output = result.stdout.strip()

        # claude --output-format json wraps in {"result": "..."}
        try:
            wrapper = json.loads(output)
            if "result" in wrapper:
                output = wrapper["result"]
        except json.JSONDecodeError:
            pass

        # Find JSON in output
        json_match = re.search(r'\{[\s\S]*\}', output)
        if not json_match:
            logger.warning("No JSON found in Claude output")
            return []

        parsed = json.loads(json_match.group())
        updates = parsed.get("updates", [])
        changes = parsed.get("changes_found", False)

        logger.info(f"Claude analysis complete: changes_found={changes}, updates={len(updates)}")
        return updates

    except subprocess.TimeoutExpired:
        logger.error("Claude CLI timed out after 120s")
        return []
    except Exception as e:
        logger.exception(f"Claude analysis failed: {e}")
        return []


async def ingest_updates(client: httpx.AsyncClient, token: str, updates: list[dict]) -> dict:
    """Push updated statuses to VPS."""
    resp = await client.post(
        f"{API_URL}/promises/ingest",
        json={"updates": updates},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def main():
    if not PASSWORD:
        logger.error("OSINT_PASSWORD env var not set")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=60) as client:
        # 1. Authenticate
        logger.info("Authenticating with VPS API...")
        token = await authenticate(client)
        logger.info("Authenticated successfully")

        # 2. Fetch data in parallel
        logger.info("Fetching current data...")
        promises, news, announcements = await asyncio.gather(
            fetch_current_promises(client, token),
            fetch_recent_news(client, token, hours=48),
            fetch_announcements(client, token),
        )

        logger.info(f"Fetched: {len(promises)} promises, {len(news)} news, {len(announcements)} announcements")

        if not promises:
            logger.warning("No promises found — seed first via POST /promises/seed")
            sys.exit(1)

        # 3. Run Claude analysis
        updates = run_claude_analysis(promises, news, announcements)

        if not updates:
            logger.info("No promise status changes detected")
            return

        # 4. Push updates
        logger.info(f"Ingesting {len(updates)} promise updates...")
        result = await ingest_updates(client, token, updates)
        logger.info(f"Ingested: {result}")


if __name__ == "__main__":
    asyncio.run(main())
