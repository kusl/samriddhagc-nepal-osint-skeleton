#!/usr/bin/env python3
"""Local election ticker agent — scans recent tweets/stories for breaking election info.

Runs every 5 minutes via cron. Uses Claude Sonnet (Max = free) to extract
structured election results from raw text, then POSTs to the ticker ingest endpoint.

Architecture:
  1. GET /stories/export + /twitter/export (last 10 min)
  2. Send to Claude Sonnet: "Extract election results from these"
  3. POST /election-results/ticker/ingest with structured alerts

Usage:
  OSINT_PASSWORD=your-osint-password python run_election_ticker_agent.py
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import time

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TICKER-AGENT] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ──
API_URL = os.environ.get("OSINT_API_URL", "https://nepalosint.com/api/v1")
EMAIL = os.environ.get("OSINT_EMAIL", "dev@narada.dev")
PASSWORD = os.environ.get("OSINT_PASSWORD", "")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", shutil.which("claude") or "claude")
LOOKBACK_MINUTES = 10


async def authenticate(client: httpx.AsyncClient) -> str:
    """Get JWT access token."""
    resp = await client.post(f"{API_URL}/auth/login", json={
        "email": EMAIL,
        "password": PASSWORD,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


async def fetch_recent_data(client: httpx.AsyncClient, token: str) -> dict:
    """Fetch recent stories and tweets from the API."""
    headers = {"Authorization": f"Bearer {token}"}

    stories_resp, tweets_resp = await asyncio.gather(
        client.get(f"{API_URL}/stories/export", params={
            "hours": 1, "limit": 30,
        }, headers=headers),
        client.get(f"{API_URL}/twitter/export", params={
            "hours": 1, "limit": 50,
        }, headers=headers),
    )

    stories_data = stories_resp.json() if stories_resp.status_code == 200 else {}
    tweets_data = tweets_resp.json() if tweets_resp.status_code == 200 else {}

    # Export endpoints return {"stories": [...], "total": N} and {"tweets": [...], "total": N}
    stories = stories_data.get("stories", []) if isinstance(stories_data, dict) else stories_data
    tweets = tweets_data.get("tweets", []) if isinstance(tweets_data, dict) else tweets_data

    return {"stories": stories, "tweets": tweets}


async def call_claude(prompt: str, timeout: int = 120) -> str:
    """Call Claude Sonnet via CLI subprocess."""
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--output-format", "text",
        "--model", "claude-sonnet-4-6",
        "--max-turns", "1",
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Claude CLI failed (exit {proc.returncode}): {err}")

    return stdout.decode("utf-8", errors="replace").strip()


def extract_json(raw: str) -> list:
    """Extract JSON array from Claude's response."""
    # Try code block first
    match = re.search(r"```(?:json)?\s*\n(.*?)```", raw, re.DOTALL)
    text = match.group(1).strip() if match else raw

    # Find array
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    return []


def make_id(headline: str) -> str:
    """Generate stable ID from headline text."""
    return hashlib.md5(headline.encode()).hexdigest()[:12]


PROMPT_TEMPLATE = """You are an election data extraction agent for Nepal's 2082 House of Representatives election.

Analyze the following recent news stories and tweets. Extract ONLY verifiable election-related breaking updates.

EXTRACT these types:
1. "elected" — Confirmed winner declarations (name, party, constituency, margin if available)
2. "leading" — Vote counting updates showing who leads a constituency
3. "update" — Major election events (violence, recount, turnout milestone, controversy)

DO NOT extract:
- Opinions, predictions, or analysis
- Already well-known information
- Non-election news

Return a JSON array of objects. Each object:
{{
  "type": "elected" | "leading" | "update",
  "headline": "Short, factual ticker headline (max 120 chars)",
  "confidence": 0.0-1.0 (how confident you are this is accurate)
}}

Return an empty array [] if nothing newsworthy is found. Only include items with confidence >= 0.7.

=== RECENT STORIES (last hour) ===
{stories}

=== RECENT TWEETS (last hour) ===
{tweets}

Return ONLY the JSON array, no other text."""


async def run():
    t0 = time.monotonic()
    logger.info("=== Election ticker agent starting ===")

    if not PASSWORD:
        logger.error("OSINT_PASSWORD not set")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Authenticate
        try:
            token = await authenticate(client)
        except Exception as e:
            logger.error(f"Auth failed: {e}")
            sys.exit(1)

        # 2. Fetch recent data
        try:
            data = await fetch_recent_data(client, token)
        except Exception as e:
            logger.error(f"Data fetch failed: {e}")
            sys.exit(1)

        stories = data.get("stories", [])
        tweets = data.get("tweets", [])

        if not stories and not tweets:
            logger.info("No recent data to analyze, skipping")
            return

        # Format for prompt
        story_text = "\n".join(
            f"- [{s.get('severity', '?')}] {s.get('title', '')} ({s.get('source_name', '')})"
            for s in stories[:30]
        ) or "(none)"

        tweet_text = "\n".join(
            f"- @{t.get('author_username', '?')}: {t.get('text', '')[:200]}"
            for t in tweets[:50]
        ) or "(none)"

        prompt = PROMPT_TEMPLATE.format(stories=story_text, tweets=tweet_text)

        # 3. Call Claude Sonnet
        logger.info(f"Analyzing {len(stories)} stories + {len(tweets)} tweets...")
        try:
            raw = await call_claude(prompt)
        except Exception as e:
            logger.error(f"Claude call failed: {e}")
            return

        # 4. Parse results
        try:
            alerts = extract_json(raw)
        except Exception as e:
            logger.warning(f"Failed to parse Claude output: {e}")
            logger.debug(f"Raw output: {raw[:500]}")
            return

        if not alerts:
            logger.info("No breaking election alerts extracted")
            return

        # Filter by confidence
        alerts = [a for a in alerts if a.get("confidence", 0) >= 0.7]
        if not alerts:
            logger.info("No alerts above confidence threshold")
            return

        # Add IDs
        for a in alerts:
            a["id"] = make_id(a.get("headline", ""))
            a["source"] = "ai-agent"

        # 5. POST to ticker ingest
        try:
            headers = {"Authorization": f"Bearer {token}"}
            resp = await client.post(
                f"{API_URL}/election-results/ticker/ingest",
                json={"alerts": alerts},
                headers=headers,
            )
            resp.raise_for_status()
            result = resp.json()
            logger.info(f"Ingested {result.get('added', 0)} alerts ({result.get('total', 0)} total)")
        except Exception as e:
            logger.error(f"Ingest failed: {e}")
            return

    elapsed = time.monotonic() - t0
    logger.info(f"=== Election ticker agent done ({elapsed:.1f}s) ===")


if __name__ == "__main__":
    asyncio.run(run())
