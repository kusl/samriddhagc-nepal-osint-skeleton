#!/usr/bin/env python3
"""Local Haiku runner — uses Claude CLI (Max subscription) for relevance + summary tasks.

Polls VPS for stories needing Haiku processing, runs them through `claude` CLI
with Haiku model, and POSTs results back.

Usage:
    OSINT_PASSWORD=your-osint-password python3 run_local_haiku.py --loop 120
    OSINT_PASSWORD=your-osint-password python3 run_local_haiku.py --once
    OSINT_PASSWORD=your-osint-password python3 run_local_haiku.py --once --task summary
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

VPS_URL = os.environ.get("VPS_URL", "http://3.148.250.92")
OSINT_EMAIL = os.environ.get("OSINT_EMAIL", "dev@narada.dev")
OSINT_PASSWORD = os.environ.get("OSINT_PASSWORD", "")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", shutil.which("claude") or "claude")
HAIKU_MODEL = "claude-haiku-4-5-20251001"

vps_token: str | None = None


def login() -> str:
    global vps_token
    r = requests.post(
        f"{VPS_URL}/api/v1/auth/login",
        json={"email": OSINT_EMAIL, "password": OSINT_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    vps_token = r.json()["access_token"]
    log.info("VPS login OK")
    return vps_token


def auth_headers() -> dict:
    global vps_token
    if not vps_token:
        login()
    return {"Authorization": f"Bearer {vps_token}"}


def vps_get(path: str, params: dict = None) -> dict:
    for attempt in range(2):
        r = requests.get(f"{VPS_URL}{path}", params=params, headers=auth_headers(), timeout=30)
        if r.status_code == 401 and attempt == 0:
            login()
            continue
        r.raise_for_status()
        return r.json()
    return {}


def vps_post(path: str, data: dict) -> dict:
    for attempt in range(2):
        r = requests.post(f"{VPS_URL}{path}", json=data, headers=auth_headers(), timeout=60)
        if r.status_code == 401 and attempt == 0:
            login()
            continue
        r.raise_for_status()
        return r.json()
    return {}


def call_haiku(prompt: str, timeout: int = 30) -> str:
    """Call Claude Haiku via CLI subprocess (Max subscription = free)."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--output-format", "text",
        "--model", HAIKU_MODEL,
        "--max-turns", "1",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI error: {result.stderr[:300]}")
    return result.stdout.strip()


def parse_json(text: str) -> dict:
    """Extract JSON from Claude response."""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError(f"No JSON found: {text[:200]}")


# ── Relevance task ──

RELEVANCE_PROMPT = """You are a Nepal intelligence relevance classifier. Determine if this story is primarily about Nepal or directly relevant to Nepal's domestic affairs.

RELEVANT: Events IN Nepal, Nepal government/economy/society, Nepal bilateral issues where Nepal is a primary actor, disasters in Nepal, Nepali diaspora issues.
NOT RELEVANT (even from Nepal media): Foreign conflicts (Israel-Iran, Russia-Ukraine, Gaza), other countries' internal politics/elections/economy, international sports where Nepal is not competing, stories where Nepal is mentioned only in passing.

Story:
Title: {title}
{summary_line}
{source_line}

Respond with ONLY valid JSON: {{"relevant": true/false, "reason": "one sentence"}}"""


def run_relevance(limit: int = 20) -> int:
    """Fetch borderline stories, check relevance via Haiku, post back."""
    data = vps_get("/api/v1/stories/pending-haiku", {"task": "relevance", "limit": limit})
    stories = data.get("stories", [])
    if not stories:
        log.info("Relevance: no pending stories")
        return 0

    log.info("Relevance: processing %d stories", len(stories))
    results = []

    for s in stories:
        try:
            prompt = RELEVANCE_PROMPT.format(
                title=s["title"],
                summary_line=f"Summary: {s['summary'][:300]}" if s.get("summary") else "",
                source_line=f"Source: {s['source_name']}" if s.get("source_name") else "",
            )
            raw = call_haiku(prompt)
            parsed = parse_json(raw)
            is_relevant = parsed.get("relevant", True)
            reason = parsed.get("reason", "")

            if not is_relevant:
                log.info("  FILTERED: %s — %s", s["title"][:60], reason[:80])
            else:
                log.debug("  OK: %s", s["title"][:60])

            results.append({"story_id": s["id"], "relevant": is_relevant})

        except Exception as e:
            log.warning("  ERROR on %s: %s", s["title"][:40], e)
            results.append({"story_id": s["id"], "relevant": True})  # fail-open

    if results:
        resp = vps_post("/api/v1/stories/haiku-results", {"task": "relevance", "results": results})
        log.info("Relevance: posted %d results, %d updated", len(results), resp.get("updated", 0))

    return len(results)


# ── Summary task ──

SUMMARY_PROMPT = """You are a professional intelligence analyst for Nepal OSINT. Create a concise, actionable intelligence summary from this news story.

IMPORTANT — Key Nepal party names (use EXACT names, do NOT hallucinate):
- रास्वपा / RASWAPA = Rastriya Swatantra Party (RSP) — led by Rabi Lamichhane, won 125 FPTP seats in 2082 elections
- नेकपा एमाले = CPN-UML — led by KP Sharma Oli
- कांग्रेस = Nepali Congress (NC) — led by Sher Bahadur Deuba
- नेकपा माओवादी = CPN-Maoist Centre — led by Pushpa Kamal Dahal (Prachanda)
- जसपा = Janata Samajbadi Party (JSP)
- राप्रपा = RPP (Rastriya Prajatantra Party)

Story:
Title: {title}
{summary_line}
{source_line}

Respond with ONLY valid JSON:
{{
  "headline": "Clear headline under 100 chars",
  "summary": "2-4 sentence intelligence summary",
  "category": "political|economic|security|disaster|social",
  "severity": "critical|high|medium|low",
  "key_entities": ["key people, orgs, places"],
  "verified": true,
  "confidence": 0.8
}}"""


def run_summary(limit: int = 20) -> int:
    """Fetch unsummarized stories, generate summaries via Haiku, post back."""
    data = vps_get("/api/v1/stories/pending-haiku", {"task": "summary", "limit": limit})
    stories = data.get("stories", [])
    if not stories:
        log.info("Summary: no pending stories")
        return 0

    log.info("Summary: processing %d stories", len(stories))
    results = []

    for s in stories:
        try:
            prompt = SUMMARY_PROMPT.format(
                title=s["title"],
                summary_line=f"Content: {s['summary'][:500]}" if s.get("summary") else "",
                source_line=f"Source: {s['source_name']}" if s.get("source_name") else "",
            )
            raw = call_haiku(prompt, timeout=45)
            parsed = parse_json(raw)

            log.info("  SUMMARIZED: %s → %s", s["title"][:50], parsed.get("headline", "?")[:50])
            results.append({"story_id": s["id"], "ai_summary": parsed})

        except Exception as e:
            log.warning("  ERROR on %s: %s", s["title"][:40], e)

    if results:
        resp = vps_post("/api/v1/stories/haiku-results", {"task": "summary", "results": results})
        log.info("Summary: posted %d results, %d updated", len(results), resp.get("updated", 0))

    return len(results)


def run_all():
    """Run both tasks."""
    run_relevance(limit=30)
    run_summary(limit=20)


def main():
    parser = argparse.ArgumentParser(description="Local Haiku runner (Max subscription)")
    parser.add_argument("--loop", type=int, help="Loop interval in seconds (e.g., 120)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--task", choices=["relevance", "summary", "all"], default="all")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if not OSINT_PASSWORD:
        print("Set OSINT_PASSWORD env var")
        sys.exit(1)

    login()

    task_fn = {
        "relevance": lambda: run_relevance(args.limit),
        "summary": lambda: run_summary(args.limit),
        "all": run_all,
    }[args.task]

    if args.once or not args.loop:
        task_fn()
    else:
        while True:
            try:
                task_fn()
            except Exception as e:
                log.error("Error: %s", e)
            log.info("Sleeping %ds...", args.loop)
            time.sleep(args.loop)


if __name__ == "__main__":
    main()
