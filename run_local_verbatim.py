#!/usr/bin/env python3
"""Local Haiku runner for verbatim parliamentary session analysis.

ONE Haiku call per session — sends all speeches as batch, gets back:
- Session summary with key agenda
- Agenda items with debate intensity, supporters/opponents, outcome
- Per-speaker scoreboard (engagement, relevance scores)

Usage:
    OSINT_PASSWORD=devpassword123 python3 run_local_verbatim.py --once
    OSINT_PASSWORD=devpassword123 python3 run_local_verbatim.py --loop 300
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
        r = requests.get(f"{VPS_URL}{path}", params=params, headers=auth_headers(), timeout=60)
        if r.status_code == 401 and attempt == 0:
            login()
            continue
        r.raise_for_status()
        return r.json()
    return {}


def vps_post(path: str, data: dict) -> dict:
    for attempt in range(2):
        r = requests.post(f"{VPS_URL}{path}", json=data, headers=auth_headers(), timeout=120)
        if r.status_code == 401 and attempt == 0:
            login()
            continue
        r.raise_for_status()
        return r.json()
    return {}


def call_haiku(prompt: str, timeout: int = 120) -> str:
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


# ── Single batch prompt per session ──

SESSION_BATCH_PROMPT = """You are an expert analyst of Nepal's parliamentary proceedings (House of Representatives).
Analyze this entire parliamentary session and provide a structured analysis.

NOTE: The text may contain garbled Unicode characters (mojibake) from PDF extraction. Do your best to interpret the Nepali text despite encoding issues.

Session: {title}
Date: {date}
Total speeches: {speech_count}

SPEECHES:
{speeches_block}

Respond with ONLY valid JSON (no markdown, no explanation):
{{
  "session_summary": "3-5 sentence English overview of the session — what was discussed, key outcomes, overall tone",
  "key_topics": ["topic1", "topic2", "topic3"],
  "bills_discussed": ["bill name or description"],
  "agenda_items": [
    {{
      "topic": "Short agenda title in English",
      "description": "What was debated about this topic",
      "intensity": "high|medium|low",
      "supporters": ["Party Name 1"],
      "opponents": ["Party Name 2"],
      "outcome": "passed|rejected|deferred|debated|procedural"
    }}
  ],
  "speaker_scores": [
    {{
      "speaker_name_ne": "Original Nepali name as shown",
      "speaker_name_en": "Romanized English name",
      "party_en": "English party name",
      "speech_count": 1,
      "total_words": 500,
      "relevance_score": 7,
      "engagement_score": 8,
      "key_contribution": "One sentence about their main contribution"
    }}
  ]
}}

Rules for scoring:
- relevance_score (1-10): How substantive and relevant were their contributions? 10=highly substantive policy debate, 1=purely procedural
- engagement_score (1-10): How actively did they engage in debate? 10=passionate detailed arguments, 1=brief procedural remarks
- Include ALL speakers who made substantive contributions (skip purely procedural chair announcements)
- Party names in English: "Nepali Congress", "Nepal Communist Party (UML)", "Nepal Communist Party (Maoist Center)", "Rastriya Swotantra Party", "Communist Party of Nepal (Unified Socialist)", "Janata Samajbadi Party Nepal", "Rastriya Prajatantra Party", etc."""


def build_speeches_block(speeches: list[dict]) -> str:
    """Build concatenated speech block, truncating each to ~500 words."""
    lines = []
    for i, s in enumerate(speeches):
        name = s.get("speaker_name_ne", "?")
        party = s.get("speaker_party_en") or s.get("speaker_party_ne") or "?"
        timestamp = s.get("timestamp", "")
        text = (s.get("speech_text") or "")[:2000]  # ~500 words
        lines.append(f"[{i+1}] {name} ({party}) [{timestamp}]:\n{text}\n")
    return "\n".join(lines)


def analyze_session(session: dict) -> dict | None:
    """Analyze a full verbatim session with ONE Haiku call."""
    session_id = session["session_id"]
    title = session.get("title_ne", "Unknown session")
    date_str = session.get("session_date") or session.get("session_date_bs") or "Unknown"
    speeches = session.get("speeches", [])

    if not speeches:
        log.warning("  Session %s has no speeches, skipping", session_id[:8])
        return None

    log.info("  Analyzing: %s (%d speeches)...", title[:50], len(speeches))

    speeches_block = build_speeches_block(speeches)
    prompt = SESSION_BATCH_PROMPT.format(
        title=title,
        date=date_str,
        speech_count=len(speeches),
        speeches_block=speeches_block,
    )

    try:
        raw = call_haiku(prompt, timeout=120)
        result = parse_json(raw)
    except Exception as e:
        log.error("  Analysis failed: %s", e)
        return None

    summary = result.get("session_summary", "")
    agendas = result.get("agenda_items", [])
    scores = result.get("speaker_scores", [])

    log.info("  Summary: %s", summary[:100])
    log.info("  Agendas: %d, Speakers scored: %d", len(agendas), len(scores))

    return {
        "session_id": session_id,
        "session_summary": summary,
        "key_topics": result.get("key_topics", []),
        "bills_discussed": result.get("bills_discussed", []),
        "agenda_items": agendas,
        "speaker_scores": scores,
        "speeches": [],  # No per-speech analysis in batch mode
    }


def run_analysis(limit: int = 18) -> int:
    """Fetch unanalyzed sessions, analyze via Haiku, post results back."""
    data = vps_get("/api/v1/verbatim/pending-analysis", {"limit": limit})
    sessions = data.get("sessions", [])

    if not sessions:
        log.info("No pending sessions to analyze")
        return 0

    log.info("Found %d unanalyzed sessions", len(sessions))
    analyzed = 0

    for session in sessions:
        result = analyze_session(session)
        if not result:
            continue

        try:
            resp = vps_post("/api/v1/verbatim/admin/ingest-analysis", result)
            log.info("  Ingested: %s", resp.get("message", "?")[:60])
            analyzed += 1
        except Exception as e:
            log.error("  Ingest failed for %s: %s", session["session_id"][:8], e)

    log.info("Done! Analyzed %d/%d sessions", analyzed, len(sessions))
    return analyzed


def main():
    parser = argparse.ArgumentParser(description="Local Haiku runner for verbatim analysis (Max subscription)")
    parser.add_argument("--loop", type=int, help="Loop interval in seconds (e.g., 300)")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--limit", type=int, default=18, help="Max sessions per run")
    args = parser.parse_args()

    if not OSINT_PASSWORD:
        print("Set OSINT_PASSWORD env var")
        sys.exit(1)

    login()

    if args.once or not args.loop:
        run_analysis(args.limit)
    else:
        while True:
            try:
                run_analysis(args.limit)
            except Exception as e:
                log.error("Error: %s", e)
            log.info("Sleeping %ds...", args.loop)
            time.sleep(args.loop)


if __name__ == "__main__":
    main()
