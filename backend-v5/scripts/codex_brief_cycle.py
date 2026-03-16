#!/usr/bin/env python3
"""Generate and post a 6-hour brief with Codex-written summary/judgment.

Flow:
1. Build the deterministic brief inputs from live NepalOSINT exports.
2. Distill the source material into a compact context file.
3. Run Codex CLI (`gpt-5.2`) as a subprocess to rewrite only:
   - national_summary
   - key_judgment
4. POST the completed brief + province monitor payloads to production.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/Users/samriddhagc/Desktop/Projects/nepal_osint_v5")
BACKEND = ROOT / "backend-v5"
SCRIPTS = BACKEND / "scripts"
OUTPUT_ROOT = BACKEND / "analysis_output" / "codex_brief_auto"
LATEST_DIR = OUTPUT_ROOT / "latest"
RUNS_DIR = OUTPUT_ROOT / "runs"
LOCK_FILE = OUTPUT_ROOT / "codex_brief_cycle.lock"
SCHEMA_FILE = SCRIPTS / "codex_brief_schema.json"
CODEX_BIN = Path("/Applications/Codex.app/Contents/Resources/codex")

API_ROOT = os.environ.get("OSINT_API_URL", "https://nepalosint.com/api/v1")
LOGIN_EMAIL = os.environ.get("OSINT_EMAIL", "dev@narada.dev")
LOGIN_PASSWORD = os.environ.get("OSINT_PASSWORD", "")
MODEL = os.environ.get("CODEX_BRIEF_MODEL", "gpt-5.2")
HOURS = int(os.environ.get("CODEX_BRIEF_HOURS", "6"))
INTL_KEYWORDS = {
    "india", "indian", "dubai", "ukraine", "russia", "russian", "nato", "sweden",
    "israel", "gaza", "iran", "america", "american", "japan", "australia",
    "भारत", "भारतीय", "दुबई", "युक्रेन", "रूसी", "रुस", "नेटो", "स्वीडेन",
    "इजरायल", "गाजा", "इरान", "अमेरिकी", "जापान", "अस्ट्रेलिया", "ओडिसा", "ओडिशा",
}


sys.path.insert(0, str(SCRIPTS))
from generate_live_brief import BriefGenerator  # noqa: E402


def ensure_dirs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def request_json(url: str, method: str = "GET", headers: dict[str, str] | None = None, payload: dict | None = None) -> dict:
    cmd = [
        "curl",
        "-sS",
        "-A",
        "Mozilla/5.0",
        "-X",
        method,
        url,
        "-H",
        "Content-Type: application/json",
    ]
    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
    if payload is not None:
        cmd.extend(["-d", json.dumps(payload, ensure_ascii=False)])
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def login() -> str:
    if not LOGIN_PASSWORD:
        raise RuntimeError("OSINT_PASSWORD must be set before posting briefs")
    data = request_json(
        f"{API_ROOT}/auth/login",
        method="POST",
        payload={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
    )
    return data["access_token"]


def post_payload(path: str, payload: dict[str, Any], token: str) -> dict[str, Any]:
    return request_json(
        f"{API_ROOT}{path}",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
        payload=payload,
    )


def is_domestic_story(story: dict[str, Any]) -> bool:
    title = (story.get("title") or "").lower()
    summary = ""
    ai = story.get("ai_summary") if isinstance(story.get("ai_summary"), dict) else {}
    if ai:
        summary = (ai.get("summary") or "").lower()
    has_geo = bool(story.get("_provinces") or story.get("_districts"))
    if has_geo:
        return True
    text = f"{title} {summary}"
    return not any(keyword in text for keyword in INTL_KEYWORDS)


def choose_top_stories(stories: list[dict[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    ranked = sorted(
        stories,
        key=lambda story: (
            severity_rank.get(story.get("severity"), 0),
            story.get("published_at") or "",
        ),
        reverse=True,
    )
    domestic_ranked = [story for story in ranked if is_domestic_story(story)]
    source_pool = domestic_ranked if len(domestic_ranked) >= min(12, limit // 2) else ranked
    selected = []
    for story in source_pool[:limit]:
        ai = story.get("ai_summary") if isinstance(story.get("ai_summary"), dict) else {}
        selected.append(
            {
                "title": story.get("title"),
                "source_name": story.get("source_name"),
                "category": story.get("category"),
                "severity": story.get("severity"),
                "published_at": story.get("published_at"),
                "provinces": story.get("_provinces") or [],
                "districts": story.get("_districts") or [],
                "summary": (ai.get("summary") or "")[:360],
            }
        )
    return selected


def choose_top_tweets(tweets: list[dict[str, Any]], limit: int = 18) -> list[dict[str, Any]]:
    ranked = sorted(
        tweets,
        key=lambda tweet: (
            tweet.get("like_count") or 0,
            tweet.get("reply_count") or 0,
            tweet.get("tweeted_at") or "",
        ),
        reverse=True,
    )
    return [
        {
            "author": tweet.get("author_username") or tweet.get("author_name"),
            "category": tweet.get("category"),
            "tweeted_at": tweet.get("tweeted_at"),
            "text": (tweet.get("text") or "")[:320],
        }
        for tweet in ranked[:limit]
    ]


def build_context(result: dict[str, Any]) -> dict[str, Any]:
    province_sitreps = result["brief_payload"].get("province_sitreps", [])
    immediate_watch = []
    for province in province_sitreps:
        hotspots = province.get("hotspots") or []
        flagged = province.get("flagged_stories") or []
        immediate_watch.append(
            {
                "province_name": province.get("province_name"),
                "threat_level": province.get("threat_level"),
                "threat_trajectory": province.get("threat_trajectory"),
                "story_count": province.get("story_count"),
                "bluf": province.get("bluf"),
                "hotspot": hotspots[0] if hotspots else None,
                "lead_story": flagged[0] if flagged else None,
            }
        )

    return {
        "hours": HOURS,
        "period_start": result.get("period_start"),
        "period_end": result.get("period_end"),
        "stories_analyzed": len(result["stories"]),
        "tweets_analyzed": len(result["tweets"]),
        "watchlist": result.get("watchlist") or [],
        "top_story_categories": Counter(result["news_category_counter"]).most_common(6),
        "top_story_severities": Counter(result["news_severity_counter"]).most_common(6),
        "top_tweet_categories": Counter(result["tweet_category_counter"]).most_common(6),
        "top_sources": Counter(result["source_counter"]).most_common(12),
        "top_accounts": Counter(result["account_counter"]).most_common(12),
        "immediate_watch": immediate_watch[:6],
        "current_national_summary": result["brief_payload"].get("national_summary"),
        "current_key_judgment": result["brief_payload"].get("key_judgment"),
        "top_stories": choose_top_stories(result["stories"]),
        "top_tweets": choose_top_tweets(result["tweets"]),
    }


def codex_prompt(context: dict[str, Any]) -> str:
    context_json = json.dumps(context, ensure_ascii=False, indent=2)
    return f"""
Produce only a JSON object that matches the provided schema.

Task:
- Rewrite `national_summary` and `key_judgment` for NepalOSINT.
- Use only the evidence in the context JSON below.
- This is an operational intelligence brief for a live dashboard, not a news article.
- Do not execute shell commands, do not inspect files, and do not use tools. Respond directly from the supplied JSON only.

Writing rules:
- Do not say "logged", "captured", "window used", "inputs used", or similar process language.
- Do not mention Codex, AI, LLM, API, automation, or the generation method.
- Do not fabricate facts beyond the context file.
- Prioritize Nepal-located, Nepal-governance, Nepal public-safety, and Nepal service-delivery developments. Treat foreign stories as secondary unless they clearly alter Nepal's operating picture.
- Keep the prose event-led, not metric-led. Avoid opening with raw story counts unless the count itself is analytically necessary.
- National summary should be detailed and analytic, ideally 120-190 words, one paragraph.
- Key judgment should be tighter and executive, ideally 80-140 words, one paragraph.
- Keep the tone confident, sober, and analyst-grade.
- The summary should explain the national picture, the main provincial pressure points, and what is driving the operating environment.
- The key judgment should identify the center of gravity, why it matters, and the main operational risk.

Context JSON:
```json
{context_json}
```
""".strip()


def run_codex(context: dict[str, Any], output_file: Path) -> dict[str, str]:
    if not CODEX_BIN.exists():
        raise FileNotFoundError(f"Codex binary not found at {CODEX_BIN}")

    cmd = [
        str(CODEX_BIN),
        "exec",
        "-m",
        MODEL,
        "-s",
        "read-only",
        "-C",
        "/tmp",
        "--skip-git-repo-check",
        "--ephemeral",
        "--output-schema",
        str(SCHEMA_FILE),
        "-o",
        str(output_file),
        codex_prompt(context),
    ]
    subprocess.run(cmd, check=True)
    return json.loads(output_file.read_text())


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def render_markdown(brief_payload: dict[str, Any], province_payload: dict[str, Any], hours: int) -> str:
    immediate_watch = []
    for sitrep in brief_payload.get("province_sitreps", []):
        stories = sitrep.get("flagged_stories") or []
        if stories:
            lead = stories[0]
            immediate_watch.append(
                f"- {sitrep['province_name']}: {lead.get('headline') or lead.get('title')} ({lead.get('source_name')})"
            )

    lines = [
        f"# NepalOSINT {hours}-Hour National Assessment and Provincial Monitor",
        "",
        "## National Assessment",
        "",
        brief_payload["national_summary"],
        "",
        "## Key Findings",
        "",
        brief_payload["key_judgment"],
        "",
        "## Immediate Watch",
    ]
    lines.extend(immediate_watch or ["- No immediate provincial spike exceeded the watch threshold in this cycle."])
    lines.extend(["", "## Provincial Monitor", ""])
    for province in province_payload.get("provinces", []):
        lines.extend(
            [
                f"### {province['province_name']}",
                province["summary"],
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    ensure_dirs()

    with LOCK_FILE.open("w") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another codex brief cycle is already running.")
            return 0

        generator = BriefGenerator()
        result = generator.generate(HOURS, API_ROOT.removesuffix("/api/v1"))

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = RUNS_DIR / timestamp
        run_dir.mkdir(parents=True, exist_ok=True)

        context = build_context(result)
        context_file = run_dir / "codex_context.json"
        codex_output_file = run_dir / "codex_output.json"
        save_json(context_file, context)

        codex_result = run_codex(context, codex_output_file)

        brief_payload = result["brief_payload"]
        brief_payload["national_summary"] = codex_result["national_summary"].strip()
        brief_payload["key_judgment"] = codex_result["key_judgment"].strip()
        brief_payload["national_analysis"]["source"] = f"codex_gpt52_{HOURS}h"
        brief_payload["national_analysis"]["method"] = "deterministic_exports_plus_codex_summary"

        province_payload = result["province_payload"]
        markdown = render_markdown(brief_payload, province_payload, HOURS)

        token = login()
        brief_response = post_payload("/briefs/ingest", brief_payload, token)
        province_response = post_payload("/province-anomalies/ingest", province_payload, token)

        markdown_file = run_dir / f"national_provincial_brief_{HOURS}h.md"
        markdown_file.write_text(markdown)
        save_json(run_dir / "brief_ingest_payload.json", brief_payload)
        save_json(run_dir / "province_anomalies_ingest_payload.json", province_payload)
        save_json(run_dir / "brief_response.json", brief_response)
        save_json(run_dir / "province_response.json", province_response)

        save_json(LATEST_DIR / "codex_context.json", context)
        save_json(LATEST_DIR / "codex_output.json", codex_result)
        save_json(LATEST_DIR / "brief_ingest_payload.json", brief_payload)
        save_json(LATEST_DIR / "province_anomalies_ingest_payload.json", province_payload)
        save_json(LATEST_DIR / "brief_response.json", brief_response)
        save_json(LATEST_DIR / "province_response.json", province_response)
        (LATEST_DIR / f"national_provincial_brief_{HOURS}h.md").write_text(markdown)
        (LATEST_DIR / "last_run.txt").write_text(timestamp)

        print(
            json.dumps(
                {
                    "status": "ok",
                    "timestamp": timestamp,
                    "model": MODEL,
                    "hours": HOURS,
                    "stories": len(result["stories"]),
                    "tweets": len(result["tweets"]),
                    "watchlist": result.get("watchlist") or [],
                    "brief_run": brief_response.get("run_number"),
                    "province_run_id": province_response.get("run_id"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        detail = (exc.stdout or "") + (exc.stderr or "")
        print(f"HTTP/subprocess error: {detail}", file=sys.stderr)
        raise
