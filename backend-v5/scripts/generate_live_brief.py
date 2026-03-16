#!/usr/bin/env python3
"""Generate a deterministic live national/provincial brief from VPS API exports.

This script is designed for the manual CLI workflow used to refresh the
National Assessment and Provincial Monitor widgets without relying on OpenAI or
Claude. It fetches the live story/tweet exports, enriches them with Nepal
district/province references, and emits:

- national markdown brief
- /briefs/ingest payload
- /province-anomalies/ingest payload

The output is intentionally prose-first so the dashboard reads like an analyst
brief rather than a metrics log.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("/Users/samriddhagc/Desktop/Projects/nepal_osint_v5")
DISTRICT_REF = ROOT / "backend-v5" / "app" / "data" / "nepal_districts.py"


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def fetch_guest_token(base_url: str) -> str:
    stdout = run(
        [
            "curl",
            "-s",
            "-X",
            "POST",
            f"{base_url}/api/v1/auth/guest",
            "-H",
            "Content-Type: application/json",
            "-d",
            "{}",
        ]
    )
    return json.loads(stdout)["access_token"]


def fetch_export(base_url: str, token: str, path: str) -> dict:
    stdout = run(
        [
            "curl",
            "-s",
            "-H",
            f"Authorization: Bearer {token}",
            f"{base_url}{path}",
        ]
    )
    return json.loads(stdout)


def load_nepal_reference() -> tuple[list[dict], list[dict]]:
    namespace: dict = {}
    exec(DISTRICT_REF.read_text(), namespace)
    return namespace["NEPAL_DISTRICTS"], namespace["NEPAL_PROVINCES"]


def normalize_text(*parts: str | None) -> str:
    return " ".join(part for part in parts if part).lower()


def title_case_words(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(word.capitalize() for word in value.split())


def top_categories(counter: Counter, limit: int = 3) -> list[str]:
    return [category for category, _ in counter.most_common(limit)]


def first_nonempty(*values):
    for value in values:
        if value:
            return value
    return None


class BriefGenerator:
    severity_weight = {
        "critical": 4.0,
        "high": 2.5,
        "medium": 1.0,
        "low": 0.4,
        None: 0.5,
        "unknown": 0.5,
    }

    def __init__(self) -> None:
        districts, provinces = load_nepal_reference()
        self.provinces = provinces
        self.province_alias_map: dict[str, str] = {}
        self.district_aliases: list[tuple[str, str, str]] = []
        self.district_to_province: dict[str, str] = {}

        for province in provinces:
            for alias in {province["name_en"], province.get("name_ne", "")} | set(province.get("aliases", [])):
                if alias:
                    self.province_alias_map[alias.lower()] = province["name_en"]

        for district in districts:
            district_name = district["name_en"].lower()
            self.district_to_province[district_name] = district["province_name"]
            for alias in {district["name_en"], district.get("name_ne", "")} | set(district.get("aliases", [])):
                if alias:
                    self.district_aliases.append((alias.lower(), district_name, district["province_name"]))

        self.district_aliases.sort(key=lambda item: len(item[0]), reverse=True)

    def extract_geo(self, story: dict) -> tuple[list[str], list[str]]:
        provinces = set(story.get("provinces") or [])
        districts = set(story.get("districts") or [])
        ai = story.get("ai_summary") if isinstance(story.get("ai_summary"), dict) else {}
        text = normalize_text(
            story.get("title"),
            ai.get("summary"),
            ai.get("headline"),
            story.get("source_name"),
        )
        for alias, district, province in self.district_aliases:
            if alias in text:
                districts.add(district)
                provinces.add(province)
        for alias, province in self.province_alias_map.items():
            if alias in text:
                provinces.add(province)
        for district in list(districts):
            province = self.district_to_province.get(str(district).lower())
            if province:
                provinces.add(province)
        return sorted(str(province) for province in provinces), sorted(str(district) for district in districts)

    def threat_level(self, score: float, critical: int, high: int) -> str:
        if critical >= 4 or score >= 36:
            return "ELEVATED"
        if critical >= 1 or high >= 4 or score >= 18:
            return "GUARDED"
        return "STABLE"

    def trajectory(self, score: float, story_count: int, critical: int, tweet_count: int) -> str:
        if critical >= 2 or score >= 28 or story_count >= 45 or tweet_count >= 8:
            return "RISING"
        return "STABLE"

    def province_bluf(
        self,
        province_name: str,
        category_counter: Counter,
        severity_counter: Counter,
        districts: list[str],
        key_sources: list[dict],
        threat_level: str,
        tweet_count: int,
        tweet_category_counter: Counter,
    ) -> str:
        drivers = top_categories(category_counter)
        driver_text = ", ".join(drivers[:2]) if drivers else "mixed local reporting"
        dominant_story = key_sources[0]["headline"] if key_sources else f"{province_name} incidents"
        district_text = ", ".join(districts[:2]).lower() if districts else province_name.lower()
        critical = severity_counter["critical"]
        high = severity_counter["high"]

        intro = f"{province_name} remained the main watch zone in this window." if threat_level == "ELEVATED" else f"{province_name} stayed on the board without breaking the national frame."
        sentence_two = (
            f"The provincial picture was set by {dominant_story}, with pressure concentrated around {district_text} and reinforced by {driver_text} reporting."
        )
        sentence_three = (
            f"The risk posture is {threat_level.lower()}, with {critical} critical and {high} high-severity items keeping the province operationally relevant."
            if (critical or high)
            else f"The risk posture is {threat_level.lower()}, with no concentrated severe-item burst visible in the window."
        )
        if tweet_count:
            tweet_drivers = ", ".join(top_categories(tweet_category_counter, 2)) or "online reaction"
            sentence_four = f"Tweet activity added a secondary signal, mainly around {tweet_drivers}."
        else:
            sentence_four = "Tweet activity did not materially change the read."
        return " ".join([intro, sentence_two, sentence_three, sentence_four])

    def category_note(self, province_name: str, category: str, stories: list[dict]) -> str | None:
        category_stories = [story for story in stories if story.get("category") == category]
        if not category_stories:
            return None
        lead = category_stories[0]["title"]
        if category == "political":
            return f"Political pressure in {province_name} was defined primarily by {lead}."
        if category == "economic":
            return f"Economic pressure in {province_name} was carried mainly by {lead}."
        if category in {"security", "disaster"}:
            return f"Public-safety pressure in {province_name} was driven chiefly by {lead}."
        return None

    def national_summary(
        self,
        watchlist: list[str],
        news_category_counter: Counter,
        source_counter: Counter,
        stories: list[dict],
        tweets: list[dict],
    ) -> str:
        primary_category = news_category_counter.most_common(1)[0][0] if news_category_counter else "mixed"
        top_source = source_counter.most_common(1)[0][0] if source_counter else "major outlets"
        intro = (
            f"Nepal remained nationally stable over the last {self.hours} hours, but the operating picture was uneven rather than quiet."
        )
        driver = (
            f"{primary_category.capitalize()} reporting dominated total volume, led by output from {top_source}, while the sharpest provincial pressure sat in {', '.join(watchlist)}."
        )
        tweet_line = (
            f"Social reaction was present and usable, with {len(tweets)} tweets adding corroboration and local sentiment to the news picture."
            if tweets
            else "The social layer was thin enough that the national read was still driven mainly by news reporting."
        )
        close = "This window reads as stable at national level but locally fragmented."
        return " ".join([intro, driver, tweet_line, close])

    def key_judgment(
        self,
        watchlist: list[str],
        severity_counter: Counter,
        stories: list[dict],
    ) -> str:
        critical = severity_counter["critical"]
        high = severity_counter["high"]
        lead = stories[0]["title"] if stories else "the current event mix"
        return (
            f"The operational picture is being shaped less by a single nationwide shock than by simultaneous provincial pressure points in {', '.join(watchlist)}, with {critical} critical and {high} high-severity stories keeping accountability, public-safety, and service-delivery risks active. "
            f"The most decision-relevant signal is {lead}, which indicates the center of gravity is still local escalation rather than national breakdown."
        )

    def generate(self, hours: int, base_url: str) -> dict:
        self.hours = hours
        token = fetch_guest_token(base_url)
        story_export = fetch_export(base_url, token, f"/api/v1/stories/export?hours={hours}&limit=1000")
        tweet_export = fetch_export(base_url, token, f"/api/v1/twitter/export?hours={hours}&limit=1000")

        stories = story_export.get("stories", [])
        tweets = tweet_export.get("tweets", [])
        period_start = story_export.get("since") or tweet_export.get("since")
        period_end = datetime.now(timezone.utc).isoformat()

        province_stats = {
            province["name_en"]: {
                "province_id": province["id"],
                "stories": [],
                "tweets": [],
                "district_counter": Counter(),
                "cat_counter": Counter(),
                "sev_counter": Counter(),
                "tweet_cat_counter": Counter(),
            }
            for province in self.provinces
        }

        source_counter = Counter()
        news_category_counter = Counter()
        news_severity_counter = Counter()
        tweet_category_counter = Counter()
        account_counter = Counter()

        for story in stories:
            ai = story.get("ai_summary") if isinstance(story.get("ai_summary"), dict) else {}
            story["category"] = story.get("category") or ai.get("category") or "unknown"
            story["severity"] = story.get("severity") or ai.get("severity") or "low"
            story["_provinces"], story["_districts"] = self.extract_geo(story)
            source_counter[story.get("source_name") or "Unknown"] += 1
            news_category_counter[story["category"]] += 1
            news_severity_counter[story["severity"]] += 1
            for province in story["_provinces"]:
                if province not in province_stats:
                    continue
                stats = province_stats[province]
                stats["stories"].append(story)
                stats["cat_counter"][story["category"]] += 1
                stats["sev_counter"][story["severity"]] += 1
                for district in story["_districts"]:
                    stats["district_counter"][district.lower()] += 1

        for tweet in tweets:
            text = normalize_text(tweet.get("text"), tweet.get("author_username"), tweet.get("author_name"))
            provinces = set()
            for alias, _, province in self.district_aliases:
                if alias in text:
                    provinces.add(province)
            for alias, province in self.province_alias_map.items():
                if alias in text:
                    provinces.add(province)
            category = tweet.get("category") or "unknown"
            tweet_category_counter[category] += 1
            account_counter[tweet.get("author_username") or tweet.get("author_name") or "unknown"] += 1
            for province in provinces:
                if province not in province_stats:
                    continue
                stats = province_stats[province]
                stats["tweets"].append(tweet)
                stats["tweet_cat_counter"][category] += 1

        province_outputs = []
        ranking = []
        hotspots = []

        for province_name, stats in province_stats.items():
            story_count = len(stats["stories"])
            tweet_count = len(stats["tweets"])
            critical = stats["sev_counter"]["critical"]
            high = stats["sev_counter"]["high"]
            score = sum(self.severity_weight.get(story["severity"], 0.5) for story in stats["stories"]) + tweet_count * 0.35
            threat_level = self.threat_level(score, critical, high)
            threat_trajectory = self.trajectory(score, story_count, critical, tweet_count)
            ranked_stories = sorted(
                stats["stories"],
                key=lambda story: (self.severity_weight.get(story["severity"], 0.5), story.get("published_at") or ""),
                reverse=True,
            )
            top_districts = [title_case_words(district) for district, _ in stats["district_counter"].most_common(3)]
            top_districts = [district for district in top_districts if district]
            key_sources = [
                {
                    "headline": story["title"],
                    "source_name": story.get("source_name"),
                    "severity": story.get("severity"),
                    "category": story.get("category"),
                    "published_at": story.get("published_at"),
                }
                for story in ranked_stories[:3]
            ]
            anomalies = [
                {
                    "type": story["category"],
                    "district": title_case_words(story["_districts"][0]) if story["_districts"] else None,
                    "severity": "high" if story["severity"] in ("critical", "high") else "medium",
                    "description": story["title"][:220],
                }
                for story in ranked_stories[:2]
            ]
            if ranked_stories:
                lead = ranked_stories[0]
                hotspots.append(
                    {
                        "province": province_name,
                        "district": title_case_words(lead["_districts"][0]) if lead["_districts"] else None,
                        "severity": "high" if lead["severity"] in ("critical", "high") else "medium",
                        "description": lead["title"],
                        "confidence": "medium-high" if lead["_districts"] else "medium",
                    }
                )
            province_outputs.append(
                {
                    "province_id": stats["province_id"],
                    "province_name": province_name,
                    "threat_level": threat_level,
                    "threat_trajectory": threat_trajectory,
                    "summary": self.province_bluf(
                        province_name,
                        stats["cat_counter"],
                        stats["sev_counter"],
                        top_districts,
                        key_sources,
                        threat_level,
                        tweet_count,
                        stats["tweet_cat_counter"],
                    ),
                    "political": self.category_note(province_name, "political", ranked_stories),
                    "economic": self.category_note(province_name, "economic", ranked_stories),
                    "security": self.category_note(province_name, "security", ranked_stories) or self.category_note(province_name, "disaster", ranked_stories),
                    "anomalies": anomalies,
                    "story_count": story_count,
                    "tweet_count": tweet_count,
                    "key_sources": key_sources,
                }
            )
            ranking.append((province_name, score, story_count))

        ranking.sort(key=lambda item: item[1], reverse=True)
        watchlist = [province for province, _, story_count in ranking if story_count > 0][:4]

        province_lookup = {province["province_name"]: province for province in province_outputs}
        immediate_watch = []
        for province_name in watchlist:
            province = province_lookup.get(province_name)
            if province and province["key_sources"]:
                immediate_watch.append(
                    {
                        "province": province_name,
                        "headline": province["key_sources"][0]["headline"],
                        "source_name": province["key_sources"][0]["source_name"],
                    }
                )

        national_summary = self.national_summary(watchlist, news_category_counter, source_counter, stories, tweets)
        key_judgment = self.key_judgment(
            watchlist,
            news_severity_counter,
            sorted(
                stories,
                key=lambda story: (self.severity_weight.get(story["severity"], 0.5), story.get("published_at") or ""),
                reverse=True,
            ),
        )

        brief_payload = {
            "period_start": period_start,
            "period_end": period_end,
            "national_summary": national_summary,
            "national_analysis": {
                "source": f"cli_manual_{hours}h",
                "method": "live_api_exports_only",
                "news_count": len(stories),
                "tweet_count": len(tweets),
                "province_watchlist": watchlist,
                "top_storylines": [item["headline"] for item in immediate_watch],
            },
            "hotspots": hotspots[:6],
            "trend_vs_previous": "stable",
            "key_judgment": key_judgment,
            "stories_analyzed": len(stories),
            "clusters_analyzed": 0,
            "claude_calls": 0,
            "duration_seconds": 0.0,
            "province_sitreps": [
                {
                    "province_id": province["province_id"],
                    "province_name": province["province_name"],
                    "bluf": province["summary"],
                    "security": province["security"],
                    "political": province["political"],
                    "economic": province["economic"],
                    "disaster": None,
                    "election": None,
                    "threat_level": province["threat_level"],
                    "threat_trajectory": province["threat_trajectory"],
                    "hotspots": province["anomalies"],
                    "flagged_stories": province["key_sources"],
                    "story_count": province["story_count"],
                }
                for province in province_outputs
            ],
            "fake_news_flags": [],
        }

        province_payload = {
            "stories_analyzed": len(stories),
            "tweets_analyzed": len(tweets),
            "provinces": province_outputs,
        }

        markdown_lines = [
            f"# NepalOSINT {hours}-Hour National Assessment and Provincial Monitor",
            "",
            f"Window used: {period_start} to {period_end}",
            "Method: live VPS API exports only, analyzed locally in CLI. No OpenAI key, no Claude fallback, no agent runtime.",
            f"Inputs used in full: {len(stories)} news stories and {len(tweets)} tweets.",
            "",
            "## National Assessment",
            "",
            national_summary,
            "",
            "## Key Findings",
            "",
            key_judgment,
            "",
            "## Immediate Watch",
        ]
        markdown_lines.extend(
            f"- {item['province']}: {item['headline']} ({item['source_name']})" for item in immediate_watch
        )
        markdown_lines.extend(["", "## Provincial Monitor", ""])
        for province in province_outputs:
            markdown_lines.extend(
                [
                    f"### {province['province_name']}",
                    province["summary"],
                    "",
                ]
            )
        markdown_lines.extend(
            [
                "## Bottom Line",
                "",
                f"This {hours}-hour cut indicates a stable national frame with sharper local stress concentrated in {', '.join(watchlist)}. If converted directly into widget copy, the national line should stay `stable but locally fragmented`, with the provincial watch order led by {', '.join(watchlist)}.",
            ]
        )

        return {
            "stories": stories,
            "tweets": tweets,
            "brief_payload": brief_payload,
            "province_payload": province_payload,
            "markdown": "\n".join(markdown_lines),
            "watchlist": watchlist,
            "period_start": period_start,
            "period_end": period_end,
            "news_category_counter": news_category_counter,
            "news_severity_counter": news_severity_counter,
            "tweet_category_counter": tweet_category_counter,
            "source_counter": source_counter,
            "account_counter": account_counter,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic live NepalOSINT brief.")
    parser.add_argument("--hours", type=int, default=12)
    parser.add_argument("--base-url", default="https://nepalosint.com")
    parser.add_argument("--output-dir", default=None, help="Optional explicit output directory")
    args = parser.parse_args()

    generator = BriefGenerator()
    result = generator.generate(args.hours, args.base_url)

    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "backend-v5" / "analysis_output" / f"brief_{args.hours}h_live_latest"
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / f"national_provincial_brief_{args.hours}h.md").write_text(result["markdown"])
    (output_dir / "brief_ingest_payload.json").write_text(json.dumps(result["brief_payload"], ensure_ascii=False, indent=2))
    (output_dir / "province_anomalies_ingest_payload.json").write_text(json.dumps(result["province_payload"], ensure_ascii=False, indent=2))
    (output_dir / "stories.json").write_text(json.dumps(result["stories"], ensure_ascii=False))
    (output_dir / "tweets.json").write_text(json.dumps(result["tweets"], ensure_ascii=False))

    print(
        json.dumps(
            {
                "stories": len(result["stories"]),
                "tweets": len(result["tweets"]),
                "watchlist": result["watchlist"],
                "period_start": result["period_start"],
                "period_end": result["period_end"],
                "output_dir": str(output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
