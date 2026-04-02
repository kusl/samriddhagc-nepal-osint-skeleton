#!/usr/bin/env python3
"""Run local agents via VPS API (Bholi-pattern, no SSH tunnels).

Architecture:
  1. Authenticate with VPS API (JWT)
  2. GET /stories/export + /twitter/export to fetch recent data
  3. Run Claude analysis locally via `claude` CLI (Max subscription)
  4. POST /briefs/ingest or /province-anomalies/ingest with results

No SSH tunnels, no direct DB access. Pure HTTPS + JWT.

Prerequisites:
  - claude CLI installed and authenticated (Max subscription)
  - Set OSINT_PASSWORD env var

Usage:
  OSINT_PASSWORD=devpassword123 python run_local_api.py analyst
  OSINT_PASSWORD=devpassword123 python run_local_api.py analyst --hours 6
  OSINT_PASSWORD=devpassword123 python run_local_api.py province
  OSINT_PASSWORD=devpassword123 python run_local_api.py province --hours 6
"""
import asyncio
import json
import logging
import os
import re
import shutil
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

PROVINCE_MAP = {
    "Koshi": 1, "Madhesh": 2, "Bagmati": 3, "Gandaki": 4,
    "Lumbini": 5, "Karnali": 6, "Sudurpashchim": 7, "National": 0,
}

# International keywords — skip these for fact-checking
INTL_KEYWORDS = {
    "iran", "khamenei", "trump", "biden", "ukraine", "russia", "putin",
    "gaza", "israel", "hamas", "china", "xi jinping", "modi",
    "pakistan", "afghanistan", "taliban", "myanmar",
    "pentagon", "white house", "kremlin", "beijing",
}


class OSINTClient:
    """HTTP client for Nepal OSINT VPS API with JWT auth."""

    def __init__(self, base_url: str = API_URL):
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=60.0,
            follow_redirects=True,
        )

    async def login(self, email: str, password: str) -> dict:
        resp = await self._client.post("/auth/login", json={
            "email": email,
            "password": password,
        })
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        logger.info("Authenticated as %s (role: %s)",
                     data["user"]["username"], data["user"]["role"])
        return data

    @property
    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise RuntimeError("Not logged in")
        return {"Authorization": f"Bearer {self._token}"}

    async def export_stories(self, hours: int = 4) -> list[dict]:
        resp = await self._client.get(
            "/stories/export",
            params={"hours": hours, "limit": 500},
            headers=self._headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("stories", [])

    async def export_stories_deduplicated(
        self, hours: int = 4, limit: int = 200, similarity_threshold: float = 0.85
    ) -> dict:
        """Fetch stories pre-deduplicated by embedding similarity."""
        resp = await self._client.get(
            "/stories/export-deduplicated",
            params={
                "hours": hours,
                "limit": limit,
                "similarity_threshold": similarity_threshold,
            },
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def export_tweets(self, hours: int = 6) -> list[dict]:
        resp = await self._client.get(
            "/twitter/export",
            params={"hours": hours, "limit": 500},
            headers=self._headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("tweets", [])

    async def get_latest_brief(self) -> dict | None:
        resp = await self._client.get("/briefs/latest", headers=self._headers)
        if resp.status_code == 200:
            return resp.json()
        return None

    async def ingest_brief(self, brief_data: dict) -> dict:
        resp = await self._client.post(
            "/briefs/ingest",
            json=brief_data,
            headers=self._headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def ingest_province_anomalies(self, data: dict) -> dict:
        resp = await self._client.post(
            "/province-anomalies/ingest",
            json=data,
            headers=self._headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def ingest_tweets(self, tweets, source_query: str = "") -> dict:
        """POST scraped tweets to /twitter/ingest endpoint.

        Args:
            tweets: List of ScrapedTweet objects from NitterScraper.
            source_query: Source tag like 'nitter:username' or 'nitter:#tag'.

        Returns:
            Dict with received, created, skipped, classified, errors counts.
        """
        payload = {
            "tweets": [
                {
                    "tweet_id": t.tweet_id,
                    "author_username": t.author_username,
                    "author_name": t.author_name,
                    "text": t.text,
                    "language": t.language,
                    "tweeted_at": t.tweeted_at.isoformat() if t.tweeted_at else None,
                    "is_retweet": t.is_retweet,
                    "is_reply": t.is_reply,
                    "is_quote": t.is_quote,
                    "retweet_count": t.retweet_count,
                    "reply_count": t.reply_count,
                    "like_count": t.like_count,
                    "quote_count": t.quote_count,
                    "hashtags": t.hashtags,
                    "mentions": t.mentions,
                    "urls": t.urls,
                    "media_urls": t.media_urls,
                    "source_query": source_query,
                }
                for t in tweets
            ]
        }
        resp = await self._client.post(
            "/twitter/ingest",
            json=payload,
            headers=self._headers,
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def ingest_tactical(self, enrichments: list[dict]) -> dict:
        """POST tactical enrichment results to /tactical/ingest endpoint."""
        resp = await self._client.post(
            "/tactical/ingest",
            json={"enrichments": enrichments},
            headers=self._headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_cluster_timeline(self, hours: int = 72, limit: int = 15, min_stories: int = 3) -> list[dict]:
        """GET /analytics/cluster-timeline for developing stories."""
        resp = await self._client.get(
            "/analytics/cluster-timeline",
            params={"hours": hours, "limit": limit, "min_stories": min_stories},
            headers=self._headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def bulk_update_blufs(self, items: list[dict]) -> dict:
        """POST /analysis/clusters/bulk-bluf to update cluster BLUFs."""
        resp = await self._client.post(
            "/analysis/clusters/bulk-bluf",
            json={"items": items},
            headers=self._headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()


async def call_claude(
    prompt: str,
    model: str = "sonnet",
    timeout: int = 300,
    max_turns: int = 1,
    allow_web_search: bool = False,
    allowed_tools: list[str] | None = None,
) -> str:
    """Call Claude via CLI subprocess (Max subscription)."""
    model_map = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
    }
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--output-format", "text",
        "--model", model_map.get(model, model),
        "--max-turns", str(max_turns),
    ]
    # Support both legacy allow_web_search flag and new allowed_tools list
    tools = list(allowed_tools) if allowed_tools else []
    if allow_web_search and "WebSearch" not in tools:
        tools.append("WebSearch")
    if tools:
        cmd.extend(["--allowedTools", ",".join(tools)])
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
        out = stdout.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Claude CLI failed (exit {proc.returncode}): stderr={err} stdout={out}")

    result = stdout.decode("utf-8", errors="replace").strip()
    if not result:
        raise RuntimeError("Claude CLI returned empty output")
    return result


def extract_json(raw: str) -> dict:
    match = re.search(r"```(?:json)?\s*\n(.*?)```", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError(f"No JSON found: {raw[:300]}")


def is_international(headline: str) -> bool:
    h = headline.lower()
    if "nepal" in h or "नेपाल" in h:
        return False
    return any(kw in h for kw in INTL_KEYWORDS)


async def run_analyst(hours: int = 4):
    """Full analyst agent cycle via API."""
    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch stories (deduplicated by embedding similarity)
        logger.info("Fetching deduplicated stories (last %dh)...", hours)
        try:
            dedup_data = await client.export_stories_deduplicated(
                hours=hours, limit=500, similarity_threshold=0.85
            )
            stories = dedup_data.get("stories", [])
            total_before = dedup_data.get("total_before_dedup", len(stories))
            dedup_ratio = dedup_data.get("dedup_ratio", 0)
            logger.info(
                "Got %d stories (was %d before dedup, %.0f%% reduction)",
                len(stories), total_before, dedup_ratio * 100,
            )
        except Exception as exc:
            logger.warning("Dedup endpoint failed (%s), falling back to normal export", exc)
            stories = await client.export_stories(hours=hours)
            logger.info("Got %d stories from VPS API (no dedup)", len(stories))

        if len(stories) < 5:
            logger.info("Not enough stories (%d). Skipping.", len(stories))
            return

        # Get previous brief for trend
        prev = await client.get_latest_brief()
        prev_text = ""
        if prev:
            prev_text = (
                f"Previous run #{prev.get('run_number', '?')}: "
                f"{prev.get('national_summary', 'N/A')}\n"
                f"Trend: {prev.get('trend_vs_previous', 'N/A')}"
            )

        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(hours=hours)

        # 2. Group by province
        provinces: dict[str, list] = {}
        for s in stories:
            provs = s.get("provinces") or ["National"]
            for p in provs:
                provinces.setdefault(p, []).append(s)

        # 3. Analyze each province
        sitreps = []
        # Fact-checking is handled by dedicated fact-check agent, not the analyst
        claude_calls = 0
        t0 = time.monotonic()

        for prov_name, prov_stories in provinces.items():
            if len(prov_stories) < 3:
                continue

            # Format stories compactly (less tokens)
            # Deduplicated stories include cluster_size and duplicate_sources
            stories_text = "\n".join(
                f"- [{s.get('category','?')}] {s.get('title','')} "
                f"({', '.join(s['duplicate_sources']) if s.get('duplicate_sources') else s.get('source_name','')}) "
                f"id:{s.get('id','')}"
                + (f" [reported by {s['cluster_size']} sources]" if s.get('cluster_size', 1) > 1 else "")
                + f"\n  {(s.get('ai_summary') or {}).get('haiku_summary', '')[:150]}"
                for s in prov_stories[:80]
            )

            prompt = f"""You are NARADA, a senior intelligence analyst producing professional briefings for journalists, researchers, and civic leaders.

# National Analysis: {prov_name}
Period: {period_start.strftime('%Y-%m-%d %H:%M')} to {period_end.strftime('%Y-%m-%d %H:%M')} UTC

## Stories ({len(prov_stories)} total, {min(len(prov_stories), 80)} shown)
{stories_text}

## Previous Brief
{prev_text or "No previous brief available."}

## WRITING STYLE
- Write like a Reuters or AP wire analyst — professional, concise, authoritative.
- Attribute claims to source outlets by NAME (e.g. "according to Kathmandu Post", "My Republica reports").
- NEVER include raw story IDs (like "id:56c1c2dc") in the text — these are for your reference only.
- Use specific numbers, district names, and named actors. No vague language.
- Each domain section: 2-3 crisp sentences. Lead with the most important fact.
- BLUF should read like a news flash — what would a decision-maker need to know if they read nothing else?

Produce a status report as JSON:
{{
  "bluf": "2-3 sentence executive summary. Lead with the single most consequential development. Include numbers and locations. No story IDs.",
  "security": "Public safety: incidents, protests, crime, arrests. Cite source names, not IDs. 2-3 sentences max.",
  "political": "Political dynamics: party activity, governance, coalition shifts. Name actors and parties. 2-3 sentences.",
  "economic": "Markets, trade, fiscal data. Include figures. 2-3 sentences.",
  "disaster": "Natural disasters, fires, health emergencies. Locations and casualty figures. 2-3 sentences.",
  "election": "Electoral activity if applicable. Constituencies, logistics, turnout signals. 2-3 sentences.",
  "threat_level": "critical|elevated|guarded|low",
  "threat_trajectory": "escalating|stable|de-escalating",
  "trajectory_reasoning": "1 sentence: WHY the trajectory changed or stayed the same vs previous brief",
  "hotspots": [
    {{
      "district": "specific district name",
      "severity": "high|medium|low",
      "description": "Concise situation description with numbers — no story IDs",
      "confidence": "HIGH|MEDIUM|LOW"
    }}
  ],
  "key_developments": [
    "Development #1 (1 sentence, specific, no IDs)",
    "Development #2",
    "Development #3"
  ]
}}

IMPORTANT: Do NOT include story IDs anywhere in the output text. Do NOT do any fact-checking.
Respond ONLY with raw JSON."""

            logger.info("  Analyzing %s (%d stories)...", prov_name, len(prov_stories))
            raw = await call_claude(prompt, model="sonnet")
            claude_calls += 1

            try:
                result = extract_json(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("  Failed to parse %s: %s", prov_name, exc)
                continue

            prov_id = PROVINCE_MAP.get(prov_name, 0)
            sitreps.append({
                "province_id": prov_id,
                "province_name": prov_name,
                "bluf": result.get("bluf"),
                "security": result.get("security"),
                "political": result.get("political"),
                "economic": result.get("economic"),
                "disaster": result.get("disaster"),
                "election": result.get("election"),
                "threat_level": result.get("threat_level", "low"),
                "threat_trajectory": result.get("threat_trajectory", "stable"),
                "hotspots": result.get("hotspots", []),
                "flagged_stories": [],
                "key_developments": result.get("key_developments", []),
                "story_count": len(prov_stories),
            })

            logger.info(
                "  → %s: threat=%s, trajectory=%s",
                prov_name, result.get("threat_level"),
                result.get("threat_trajectory"),
            )

        if not sitreps:
            logger.info("No provinces had enough data.")
            return

        # 4. National synthesis
        sitreps_text = "\n".join(
            f"### {s['province_name']} (threat: {s['threat_level']}, trajectory: {s['threat_trajectory']})\n"
            f"BLUF: {s['bluf']}\n"
            f"Security: {s.get('security', 'N/A')}\n"
            f"Political: {s.get('political', 'N/A')}\n"
            f"Economic: {s.get('economic', 'N/A')}\n"
            f"Disaster: {s.get('disaster', 'N/A')}\n"
            + (f"Key Developments: {'; '.join(s.get('key_developments', []))}\n" if s.get('key_developments') else "")
            for s in sitreps
        )

        synth_prompt = f"""You are NARADA, Nepal's premier intelligence synthesis analyst writing for senior decision-makers, journalists, and civic researchers.

# National Overview Synthesis
Period: {period_start.strftime('%Y-%m-%d %H:%M')} to {period_end.strftime('%Y-%m-%d %H:%M')} UTC
Stories analyzed: {len(stories)} across {len(sitreps)} provinces

## Province Reports
{sitreps_text}

## Previous Brief
{prev_text or "No previous brief."}

## WRITING STYLE
- Write like a Reuters/AP intelligence desk — authoritative, concise, no filler.
- NEVER include raw story IDs. Attribute to source outlets by name when needed.
- The national_summary is the MOST IMPORTANT output — it goes directly to decision-makers.
- The key_judgment must be an ANALYTICAL FINDING, not a summary — connect dots across provinces to surface insights that no individual report reveals.
- Be specific with numbers, locations, and named actors.

Respond with JSON:
{{
  "national_summary": "3-5 sentence national BLUF. Lead with the most consequential development. No story IDs. Write like an AP wire flash for journalists.",
  "key_judgment": "1-2 sentence analytical finding with confidence level (HIGH/MEDIUM/LOW). This must be a JUDGMENT that connects patterns across provinces — not a restatement of individual reports.",
  "trend_vs_previous": "escalating|stable|de-escalating",
  "trend_reasoning": "1 sentence explaining the trend compared to previous brief",
  "hotspots": [
    {{
      "province": "Province name",
      "district": "Specific district",
      "severity": "critical|high|medium|low",
      "description": "Concise situation with numbers — no story IDs",
      "confidence": "HIGH|MEDIUM|LOW"
    }}
  ],
  "national_risks": [
    "Risk #1: specific emerging risk with geographic scope",
    "Risk #2: specific risk"
  ]
}}

Respond ONLY with raw JSON."""

        logger.info("  Synthesizing national brief...")
        raw = await call_claude(synth_prompt, model="sonnet")
        claude_calls += 1

        try:
            national = extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            national = {
                "national_summary": "Synthesis failed.",
                "key_judgment": "See individual SITREPs.",
                "trend_vs_previous": "stable",
                "hotspots": [],
            }

        duration = time.monotonic() - t0

        # 5. POST to VPS (no fact-check flags — handled by dedicated fact-check system)
        brief_payload = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "national_summary": national.get("national_summary"),
            "national_analysis": national,
            "hotspots": national.get("hotspots", []),
            "trend_vs_previous": national.get("trend_vs_previous", "stable"),
            "key_judgment": national.get("key_judgment"),
            "stories_analyzed": len(stories),
            "clusters_analyzed": 0,
            "claude_calls": claude_calls,
            "duration_seconds": duration,
            "province_sitreps": sitreps,
            "fake_news_flags": [],
        }

        logger.info("POSTing brief to VPS API...")
        result = await client.ingest_brief(brief_payload)
        logger.info(
            "=== Brief #%s ingested ===\n"
            "  Sitreps: %d\n"
            "  Claude calls: %d, Duration: %.1fs\n"
            "  Trend: %s",
            result.get("run_number"), len(sitreps),
            claude_calls, duration,
            national.get("trend_vs_previous"),
        )

    finally:
        await client.close()


# ── Province Anomaly Agent ──

# Import province keyword data for classification
from collections import defaultdict
from app.data.nepal_districts import NEPAL_PROVINCES, NEPAL_DISTRICTS

# Build keyword → province_id map (same logic as data_collector.py)
_KEYWORD_TO_PROVINCE: dict[str, int] = {}
for _prov in NEPAL_PROVINCES:
    _pid = _prov["id"]
    _KEYWORD_TO_PROVINCE[_prov["name_en"].lower()] = _pid
    for _alias in _prov.get("aliases", []):
        _KEYWORD_TO_PROVINCE[_alias.lower()] = _pid
for _dist in NEPAL_DISTRICTS:
    _pid = _dist["province_id"]
    _KEYWORD_TO_PROVINCE[_dist["name_en"].lower()] = _pid
    _KEYWORD_TO_PROVINCE[_dist["headquarters"].lower()] = _pid
    for _alias in _dist.get("aliases", []):
        _low = _alias.lower()
        if len(_low) >= 3:
            _KEYWORD_TO_PROVINCE[_low] = _pid
_SORTED_KEYWORDS = sorted(_KEYWORD_TO_PROVINCE.keys(), key=len, reverse=True)
PROVINCE_NAMES = {p["id"]: p["name_en"] for p in NEPAL_PROVINCES}


def classify_province(text: str) -> int | None:
    """Classify text to a province_id via keyword matching."""
    if not text:
        return None
    text_lower = text.lower()
    hits: dict[int, int] = defaultdict(int)
    for keyword in _SORTED_KEYWORDS:
        if keyword in text_lower:
            hits[_KEYWORD_TO_PROVINCE[keyword]] += 1
    if not hits:
        return None
    return max(hits, key=hits.get)


async def run_province(hours: int = 6):
    """Province Anomaly Agent cycle via API.

    Uses district→province mapping from story_features to classify stories.
    Single Claude CLI call (Sonnet 4.6) for all 7 provinces.
    """
    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch stories (deduplicated) + tweets
        logger.info("Fetching stories and tweets (last %dh)...", hours)
        try:
            dedup_data = await client.export_stories_deduplicated(
                hours=hours, limit=500, similarity_threshold=0.85
            )
            stories = dedup_data.get("stories", [])
            logger.info(
                "Got %d stories (was %d before dedup)",
                len(stories), dedup_data.get("total_before_dedup", len(stories)),
            )
        except Exception as exc:
            logger.warning("Dedup failed (%s), falling back to normal export", exc)
            stories = await client.export_stories(hours=hours)
        tweets = await client.export_tweets(hours=hours)
        logger.info("Got %d stories, %d tweets total", len(stories), len(tweets))

        # 2. Build district→province_id lookup
        district_to_province: dict[str, int] = {}
        for d in NEPAL_DISTRICTS:
            district_to_province[d["name_en"].lower()] = d["province_id"]
            district_to_province[d.get("name_ne", "").lower()] = d["province_id"]
            district_to_province[d["headquarters"].lower()] = d["province_id"]
            for alias in d.get("aliases", []):
                district_to_province[alias.lower()] = d["province_id"]

        # 3. Classify stories to provinces
        provinces: dict[int, dict] = {
            pid: {"name": name, "stories": [], "tweets": [], "districts_seen": set()}
            for pid, name in PROVINCE_NAMES.items()
        }

        stories_classified = 0
        national_stories = []
        for s in stories:
            assigned = False
            title = s.get("title", "")
            snippet = (s.get("ai_summary") or {}).get("haiku_summary", "")[:200]

            # Primary: use districts from story_features
            districts = s.get("districts") or []
            for dist in districts:
                dist_lower = dist.lower()
                pid = district_to_province.get(dist_lower)
                if pid and pid in provinces:
                    provinces[pid]["stories"].append({
                        "source": s.get("source_name", "Unknown"),
                        "title": title,
                        "snippet": snippet,
                        "district": dist,
                        "category": s.get("category", ""),
                        "severity": s.get("severity", ""),
                    })
                    provinces[pid]["districts_seen"].add(dist)
                    stories_classified += 1
                    assigned = True
                    break  # One province per story

            # Fallback: keyword classification on title + summary
            if not assigned:
                search_text = f"{title} {snippet}"
                pid = classify_province(search_text)
                if pid and pid in provinces:
                    provinces[pid]["stories"].append({
                        "source": s.get("source_name", "Unknown"),
                        "title": title,
                        "snippet": snippet,
                        "district": "",
                        "category": s.get("category", ""),
                        "severity": s.get("severity", ""),
                    })
                    stories_classified += 1
                    assigned = True

            if not assigned:
                national_stories.append({
                    "source": s.get("source_name", "Unknown"),
                    "title": title,
                    "snippet": snippet,
                })

        tweets_classified = 0
        for t in tweets:
            text = t.get("text", "")
            pid = classify_province(text)
            if pid and pid in provinces:
                provinces[pid]["tweets"].append({
                    "author": f"@{t.get('author_username', 'unknown')}",
                    "text": text[:200],
                })
                tweets_classified += 1

        logger.info(
            "Province classification: %d/%d stories, %d/%d tweets classified (%d national)",
            stories_classified, len(stories), tweets_classified, len(tweets), len(national_stories),
        )

        # 3. Build structured prompt — district-level detail per province
        sections = []
        for pid in sorted(provinces.keys()):
            ctx = provinces[pid]
            n_stories = len(ctx["stories"])
            n_tweets = len(ctx["tweets"])
            districts = sorted(ctx["districts_seen"])

            section = f"## Province {pid}: {ctx['name']}"
            if districts:
                section += f" (Districts: {', '.join(districts)})"
            section += f"\nData: {n_stories} stories, {n_tweets} tweets\n"

            if ctx["stories"]:
                # Group by district for clarity
                by_district: dict[str, list] = defaultdict(list)
                for s in ctx["stories"][:50]:
                    key = s.get("district") or "General"
                    by_district[key].append(s)

                for dist, dist_stories in by_district.items():
                    section += f"\n[{dist}]\n"
                    for s in dist_stories[:10]:
                        cat = f"({s['category']})" if s.get("category") else ""
                        sev = f"[{s['severity']}]" if s.get("severity") else ""
                        section += f"  - {sev}{cat} {s['title']}"
                        if s.get("snippet"):
                            section += f"\n    {s['snippet'][:150]}"
                        section += f" ({s['source']})\n"
            else:
                section += "\nNo stories.\n"

            if ctx["tweets"]:
                section += "\nTweets:\n"
                for t in ctx["tweets"][:8]:
                    section += f"  - {t['author']}: {t['text'][:150]}\n"

            sections.append(section)

        # National context
        national_section = ""
        if national_stories[:20]:
            national_section = f"\n## National/Cross-Province ({len(national_stories)} stories)\n"
            for s in national_stories[:20]:
                national_section += f"  - {s['title']} ({s['source']})\n"

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        prompt = f"""You are NARADA, a Nepal provincial intelligence analyst. Date: {now_str}. Window: last {hours} hours.

Assess each of Nepal's 7 provinces. You have real district-level news data below.

For EACH province, produce:
- threat_level: LOW | GUARDED | ELEVATED | CRITICAL
- threat_trajectory: ESCALATING | STABLE | DE-ESCALATING
- summary: 2-3 precise sentences citing specific incidents, districts, and sources
- security: security assessment (incidents, protests, crime) or null
- political: political dynamics or null
- economic: economic issues or null
- anomalies: [{{type, description, severity, district}}] — only for real events

Rules:
- ALL 7 provinces required. No data = LOW/STABLE with note about coverage gap.
- Cite specific districts and events from the data. No vague statements.
- Cross-reference National section for context affecting multiple provinces.
- Be precise: "tear gas deployed at Gaushala bazar" not "security incidents reported"

Return raw JSON only:
{{"provinces": [{{"province_id": 1, "province_name": "Koshi", "threat_level": "LOW", "threat_trajectory": "STABLE", "summary": "...", "security": null, "political": null, "economic": null, "anomalies": []}}]}}

=== PROVINCIAL DATA ===

""" + "\n".join(sections) + national_section

        # 4. Call Claude locally (single call, no web search — data is already rich)
        logger.info("Calling Claude for province analysis...")
        t0 = time.monotonic()
        raw = await call_claude(
            prompt, model="sonnet", timeout=300,
            max_turns=1, allow_web_search=False,
        )
        duration = time.monotonic() - t0

        try:
            result = extract_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse Claude response: %s", exc)
            return

        parsed_provinces = result.get("provinces", [])
        logger.info("Got %d province assessments (%.1fs)", len(parsed_provinces), duration)

        # 5. Build ingest payload
        province_data = []
        for p in parsed_provinces:
            pid = p.get("province_id", 0)
            ctx = provinces.get(pid, {"stories": [], "tweets": []})
            province_data.append({
                "province_id": pid,
                "province_name": p.get("province_name", PROVINCE_NAMES.get(pid, f"Province {pid}")),
                "threat_level": p.get("threat_level", "LOW"),
                "threat_trajectory": p.get("threat_trajectory", "STABLE"),
                "summary": p.get("summary", ""),
                "political": p.get("political"),
                "economic": p.get("economic"),
                "security": p.get("security"),
                "anomalies": p.get("anomalies", []),
                "story_count": len(ctx.get("stories", [])),
                "tweet_count": len(ctx.get("tweets", [])),
                "key_sources": [],
            })

        payload = {
            "stories_analyzed": len(stories),
            "tweets_analyzed": len(tweets),
            "provinces": province_data,
        }

        # 6. POST to VPS
        logger.info("POSTing province anomalies to VPS API...")
        result = await client.ingest_province_anomalies(payload)
        logger.info(
            "=== Province anomaly run ingested ===\n"
            "  Provinces: %d, Stories classified: %d/%d, Tweets: %d/%d\n"
            "  Duration: %.1fs",
            len(province_data),
            stories_classified, len(stories),
            tweets_classified, len(tweets),
            duration,
        )

    finally:
        await client.close()


async def run_nitter():
    """Scrape Twitter via Nitter locally, POST to VPS API.

    Nitter instances block cloud provider IPs (AWS Lightsail),
    so scraping must happen locally. Results are sent to VPS via
    the /twitter/ingest API endpoint.
    """
    from pathlib import Path
    import yaml
    from app.ingestion.nitter_scraper import NitterInstanceManager, NitterScraper

    # Load config
    sources_path = Path(__file__).resolve().parent / "config" / "sources.yaml"
    with open(sources_path) as f:
        cfg = yaml.safe_load(f)

    nitter_cfg = cfg.get("nitter_config", {})
    accounts = cfg.get("nitter_accounts", [])
    hashtags = cfg.get("nitter_hashtags", [])
    text_searches = cfg.get("nitter_searches", [])

    instances = nitter_cfg.get("instances", [{"url": "https://nitter.poast.org", "priority": 1}])
    instance_mgr = NitterInstanceManager(instances)

    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        scraper = NitterScraper(
            instance_manager=instance_mgr,
            request_timeout=nitter_cfg.get("request_timeout", 30),
            delay_between_requests=nitter_cfg.get("delay_between_requests", 4.0),
        )

        total_scraped = 0
        total_new = 0
        total_skipped = 0
        errors = []
        t0 = time.monotonic()

        BATCH_SIZE = 100  # POST in batches to avoid timeout

        async with scraper:
            # ── Scrape accounts ──
            logger.info("Scraping %d account timelines...", len(accounts))
            for account in accounts:
                username = account["username"]
                source_query = f"nitter:{username}"

                try:
                    result = await scraper.scrape_user_timeline(username)
                    if not result.success:
                        errors.append(f"@{username}: {result.error}")
                        continue

                    total_scraped += len(result.tweets)

                    if result.tweets:
                        # Batch POST
                        for i in range(0, len(result.tweets), BATCH_SIZE):
                            batch = result.tweets[i : i + BATCH_SIZE]
                            ingest = await client.ingest_tweets(batch, source_query=source_query)
                            total_new += ingest.get("created", 0)
                            total_skipped += ingest.get("skipped", 0)

                        logger.info(
                            "  @%s: %d scraped via %s",
                            username, len(result.tweets), result.instance_used,
                        )

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception("Error scraping @%s: %s", username, e)
                    errors.append(f"@{username}: {e}")

            # ── Scrape hashtags ──
            logger.info("Scraping %d hashtag searches...", len(hashtags))
            for hashtag_cfg in hashtags:
                tag = hashtag_cfg["tag"]
                source_query = f"nitter:#{tag}"

                try:
                    result = await scraper.scrape_hashtag_search(tag)
                    if not result.success:
                        errors.append(f"#{tag}: {result.error}")
                        continue

                    total_scraped += len(result.tweets)

                    if result.tweets:
                        for i in range(0, len(result.tweets), BATCH_SIZE):
                            batch = result.tweets[i : i + BATCH_SIZE]
                            ingest = await client.ingest_tweets(batch, source_query=source_query)
                            total_new += ingest.get("created", 0)
                            total_skipped += ingest.get("skipped", 0)

                        logger.info(
                            "  #%s: %d scraped via %s",
                            tag, len(result.tweets), result.instance_used,
                        )

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception("Error scraping #%s: %s", tag, e)
                    errors.append(f"#{tag}: {e}")

            # ── Scrape text searches ──
            logger.info("Scraping %d text searches...", len(text_searches))
            for search_cfg in text_searches:
                query = search_cfg["query"]
                source_query = f"nitter:search:{query}"

                try:
                    result = await scraper.scrape_text_search(query)
                    if not result.success:
                        errors.append(f"search '{query}': {result.error}")
                        continue

                    total_scraped += len(result.tweets)

                    if result.tweets:
                        for i in range(0, len(result.tweets), BATCH_SIZE):
                            batch = result.tweets[i : i + BATCH_SIZE]
                            ingest = await client.ingest_tweets(batch, source_query=source_query)
                            total_new += ingest.get("created", 0)
                            total_skipped += ingest.get("skipped", 0)

                        logger.info(
                            "  search '%s': %d scraped via %s",
                            query, len(result.tweets), result.instance_used,
                        )

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception("Error scraping search '%s': %s", query, e)
                    errors.append(f"search '{query}': {e}")

        duration = time.monotonic() - t0
        logger.info(
            "=== Nitter scrape complete (%.1fs) ===\n"
            "  Total scraped: %d\n"
            "  New: %d, Skipped: %d\n"
            "  Errors: %d",
            duration, total_scraped, total_new, total_skipped, len(errors),
        )
        if errors:
            for err in errors:
                logger.warning("  Error: %s", err)

    finally:
        await client.close()


async def run_reddit():
    """Scrape Reddit locally via public JSON API, POST to VPS API.

    Reddit's public JSON API works without authentication.
    Results are converted to ScrapedTweet format and sent to VPS via
    the /twitter/ingest API endpoint (shared social media table).
    """
    from pathlib import Path
    import yaml
    from app.ingestion.reddit_scraper import RedditScraper

    # Load config
    sources_path = Path(__file__).resolve().parent / "config" / "sources.yaml"
    with open(sources_path) as f:
        cfg = yaml.safe_load(f)

    reddit_cfg = cfg.get("reddit_config", {})
    subreddits = cfg.get("reddit_subreddits", [])
    searches = cfg.get("reddit_searches", [])

    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        scraper = RedditScraper(
            request_timeout=reddit_cfg.get("request_timeout", 30),
            delay_between_requests=reddit_cfg.get("delay_between_requests", 2.0),
        )

        total_scraped = 0
        total_new = 0
        total_skipped = 0
        errors = []
        seen_post_ids: set = set()  # Global dedup across subreddits
        t0 = time.monotonic()

        BATCH_SIZE = 100

        async with scraper:
            # ── Scrape subreddits ──
            logger.info("Scraping %d subreddit feeds...", len(subreddits))
            for sub_cfg in subreddits:
                subreddit = sub_cfg["subreddit"]
                sort = sub_cfg.get("sort", "new")
                limit = sub_cfg.get("limit", 25)
                source_query = f"reddit:r/{subreddit}"

                try:
                    result = await scraper.scrape_subreddit(
                        subreddit=subreddit,
                        sort=sort,
                        limit=limit,
                    )
                    if not result.success:
                        errors.append(f"r/{subreddit}: {result.error}")
                        continue

                    # Dedup across subreddits (r/Nepal appears twice with different sorts)
                    new_posts = []
                    for post in result.posts:
                        if post.post_id not in seen_post_ids:
                            seen_post_ids.add(post.post_id)
                            new_posts.append(post)

                    total_scraped += len(new_posts)

                    if new_posts:
                        tweets = [
                            RedditScraper.post_to_scraped_tweet(p, source_query)
                            for p in new_posts
                        ]
                        for i in range(0, len(tweets), BATCH_SIZE):
                            batch = tweets[i : i + BATCH_SIZE]
                            ingest = await client.ingest_tweets(batch, source_query=source_query)
                            total_new += ingest.get("created", 0)
                            total_skipped += ingest.get("skipped", 0)

                        logger.info(
                            "  r/%s (%s): %d scraped (%d new after dedup)",
                            subreddit, sort, len(result.posts), len(new_posts),
                        )

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception("Error scraping r/%s: %s", subreddit, e)
                    errors.append(f"r/{subreddit}: {e}")

            # ── Scrape search queries ──
            logger.info("Scraping %d Reddit search queries...", len(searches))
            for search_cfg in searches:
                query = search_cfg["query"]
                source_query = f"reddit:search:{query}"

                try:
                    result = await scraper.scrape_search(
                        query=query,
                        sort="new",
                        limit=25,
                        time_filter="day",
                    )
                    if not result.success:
                        errors.append(f"search '{query}': {result.error}")
                        continue

                    # Dedup against already-seen posts from subreddit scrapes
                    new_posts = []
                    for post in result.posts:
                        if post.post_id not in seen_post_ids:
                            seen_post_ids.add(post.post_id)
                            new_posts.append(post)

                    total_scraped += len(new_posts)

                    if new_posts:
                        tweets = [
                            RedditScraper.post_to_scraped_tweet(p, source_query)
                            for p in new_posts
                        ]
                        for i in range(0, len(tweets), BATCH_SIZE):
                            batch = tweets[i : i + BATCH_SIZE]
                            ingest = await client.ingest_tweets(batch, source_query=source_query)
                            total_new += ingest.get("created", 0)
                            total_skipped += ingest.get("skipped", 0)

                        logger.info(
                            "  search '%s': %d scraped (%d new after dedup)",
                            query, len(result.posts), len(new_posts),
                        )

                    await asyncio.sleep(scraper.delay_between_requests)

                except Exception as e:
                    logger.exception("Error searching Reddit '%s': %s", query, e)
                    errors.append(f"search '{query}': {e}")

        duration = time.monotonic() - t0
        logger.info(
            "=== Reddit scrape complete (%.1fs) ===\n"
            "  Total scraped: %d\n"
            "  New: %d, Skipped: %d\n"
            "  Errors: %d",
            duration, total_scraped, total_new, total_skipped, len(errors),
        )
        if errors:
            for err in errors:
                logger.warning("  Error: %s", err)

    finally:
        await client.close()


async def run_clustering(hours: int = 48):
    """Run Haiku merge locally via Claude CLI (free on Max subscription).

    1. GET /ml/clustering/merge-candidates — unclustered stories by district
    2. For each district batch, call Claude CLI (Haiku) to identify same-event groups
    3. POST /ml/clustering/merge-results — send merge groups back to VPS
    """
    SYSTEM_PROMPT = """You are NARADA, Nepal's premier intelligence clustering analyst. Nepal is in an ELECTION PERIOD — accurate clustering is critical for the live tactical map.

## TASK
Identify news stories covering the SAME real-world event or incident and group them.

## GROUPING RULES — BE AGGRESSIVE ON SAME-EVENT MATCHING
- Group stories about the SAME specific event — including updates, follow-ups, different angles, death toll changes
- CRITICAL: Stories in Nepali and English about the SAME event MUST be grouped (cross-lingual). This is the #1 priority.
- CRITICAL: Stories about the same clash/arrest/deployment with different wording MUST be grouped. Example: "धनगढीमा झडप" and "Clash in Dhangarhi" = SAME EVENT.
- Cities within districts are the SAME location: "Dhangadhi" = "Kailali", "Birgunj" = "Parsa", "Butwal" = "Rupandehi"
- Stories about the same broad TOPIC but DIFFERENT specific events must NOT be grouped (e.g., two separate arrests in different cities)
- Group across existing cluster tags [Cxxxx] if they're about the same event
- Max 10 stories per group. Singletons = omit
- When in doubt about edge cases, GROUP THEM — false negatives (missing a cluster) are worse than false positives

## OUTPUT FORMAT
Raw JSON only:
{
  "groups": [
    {
      "indices": [1, 3, 5],
      "event_type": "disaster|political|security|economic|social|infrastructure|health|judicial|environmental",
      "severity": "critical|high|medium|low",
      "headline": "Synthesized headline (English)",
      "bluf": "1-2 sentence Bottom Line Up Front",
      "development_stage": "breaking|developing|ongoing|resolved",
      "key_updates": ["Most recent development", "Second most recent"],
      "geographic_scope": "local|district|provincial|national|cross-border",
      "cross_lingual": true/false,
      "source_agreement": "unanimous|majority|mixed|contradictory",
      "confidence": 0.0-1.0
    }
  ]
}

If no matches found, output: {"groups":[]}"""

    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch merge candidates
        logger.info("Fetching merge candidates (last %dh)...", hours)
        resp = await client._client.get(
            "/ml/clustering/merge-candidates",
            params={"hours": hours},
            headers=client._headers,
        )
        resp.raise_for_status()
        data = resp.json()
        batches = data["batches"]
        logger.info("Got %d district batches (%d total stories)",
                     len(batches), data["total_stories"])

        if not batches:
            logger.info("No unclustered stories to merge")
            return

        # 2. Process each district via Claude CLI (Haiku)
        merge_results = []
        t0 = time.monotonic()

        for batch in batches:
            district = batch["district"]
            stories = batch["stories"]

            if len(stories) < 2:
                continue

            # Build numbered story list with rich context
            story_lines = []
            idx_to_id = {}
            for i, s in enumerate(stories, 1):
                idx_to_id[i] = s["id"]
                parts = [f"[{i}] ({s.get('source_name', s['source'])})"]
                if s.get("language"):
                    parts.append(f"[{s['language']}]")
                parts.append(s["title"])
                if s.get("cluster_tag"):
                    parts.append(s["cluster_tag"])
                line = " ".join(parts)
                if s.get("summary"):
                    line += f"\n    → {s['summary']}"
                if s.get("published_at"):
                    line += f"\n    @ {s['published_at']}"
                story_lines.append(line)

            user_msg = f"District: {district}\n\n" + "\n\n".join(story_lines)
            prompt = f"{SYSTEM_PROMPT}\n\n{user_msg}"

            try:
                raw = await call_claude(prompt, model="haiku", timeout=90, max_turns=1)

                # Parse groups from response
                groups_data = extract_json('{"groups":' + raw if not raw.strip().startswith('{') else raw)
                raw_groups = groups_data.get("groups", [])

                # Convert index-based groups to UUID-based groups with metadata
                uuid_groups = []
                group_metadata = []
                for group in raw_groups:
                    # Handle both old format (list of ints) and new format (dict with indices)
                    if isinstance(group, dict):
                        indices = group.get("indices", [])
                        meta = {
                            k: v for k, v in group.items()
                            if k != "indices"
                        }
                    elif isinstance(group, list):
                        indices = group
                        meta = {}
                    else:
                        continue

                    if len(indices) < 2:
                        continue
                    uuids = []
                    for idx in indices[:10]:
                        if isinstance(idx, int) and idx in idx_to_id:
                            uuids.append(idx_to_id[idx])
                    if len(uuids) >= 2:
                        uuid_groups.append(uuids)
                        group_metadata.append(meta)

                if uuid_groups:
                    merge_results.append({
                        "district": district,
                        "groups": uuid_groups,
                        "metadata": group_metadata,
                    })
                    logger.info("  %s: %d groups from %d stories",
                                district, len(uuid_groups), len(stories))

            except Exception as e:
                logger.warning("  %s: Claude CLI failed: %s", district, e)

        # 3. POST merge results back to VPS (re-login in case token expired during Claude calls)
        if merge_results:
            logger.info("POSTing %d district merges to VPS...", len(merge_results))
            await client.login(EMAIL, PASSWORD)
            resp = await client._client.post(
                "/ml/clustering/merge-results",
                json={"merges": merge_results},
                headers=client._headers,
                timeout=60.0,
            )
            resp.raise_for_status()
            result = resp.json()
            duration = time.monotonic() - t0
            logger.info(
                "=== Clustering complete (%.1fs) ===\n"
                "  Districts processed: %d\n"
                "  Total merges: %d\n"
                "  Errors: %s",
                duration, result["districts_processed"],
                result["total_merges"], result.get("errors", []),
            )
        else:
            logger.info("No merges needed — all stories already clustered")

    finally:
        await client.close()


async def _factcheck_one(item: dict, prompt_template: str, semaphore: asyncio.Semaphore) -> dict | None:
    """Fact-check a single story. Returns result dict or None on failure."""
    story_id = item["story_id"]
    title = item["title"]
    source = item.get("source_name", "Unknown")
    summary = item.get("summary", "")
    content = item.get("content", "")
    url = item.get("url", "")

    # Pre-check layer (free, <2s)
    try:
        from app.services.factcheck_precheck import run_precheck
        precheck_result = await run_precheck(title, summary)
        if precheck_result:
            logger.info("  [PRECHECK HIT] %s -> %s via %s", title[:60], precheck_result["verdict"], precheck_result.get("precheck_source", "unknown"))
            precheck_result["story_id"] = story_id
            return precheck_result
    except Exception as e:
        logger.warning("Pre-check failed (continuing): %s", e)

    # Build story text — keep it tight to reduce token waste
    story_text = f"# {title}\nSource: {source}\n"
    if url:
        story_text += f"URL: {url}\n"
    if summary:
        story_text += f"\nSummary: {summary}\n"
    if content:
        story_text += f"\nArticle text:\n{content[:8000]}\n"
    if not content and not summary:
        story_text += "\nNo article body — search the web for this article.\n"

    prompt = f"{prompt_template}\n\n---\n\n## STORY TO FACT-CHECK\n{story_text}"

    async with semaphore:
        try:
            logger.info("  Checking: %s (%d requests)", title[:60], item["request_count"])
            raw = await call_claude(
                prompt,
                model="sonnet",
                timeout=300,
                max_turns=4,
                allowed_tools=["WebSearch", "WebFetch"],
            )
            result = extract_json(raw)

            logger.info("    -> %s (%.0f%% confidence)",
                        result.get("verdict"), (result.get("confidence", 0) * 100))
            return {
                "story_id": story_id,
                "verdict": result.get("verdict", "unverifiable"),
                "verdict_summary": result.get("verdict_summary", "Analysis inconclusive"),
                "confidence": result.get("confidence", 0.5),
                "claims_analyzed": result.get("claims_analyzed"),
                "sources_checked": result.get("sources_checked"),
                "key_finding": result.get("key_finding"),
                "context": result.get("context"),
                "model_used": "sonnet",
            }
        except Exception as e:
            logger.warning("  Failed to fact-check %s: %s", story_id[:8], e)
            return None


FACTCHECK_STATEMENT_PROMPT = """You are NARADA, a rigorous fact-checker for Nepal news.

## RULES
- Follow evidence, not assumptions. Political claims need official records.
- If evidence is insufficient, verdict = "unverifiable". Do NOT guess.
- Decompose the statement into atomic factual claims before verifying.
- Each claim must be self-contained (understandable without reading the statement).
- For each claim, search for corroborating or contradicting evidence.
- Record every source you check, including sources that had no relevant info.

## PROCESS
1. Read the statement carefully. Identify ALL verifiable factual claims (not opinions or predictions).
2. For each claim, formulate it as a self-contained statement:
   BAD: "The figure is wrong" (not self-contained)
   GOOD: "Nepal's GDP growth was 7.2% in FY2082 according to NRB" (self-contained)
3. Search for evidence for each claim. Use targeted queries.
4. For each source found, record its URL, a relevant excerpt, and whether it supports or contradicts.
5. Assess each claim independently, then aggregate into an overall verdict.
6. Set confidence based on: source quality, source agreement, and evidence completeness.
   - 0.9+ : Multiple Tier 1 sources (NRB, Election Commission) agree
   - 0.7-0.9 : Credible sources agree, minor gaps
   - 0.5-0.7 : Mixed or limited evidence
   - <0.5 : Mostly unverifiable, use "unverifiable" verdict

## NEPAL-SPECIFIC SOURCES (prefer these)
- Nepal Rastra Bank (nrb.org.np) — monetary/GDP data [Tier 1]
- Election Commission (election.gov.np) — election results [Tier 1]
- NepalFactCheck.org — existing fact-checks [Tier 1]
- Kathmandu Post, Republica, The Himalayan Times — English news [Tier 2]
- Kantipur, Ratopati, Setopati — Nepali news [Tier 2]

## VERDICT SCALE
- "true" — Verified by multiple independent sources
- "mostly_true" — Main claim accurate, minor inaccuracy or missing nuance
- "partially_true" — Mix of accurate and inaccurate elements
- "misleading" — True elements framed to give false impression
- "false" — Core claims contradicted by evidence
- "unverifiable" — Insufficient evidence to determine (this is OK)
- "satire" — Intentionally fictional/satirical

## OUTPUT — respond with ONLY this JSON, nothing else:
{
  "verdict": "true|mostly_true|partially_true|misleading|false|unverifiable|satire",
  "verdict_summary": "2-3 sentences explaining the verdict with specific evidence cited.",
  "confidence": 0.0-1.0,
  "key_finding": "Single most important finding from the fact-check",
  "context": "Important missing context from the original statement (or null)",
  "claims_analyzed": [
    {
      "claim": "Self-contained factual claim",
      "verdict": "true|false|misleading|unverifiable",
      "evidence": "Evidence found with source attribution",
      "sources": ["Source name or URL"]
    }
  ],
  "sources_checked": [
    {
      "url": "https://...",
      "title": "Source name",
      "relevant_excerpt": "Key quote from the source",
      "supports": true
    }
  ]
}"""


async def _factcheck_statement(statement: str, semaphore: asyncio.Semaphore) -> dict | None:
    """Fact-check a custom user statement via Claude CLI."""
    async with semaphore:
        prompt = FACTCHECK_STATEMENT_PROMPT + f"\n\n---\nSTATEMENT TO FACT-CHECK:\n{statement}\n"
        try:
            raw = await call_claude(prompt, model="sonnet", timeout=300, max_turns=4, allowed_tools=["WebSearch", "WebFetch"])
            result = extract_json(raw)
            if not result or not isinstance(result, dict):
                return None
            return {
                "verdict": result.get("verdict", "unverifiable"),
                "verdict_summary": result.get("verdict_summary", "Analysis inconclusive"),
                "confidence": result.get("confidence", 0.5),
                "claims_analyzed": result.get("claims_analyzed"),
                "sources_checked": result.get("sources_checked"),
                "key_finding": result.get("key_finding"),
                "context": result.get("context"),
                "model_used": "sonnet",
            }
        except Exception as e:
            logger.error("Statement fact-check failed: %s", e)
            return None


async def run_factcheck():
    """Fact-check agent: picks top stories by request count, verifies via Claude CLI.

    Election-optimized: parallel checks (3 concurrent), tight prompt, max_turns=4.
    Runs every 30min via cron during election period.
    """
    FACTCHECK_PROMPT = """You are NARADA, a rigorous fact-checker for Nepal news.

## RULES
- Follow evidence, not assumptions. Political claims need official records.
- If evidence is insufficient, verdict = "unverifiable". Do NOT guess.
- Decompose the story into atomic factual claims before verifying.
- Each claim must be self-contained (understandable without reading the article).
- For each claim, search for corroborating or contradicting evidence.
- Record every source you check, including sources that had no relevant info.

## PROCESS
1. Read the story carefully. Identify ALL verifiable factual claims (not opinions or predictions).
2. For each claim, formulate it as a self-contained statement:
   BAD: "The figure is wrong" (not self-contained)
   GOOD: "Nepal's GDP growth was 7.2% in FY2082 according to NRB" (self-contained)
3. Search for evidence for each claim. Use targeted queries.
4. For each source found, record its URL, a relevant excerpt, and whether it supports or contradicts.
5. Assess each claim independently, then aggregate into an overall verdict.
6. Set confidence based on: source quality, source agreement, and evidence completeness.
   - 0.9+ : Multiple Tier 1 sources (NRB, Election Commission) agree
   - 0.7-0.9 : Credible sources agree, minor gaps
   - 0.5-0.7 : Mixed or limited evidence
   - <0.5 : Mostly unverifiable, use "unverifiable" verdict

## NEPAL-SPECIFIC SOURCES (prefer these)
- Nepal Rastra Bank (nrb.org.np) — monetary/GDP data [Tier 1]
- Election Commission (election.gov.np) — election results [Tier 1]
- NepalFactCheck.org — existing fact-checks [Tier 1]
- Kathmandu Post, Republica, The Himalayan Times — English news [Tier 2]
- Kantipur, Ratopati, Setopati — Nepali news [Tier 2]

## VERDICT SCALE
- "true" — Verified by multiple independent sources
- "mostly_true" — Main claim accurate, minor inaccuracy or missing nuance
- "partially_true" — Mix of accurate and inaccurate elements
- "misleading" — True elements framed to give false impression
- "false" — Core claims contradicted by evidence
- "unverifiable" — Insufficient evidence to determine (this is OK)
- "satire" — Intentionally fictional/satirical

## OUTPUT — respond with ONLY this JSON, nothing else:
{
  "verdict": "true|mostly_true|partially_true|misleading|false|unverifiable|satire",
  "verdict_summary": "2-3 sentences explaining the verdict with specific evidence cited.",
  "confidence": 0.0-1.0,
  "key_finding": "Single most important finding from the fact-check",
  "context": "Important missing context from the original story (or null)",
  "claims_analyzed": [
    {
      "claim": "Self-contained factual claim",
      "verdict": "true|false|misleading|unverifiable",
      "evidence": "Evidence found with source attribution",
      "sources": ["Source name or URL"]
    }
  ],
  "sources_checked": [
    {
      "url": "https://...",
      "title": "Source name",
      "relevant_excerpt": "Key quote from the source",
      "supports": true
    }
  ]
}"""

    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch pending fact-checks
        logger.info("Fetching pending fact-check requests...")
        resp = await client._client.get(
            "/fact-check/pending",
            params={"limit": 10},
            headers=client._headers,
        )
        resp.raise_for_status()
        pending = resp.json()
        logger.info("Got %d stories awaiting fact-check", len(pending))

        if not pending:
            logger.info("No pending story fact-checks")

        if pending:
            # 2. Fact-check stories in parallel (max 3 concurrent)
            t0 = time.monotonic()
            semaphore = asyncio.Semaphore(3)
            tasks = [
                _factcheck_one(item, FACTCHECK_PROMPT, semaphore)
                for item in pending
            ]
            raw_results = await asyncio.gather(*tasks)
            results = [r for r in raw_results if r is not None]

            # 3. POST results to VPS
            if results:
                logger.info("POSTing %d fact-check results to VPS...", len(results))
                resp = await client._client.post(
                    "/fact-check/ingest",
                    json={"results": results},
                    headers=client._headers,
                    timeout=30.0,
                )
                resp.raise_for_status()
                ingest_result = resp.json()
                duration = time.monotonic() - t0
                logger.info(
                    "=== Fact-check complete (%.1fs) ===\n"
                    "  Checked: %d, Ingested: %d, Skipped: %d",
                    duration, len(results),
                    ingest_result["ingested"], ingest_result["skipped"],
                )
            else:
                logger.info("No fact-checks completed")

        # 4. Process pending custom statements
        logger.info("Fetching pending custom statements...")
        resp = await client._client.get(
            "/fact-check/statement/pending",
            params={"limit": 5},
            headers=client._headers,
        )
        resp.raise_for_status()
        pending_stmts = resp.json()
        logger.info("Got %d pending statements", len(pending_stmts))

        if pending_stmts:
            stmt_semaphore = asyncio.Semaphore(2)
            stmt_tasks = []
            for stmt in pending_stmts:
                stmt_tasks.append(_factcheck_statement(stmt["statement"], stmt_semaphore))
            stmt_raw = await asyncio.gather(*stmt_tasks)

            ingest_items = []
            for stmt_item, stmt_result in zip(pending_stmts, stmt_raw):
                if stmt_result is None:
                    logger.warning("  Statement %s failed", stmt_item["id"][:8])
                    continue
                ingest_items.append({
                    "statement_id": stmt_item["id"],
                    **stmt_result,
                })
                logger.info("  Statement %s -> %s (%.0f%%)",
                            stmt_item["id"][:8], stmt_result["verdict"],
                            stmt_result.get("confidence", 0) * 100)

            if ingest_items:
                try:
                    resp = await client._client.post(
                        "/fact-check/statement/ingest",
                        json={"results": ingest_items},
                        headers=client._headers,
                        timeout=15.0,
                    )
                    resp.raise_for_status()
                    ingest_resp = resp.json()
                    logger.info("  Statements ingested: %d", ingest_resp.get("ingested", len(ingest_items)))
                except Exception as e:
                    logger.warning("  Failed to ingest statements: %s", e)

    finally:
        await client.close()


TACTICAL_CATEGORIES = {"security", "political", "disaster", "social"}

TACTICAL_PROMPT = """You are NARADA, Nepal's premier OSINT tactical intelligence classifier. Nepal is entering a critical ELECTION PERIOD — your classifications directly feed a live tactical situation map used by analysts, journalists, and officials.

## CLASSIFICATION RULES

For each story, classify with extreme precision:

1. **tactical_type** — Pick the BEST match:
   - SECURITY_DEPLOYMENT: Police/army mobilization, security cordons, checkpoints, force deployment, election security measures
   - ARREST: Detentions, police custody, raids, warrants, court remands
   - PROTEST: Public demonstrations, sit-ins, rallies against government/policy (not political campaign events)
   - ELECTORAL_VIOLENCE: Election-related clashes, booth capturing, candidate attacks, voter intimidation, ballot tampering, election-day violence
   - BORDER_INCIDENT: Cross-border tensions, smuggling, border closures, customs incidents
   - STRIKE: Bandhs, shutdowns, blockades, chakkajam, general strikes, transport strikes
   - POLITICAL_RALLY: Campaign events, election speeches, party meetings, candidate filing
   - CRIME: Murder, theft, robbery, fraud, kidnapping, drug-related (NOT election-related violence)
   - CURFEW: Curfew orders, Section 144, movement restrictions
   - RIOT: Mob violence, arson, vandalism, communal clashes, stone-pelting (overlaps with STRIKE for bandh-related violence — use STRIKE if bandh-motivated, RIOT if spontaneous)
   - EXPLOSION: Bombs, IEDs, blasts, suspicious devices
   - ACCIDENT: Road accidents, fire, industrial accidents, natural disasters
   - OTHER: Doesn't fit above categories

2. **municipality**: Most specific Nepal municipality/city (e.g., "Dhangadhi", "Birgunj", "Lalitpur"). Use Nepali place names. null if only district-level.
3. **ward**: Ward number if mentioned, null otherwise.
4. **tactical_context**: 1-sentence intelligence assessment with operational significance. Be specific: who, what, where, impact.
5. **actors**: Named actors, organizations, parties involved (e.g., ["Nepal Police", "CPN-UML", "Pushpa Kamal Dahal"])
6. **confidence**: HIGH (clear tactical event) | MEDIUM (likely tactical) | LOW (ambiguous)

## CROSS-LINGUAL AWARENESS
Stories may be in Nepali (Devanagari) or English. Same event often appears in both languages. Classify consistently regardless of language.

## ELECTION CONTEXT
- Stories about election security = SECURITY_DEPLOYMENT
- Candidate arrests = ARREST (not ELECTORAL_VIOLENCE unless violent)
- Election-related clashes/violence = ELECTORAL_VIOLENCE
- Campaign rallies/speeches = POLITICAL_RALLY
- Anti-election bandhs = STRIKE
- Stories about SAME incident with different wording — classify with SAME tactical_type

IMPORTANT: Only classify stories that are ACTUAL tactical events. Skip:
- Routine voting updates ("X casts vote", "Y% turnout in Z")
- Opinion pieces, editorials, weather, economic news
- International stories, sports, entertainment
Return EMPTY results array for non-tactical stories. Do NOT classify them as OTHER.
Only use OTHER if it's a genuine tactical event that doesn't fit the categories above.

Respond as JSON: {"results": [{"story_id": "...", "tactical_type": "...", "municipality": "...", "ward": null, "tactical_context": "...", "actors": [...], "confidence": "..."}]}

STORIES:
"""


async def run_tactical(hours: int = 1):
    """Tactical enrichment agent — near-real-time classification for election tactical map.

    Election-optimized: runs every 2 min, only classifies NEW stories not yet enriched.
    Uses Haiku (fast + cheap on Max). Skips already-enriched stories before calling Claude.
    """
    from app.data.municipality_coordinates import MUNICIPALITY_COORDINATES

    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch recent stories (short window — we run frequently)
        fetch_hours = min(hours, 48)
        logger.info("Fetching stories (last %dh) for tactical enrichment...", fetch_hours)
        stories = await client.export_stories(hours=fetch_hours)
        logger.info("Got %d stories from VPS API", len(stories))

        # 2. Filter to tactical-relevant categories
        tactical_stories = [
            s for s in stories
            if (s.get("category", "").lower() in TACTICAL_CATEGORIES)
            and not is_international(s.get("title", ""))
        ]
        logger.info("Filtered to %d tactical-relevant stories", len(tactical_stories))

        if not tactical_stories:
            logger.info("No tactical stories to process")
            return

        # 3. Check which stories are already enriched — skip them before calling Claude
        story_ids = [s.get("id", "") for s in tactical_stories]
        try:
            resp = await client._client.post(
                "/tactical/enriched-ids",
                json={"story_ids": story_ids},
                headers=client._headers,
                timeout=15.0,
            )
            resp.raise_for_status()
            enriched_ids = set(resp.json().get("enriched_ids", []))
        except Exception as e:
            logger.warning("Could not check enriched IDs (will re-classify all): %s", e)
            enriched_ids = set()

        new_stories = [s for s in tactical_stories if s.get("id", "") not in enriched_ids]
        logger.info("Already enriched: %d, New to classify: %d",
                     len(tactical_stories) - len(new_stories), len(new_stories))

        if not new_stories:
            logger.info("All stories already enriched — nothing to do")
            return

        # 4. Batch stories and classify in parallel (3 concurrent Haiku calls)
        BATCH_SIZE = 20
        t0 = time.monotonic()
        sem = asyncio.Semaphore(3)

        async def _classify_batch(batch: list[dict], batch_idx: int) -> list[dict]:
            stories_text = "\n---\n".join(
                f"STORY_ID: {s.get('id', '')}\n"
                f"TITLE: {s.get('title', '')}\n"
                f"CATEGORY: {s.get('category', '')}\n"
                f"DISTRICTS: {', '.join(s.get('districts', []))}\n"
                f"SUMMARY: {(s.get('ai_summary') or {}).get('haiku_summary', '')[:200]}"
                for s in batch
            )
            prompt = TACTICAL_PROMPT + stories_text
            async with sem:
                try:
                    logger.info("  Classifying batch %d (%d stories)...", batch_idx, len(batch))
                    raw = await call_claude(prompt, model="haiku", timeout=120)
                    result = extract_json(raw)
                    batch_results = result.get("results", [])

                    for item in batch_results:
                        municipality = item.get("municipality")
                        if municipality:
                            muni_lower = municipality.lower().strip()
                            if muni_lower in MUNICIPALITY_COORDINATES:
                                lat, lng, _dist = MUNICIPALITY_COORDINATES[muni_lower]
                                item["latitude"] = lat
                                item["longitude"] = lng
                            else:
                                for muni_key, (lat, lng, _dist) in MUNICIPALITY_COORDINATES.items():
                                    if muni_lower in muni_key or muni_key in muni_lower:
                                        item["latitude"] = lat
                                        item["longitude"] = lng
                                        break

                    logger.info("    -> %d classifications", len(batch_results))
                    return batch_results
                except Exception as e:
                    logger.warning("  Batch %d failed: %s", batch_idx, e)
                    return []

        batches = [
            new_stories[i:i + BATCH_SIZE]
            for i in range(0, len(new_stories), BATCH_SIZE)
        ]
        results = await asyncio.gather(*[
            _classify_batch(batch, i) for i, batch in enumerate(batches)
        ])
        all_enrichments = [item for batch_result in results for item in batch_result]

        # 5. POST results to VPS
        if all_enrichments:
            logger.info("POSTing %d tactical enrichments to VPS...", len(all_enrichments))
            result = await client.ingest_tactical(all_enrichments)
            duration = time.monotonic() - t0
            logger.info(
                "=== Tactical enrichment complete (%.1fs) ===\n"
                "  Total: %d, Ingested: %d, Skipped: %d",
                duration, result["total"], result["ingested"], result["skipped"],
            )
        else:
            logger.info("No tactical enrichments produced")

    finally:
        await client.close()


# ============================================================
# Story Digest Agent — Haiku generates BLUFs for top clusters
# ============================================================

DIGEST_PROMPT = """You are an intelligence analyst generating concise BLUF (Bottom Line Up Front) summaries for story clusters from Nepal.

For each cluster, write a 1-2 sentence BLUF that:
- States the KEY FACT first (who, what, where)
- Includes the SO WHAT (impact, implications, what to watch)
- Uses active voice, no filler words
- If election-related, note which party/candidate and constituency

Context: Nepal's provincial and federal elections are on 2082/01/04 BS (April 17, 2026 AD). The election campaign is active now.

Return JSON:
{
  "blufs": [
    {"cluster_id": "...", "bluf": "..."},
    ...
  ]
}

Here are the clusters:
"""


async def run_digest(hours: int = 72):
    """Generate Haiku BLUFs for top story clusters."""
    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch top clusters
        logger.info("Fetching top clusters (last %dh)...", hours)
        clusters = await client.get_cluster_timeline(hours=hours, limit=20, min_stories=2)
        logger.info("Got %d clusters", len(clusters))

        # Filter to those without BLUFs or with stale BLUFs
        needs_bluf = [c for c in clusters if not c.get("bluf")]
        logger.info("  %d need BLUFs", len(needs_bluf))

        if not needs_bluf:
            logger.info("All clusters already have BLUFs")
            return

        # 2. Format clusters for Haiku
        cluster_text = "\n---\n".join(
            f"CLUSTER_ID: {c['cluster_id']}\n"
            f"HEADLINE: {c['headline']}\n"
            f"CATEGORY: {c.get('category', 'unknown')}\n"
            f"SEVERITY: {c.get('severity', 'medium')}\n"
            f"SOURCES: {c.get('source_count', 0)} ({c.get('confidence_level', 'unknown')})\n"
            f"STORIES:\n" + "\n".join(
                f"  - [{s.get('source_name', '?')}] {s.get('title', '')}"
                for s in c.get("timeline", [])[:5]
            )
            for c in needs_bluf
        )

        prompt = DIGEST_PROMPT + cluster_text

        # 3. Call Haiku
        t0 = time.monotonic()
        logger.info("Generating BLUFs with Haiku...")
        raw = await call_claude(prompt, model="haiku", timeout=120)
        result = extract_json(raw)
        blufs = result.get("blufs", [])
        logger.info("  Got %d BLUFs in %.1fs", len(blufs), time.monotonic() - t0)

        # 4. POST to VPS
        if blufs:
            await client.login(EMAIL, PASSWORD)  # re-auth
            result = await client.bulk_update_blufs(blufs)
            logger.info("=== Digest complete: %d/%d BLUFs updated ===",
                        result.get("updated", 0), len(blufs))
        else:
            logger.info("No BLUFs generated")

    finally:
        await client.close()


async def run_embedding_backfill():
    """Backfill embeddings for un-embedded tweets via VPS API."""
    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        logger.info("Triggering tweet embedding backfill...")
        resp = await client._client.post(
            "/embeddings/generate",
            json={"hours": 72, "limit": 500, "nepal_only": True},
            headers=client._headers,
            timeout=120.0,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            "=== Embedding backfill complete: processed=%d created=%d skipped=%d failed=%d ===",
            result.get("processed", 0),
            result.get("created", 0),
            result.get("skipped", 0),
            result.get("failed", 0),
        )
    finally:
        await client.close()


SIGINT_ECONOMIC_PROMPT = """You are a Nepal financial intelligence analyst. Given this economic signal detected from news sources, provide a 2-3 sentence "so what" interpretation answering: What does this mean for NEPSE traders?

Be specific about sectors, stocks, or market dynamics affected. Use plain language.

SIGNAL: {signal_title}
SOURCES ({source_count} articles): {source_titles}

Respond with ONLY your 2-3 sentence interpretation, no preamble."""

SIGINT_SECURITY_PROMPT = """You are a Nepal security analyst. Given this security signal detected from news sources, provide a 2-3 sentence "so what" interpretation answering: What is the operational implication?

Focus on geographic impact, affected populations, and escalation potential. Use plain language.

SIGNAL: {signal_title}
SOURCES ({source_count} articles): {source_titles}

Respond with ONLY your 2-3 sentence interpretation, no preamble."""


async def run_sigint_triage():
    """SIGINT triage agent: interpret elevated signals with Haiku."""
    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch heatmap to find elevated topics
        logger.info("Fetching SIGINT heatmap (72h)...")
        resp = await client._client.get(
            "/sigint/heatmap",
            params={"hours": 72},
            headers=client._headers,
        )
        resp.raise_for_status()
        heatmap = resp.json()

        # 2. Identify HIGH/CRITICAL topics (nested: categories -> topics)
        elevated = []
        categories = heatmap.get("categories", []) if isinstance(heatmap, dict) else heatmap
        for cat in categories:
            cat_name = cat.get("category", "unknown")
            # Map category to signal type
            cat_type = "security" if cat_name.upper() in ("SECURITY", "POLITICAL") else "economic"
            for topic in cat.get("topics", []):
                intensity = topic.get("intensity", "").upper()
                if intensity in ("HIGH", "CRITICAL"):
                    elevated.append({
                        **topic,
                        "type": cat_type,
                        "category": cat_name,
                        "intensity": intensity,
                    })

        if not elevated:
            logger.info("No elevated SIGINT topics found. Skipping.")
            return

        logger.info("Found %d elevated SIGINT topics", len(elevated))

        # 3. Determine which signal types to fetch (dedup)
        need_economic = any(t["type"] == "economic" for t in elevated)
        need_security = any(t["type"] == "security" for t in elevated)

        # Get the max severity from elevated topics for each type
        econ_severity = "HIGH"
        sec_severity = "HIGH"
        for t in elevated:
            if t["type"] == "economic" and t["intensity"] == "CRITICAL":
                econ_severity = "CRITICAL"
            if t["type"] == "security" and t["intensity"] == "CRITICAL":
                sec_severity = "CRITICAL"

        interpretations = []
        seen_titles = set()

        async def fetch_and_interpret(endpoint: str, signal_type: str, severity: str):
            logger.info("  Fetching %s signals...", signal_type)
            try:
                sig_resp = await client._client.get(
                    endpoint,
                    params={"hours": 48},
                    headers=client._headers,
                )
                sig_resp.raise_for_status()
                signals_data = sig_resp.json()
            except Exception as e:
                logger.warning("  Failed to fetch %s signals: %s", signal_type, e)
                return

            signals = signals_data if isinstance(signals_data, list) else signals_data.get("signals", signals_data.get("items", []))

            for signal in signals:
                signal_title = signal.get("title", signal.get("signal_title", "unknown"))
                # Dedup by title
                if signal_title in seen_titles:
                    continue
                seen_titles.add(signal_title)

                sources = signal.get("sources", signal.get("source_titles", []))
                source_titles = ", ".join(
                    s.get("title", s) if isinstance(s, dict) else str(s)
                    for s in (sources[:10] if sources else [])
                )
                source_count = signal.get("source_count", len(sources) if sources else 0)

                if signal_type == "security":
                    prompt = SIGINT_SECURITY_PROMPT.format(
                        signal_title=signal_title,
                        source_count=source_count,
                        source_titles=source_titles or "N/A",
                    )
                else:
                    prompt = SIGINT_ECONOMIC_PROMPT.format(
                        signal_title=signal_title,
                        source_count=source_count,
                        source_titles=source_titles or "N/A",
                    )

                try:
                    t0 = time.monotonic()
                    interpretation = await call_claude(prompt, model="haiku", timeout=60)
                    logger.info("    Interpreted '%s' in %.1fs", signal_title[:50], time.monotonic() - t0)
                except Exception as e:
                    logger.warning("    Haiku failed for '%s': %s", signal_title[:50], e)
                    continue

                interpretations.append({
                    "signal_title": signal_title,
                    "signal_type": signal_type,
                    "severity": severity,
                    "interpretation": interpretation.strip(),
                    "source_count": source_count,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                })

        if need_economic:
            await fetch_and_interpret("/sigint/economic", "economic", econ_severity)
        if need_security:
            await fetch_and_interpret("/sigint/security", "security", sec_severity)

        if not interpretations:
            logger.info("No interpretations generated")
            return

        # 5. POST interpreted results to VPS
        logger.info("Posting %d triage interpretations to VPS...", len(interpretations))
        await client.login(EMAIL, PASSWORD)  # re-auth
        post_resp = await client._client.post(
            "/sigint/triage",
            json={"interpretations": interpretations},
            headers=client._headers,
            timeout=30.0,
        )
        post_resp.raise_for_status()
        result = post_resp.json()
        logger.info(
            "=== SIGINT triage complete: %d/%d interpretations stored ===",
            result.get("ingested", 0), len(interpretations),
        )

    finally:
        await client.close()


SIGINT_SONNET_PROMPT = """You are a senior Nepal intelligence analyst producing a SIGINT briefing.

You are given raw signal intelligence data — economic signals, security signals, cross-source convergence clusters, and novel/emerging signals detected in the last {period_hours} hours.

Produce a structured intelligence assessment with these sections:

## HEADLINE
One sentence capturing the most actionable intelligence in this cycle.

## NEPSE MARKET IMPACT
For each relevant signal, explain in 1-2 sentences what it means for NEPSE traders:
- Which sectors/stocks are affected (banking, hydropower, insurance, hotels, microfinance, manufacturing)?
- Is it bullish, bearish, or neutral?
- How confident are you (low/medium/high)?
- What is the expected time horizon (days/weeks/months)?

## SECURITY ASSESSMENT
For each relevant security signal:
- What is the operational implication?
- Geographic scope and affected populations?
- Escalation potential?

## KEY CONVERGENCE
Which stories are being covered by multiple independent sources? What does the convergence pattern tell us about confidence level?

## EMERGING SIGNALS
Any genuinely new topics that haven't appeared before? Are they threats or opportunities?

## BOTTOM LINE
2-3 sentences: If you were advising a NEPSE trader AND a security analyst in Kathmandu, what would you tell them to do RIGHT NOW?

--- RAW SIGNAL DATA ---

ECONOMIC SIGNALS ({economic_count}):
{economic_signals}

SECURITY SIGNALS ({security_count}):
{security_signals}

CONVERGENCE CLUSTERS ({convergence_count}):
{convergence_data}

NOVEL SIGNALS ({novel_count}):
{novel_signals}

TOPIC HEATMAP:
{heatmap_data}

Respond with ONLY the structured assessment. Be specific about Nepal context. No preamble."""


async def run_sigint_analysis():
    """SIGINT analysis agent: produce Sonnet-level intelligence assessment."""
    client = OSINTClient()
    try:
        await client.login(EMAIL, PASSWORD)

        # 1. Fetch all raw SIGINT data in parallel
        logger.info("Fetching raw SIGINT data for Sonnet analysis...")

        async def fetch_safe(endpoint, params=None):
            try:
                resp = await client._client.get(
                    endpoint,
                    params=params or {},
                    headers=client._headers,
                    timeout=90.0,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", endpoint, e)
                return None

        econ_data, sec_data, conv_data, novel_data, heatmap_data = await asyncio.gather(
            fetch_safe("/sigint/economic", {"hours": 48}),
            fetch_safe("/sigint/security", {"hours": 48}),
            fetch_safe("/sigint/convergence", {"hours": 72, "limit": 20}),
            fetch_safe("/sigint/novel", {"hours": 48, "limit": 15}),
            fetch_safe("/sigint/heatmap", {"hours": 72}),
        )

        # 2. Format signals for Sonnet
        economic_signals = []
        if econ_data:
            signals = econ_data if isinstance(econ_data, list) else econ_data.get("signals", [])
            for s in signals:
                title = s.get("title", "Unknown")
                severity = s.get("severity", "LOW")
                summary = s.get("summary", "")
                src_count = s.get("source_count", 0)
                economic_signals.append(f"  [{severity}] {title} ({src_count} sources): {summary}")

        security_signals = []
        if sec_data:
            signals = sec_data if isinstance(sec_data, list) else sec_data.get("signals", [])
            for s in signals:
                title = s.get("title", "Unknown")
                severity = s.get("severity", "LOW")
                summary = s.get("summary", "")
                src_count = s.get("source_count", 0)
                security_signals.append(f"  [{severity}] {title} ({src_count} sources): {summary}")

        convergence_items = []
        if conv_data:
            clusters = conv_data if isinstance(conv_data, list) else conv_data.get("clusters", [])
            for c in clusters[:15]:
                title = c.get("title", "Unknown")
                src_count = c.get("source_count", 0)
                avg_sim = c.get("avg_similarity", 0)
                convergence_items.append(f"  {title} ({src_count} sources, {avg_sim:.0%} avg similarity)")

        novel_items = []
        if novel_data:
            signals = novel_data if isinstance(novel_data, list) else novel_data.get("signals", [])
            # Deduplicate by rough title matching
            seen_titles = set()
            for n in signals:
                title = n.get("title", "Unknown")
                # Simple dedup: lowercase first 40 chars
                key = title.lower()[:40]
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                novelty = 1 - n.get("max_similarity_to_past", 0)
                novel_items.append(f"  {title} ({novelty:.0%} novel)")

        heatmap_str = ""
        if heatmap_data:
            categories = heatmap_data if isinstance(heatmap_data, list) else heatmap_data.get("categories", [])
            for cat in categories:
                cat_name = cat.get("category", "Unknown")
                topics = cat.get("topics", [])
                elevated = [t for t in topics if t.get("intensity", "NONE") in ("HIGH", "CRITICAL")]
                if elevated:
                    topic_strs = [f"{t['seed_query']}={t['intensity']}({t['count']})" for t in elevated]
                    heatmap_str += f"  {cat_name}: {', '.join(topic_strs)}\n"

        total_signals = len(economic_signals) + len(security_signals)
        if total_signals == 0 and not convergence_items and not novel_items:
            logger.info("No SIGINT data to analyze. Skipping Sonnet call.")
            return

        # 3. Call Sonnet for analysis
        prompt = SIGINT_SONNET_PROMPT.format(
            period_hours=48,
            economic_count=len(economic_signals),
            economic_signals="\n".join(economic_signals) or "  (none detected)",
            security_count=len(security_signals),
            security_signals="\n".join(security_signals) or "  (none detected)",
            convergence_count=len(convergence_items),
            convergence_data="\n".join(convergence_items) or "  (none detected)",
            novel_count=len(novel_items),
            novel_signals="\n".join(novel_items[:10]) or "  (none detected)",
            heatmap_data=heatmap_str or "  (no elevated topics)",
        )

        logger.info(
            "Calling Sonnet for SIGINT analysis (%d economic, %d security, %d convergence, %d novel)...",
            len(economic_signals), len(security_signals), len(convergence_items), len(novel_items),
        )
        t0 = time.monotonic()
        analysis = await call_claude(prompt, model="sonnet", timeout=120)
        elapsed = time.monotonic() - t0
        logger.info("Sonnet analysis complete in %.1fs (%d chars)", elapsed, len(analysis))

        # 4. Extract headline from analysis
        headline = "SIGINT Intelligence Assessment"
        for line in analysis.split("\n"):
            line = line.strip()
            if line.startswith("## HEADLINE"):
                continue
            if line and not line.startswith("#"):
                headline = line.strip("*").strip()
                break

        # 5. Extract NEPSE impact section
        nepse_impact = None
        in_nepse = False
        nepse_lines = []
        for line in analysis.split("\n"):
            if "NEPSE MARKET IMPACT" in line:
                in_nepse = True
                continue
            if in_nepse and line.strip().startswith("## "):
                break
            if in_nepse:
                nepse_lines.append(line)
        if nepse_lines:
            nepse_impact = "\n".join(nepse_lines).strip()

        # 6. POST to VPS
        await client.login(EMAIL, PASSWORD)  # re-auth
        payload = {
            "assessments": [{
                "analysis_type": "combined",
                "headline": headline[:300],
                "analysis": analysis,
                "nepse_impact": nepse_impact,
                "signals_analyzed": total_signals,
                "clusters_analyzed": len(convergence_items),
                "period_hours": 48,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }],
        }

        post_resp = await client._client.post(
            "/sigint/analysis",
            json=payload,
            headers=client._headers,
            timeout=30.0,
        )
        post_resp.raise_for_status()
        result = post_resp.json()
        logger.info(
            "=== SIGINT analysis complete: %d assessments stored ===",
            result.get("ingested", 0),
        )

    finally:
        await client.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run local agent via VPS API")
    parser.add_argument("job", choices=[
        "analyst", "province", "nitter", "reddit", "clustering",
        "factcheck", "tactical", "digest", "sigint", "sigint-analysis", "embeddings",
    ], help="Job to run")
    parser.add_argument("--hours", type=int, default=4, help="Analysis window (hours)")
    args = parser.parse_args()

    if not PASSWORD:
        print("Error: OSINT_PASSWORD env var not set")
        print("  export OSINT_PASSWORD='devpassword123'")
        sys.exit(1)

    logger.info("Running %s (API mode, no SSH tunnels)", args.job)
    if args.job == "analyst":
        asyncio.run(run_analyst(hours=args.hours))
    elif args.job == "province":
        asyncio.run(run_province(hours=args.hours))
    elif args.job == "nitter":
        asyncio.run(run_nitter())
    elif args.job == "reddit":
        asyncio.run(run_reddit())
    elif args.job == "clustering":
        asyncio.run(run_clustering(hours=args.hours))
    elif args.job == "factcheck":
        asyncio.run(run_factcheck())
    elif args.job == "tactical":
        asyncio.run(run_tactical(hours=args.hours))
    elif args.job == "digest":
        asyncio.run(run_digest(hours=args.hours))
    elif args.job == "sigint":
        asyncio.run(run_sigint_triage())
    elif args.job == "sigint-analysis":
        asyncio.run(run_sigint_analysis())
    elif args.job == "embeddings":
        asyncio.run(run_embedding_backfill())
    logger.info("DONE")


if __name__ == "__main__":
    main()
