"""OpenAI-backed VPS briefing service for National Assessment and Provincial Monitor."""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.data.nepal_districts import NEPAL_DISTRICTS, NEPAL_PROVINCES, normalize_district_name
from app.data.municipality_coordinates import MUNICIPALITY_COORDINATES, NEPALI_MUNICIPALITIES
from app.models.province_anomaly import ProvinceAnomaly, ProvinceAnomalyRun
from app.models.situation_brief import ProvinceSitrep, SituationBrief
from app.models.story import Story
from app.models.story_feature import StoryFeature
from app.models.tweet import Tweet
from app.services.notification_matching_service import NotificationMatchingService
from app.services.openai_runtime import get_openai_runtime

logger = logging.getLogger(__name__)


class OpenAIBriefingService:
    """Generate and persist twice-daily operational briefings on the VPS."""

    severity_weight = {
        "critical": 4.0,
        "high": 2.5,
        "medium": 1.0,
        "low": 0.4,
        None: 0.5,
        "unknown": 0.5,
    }

    def __init__(self, db: AsyncSession, *, hours: Optional[int] = None, model: Optional[str] = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.openai = get_openai_runtime()
        self.hours = hours or self.settings.openai_briefing_hours
        self.model = model or self.settings.openai_briefing_model
        self.provinces = NEPAL_PROVINCES
        self.province_alias_map: dict[str, str] = {}
        self.district_aliases: list[tuple[str, str, str]] = []
        self.district_to_province: dict[str, str] = {}

        for province in self.provinces:
            for alias in {province["name_en"], province.get("name_ne", "")} | set(province.get("aliases", [])):
                if alias:
                    self.province_alias_map[alias.lower()] = province["name_en"]

        for district in NEPAL_DISTRICTS:
            district_name = district["name_en"].lower()
            self.district_to_province[district_name] = district["province_name"]
            district_aliases = {district["name_en"], district.get("name_ne", ""), district.get("headquarters", "")}
            for alias in district_aliases | set(district.get("aliases", [])):
                for variant in self._alias_variants(alias):
                    self.district_aliases.append((variant.lower(), district_name, district["province_name"]))

        for alias, municipality_key in NEPALI_MUNICIPALITIES.items():
            municipality = MUNICIPALITY_COORDINATES.get(municipality_key)
            if not municipality:
                continue
            district_name = str(municipality[2]).lower()
            province_name = self.district_to_province.get(district_name)
            if province_name:
                for variant in self._alias_variants(alias):
                    self.district_aliases.append((variant.lower(), district_name, province_name))
        self.district_aliases.sort(key=lambda item: len(item[0]), reverse=True)

    @staticmethod
    def _normalize_text(*parts: Optional[str]) -> str:
        return " ".join(part for part in parts if part).lower()

    @staticmethod
    def _alias_variants(value: Optional[str]) -> set[str]:
        if not value:
            return set()
        variants = {value}
        variants.add(value.replace("ञ्ज", "न्ज"))
        variants.add(value.replace("गञ्ज", "गन्ज"))
        return {variant for variant in variants if variant}

    @staticmethod
    def _title_case_words(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return " ".join(word.capitalize() for word in value.split())

    @staticmethod
    def _first_nonempty(*values: Any) -> Any:
        for value in values:
            if value:
                return value
        return None

    @staticmethod
    def _top_categories(counter: Counter, limit: int = 3) -> list[str]:
        return [category for category, _ in counter.most_common(limit)]

    def _extract_geo_from_text(self, text: str) -> tuple[set[str], set[str]]:
        provinces: set[str] = set()
        districts: set[str] = set()

        for alias, district, province in self.district_aliases:
            if alias in text:
                districts.add(district)
                provinces.add(province)

        # District-level anchors are more precise than generic province mentions.
        if not districts:
            for alias, province in self.province_alias_map.items():
                if alias in text:
                    provinces.add(province)

        return provinces, districts

    def _extract_story_geo(self, story: dict[str, Any]) -> tuple[list[str], list[str]]:
        provinces: set[str] = set()
        districts: set[str] = set()

        for province in story.get("provinces") or []:
            normalized = str(province).strip().lower()
            canonical = self.province_alias_map.get(normalized)
            if canonical:
                provinces.add(canonical)

        for district in story.get("districts") or []:
            normalized = normalize_district_name(str(district))
            if normalized:
                districts.add(normalized.lower())

        for district in list(districts):
            province = self.district_to_province.get(str(district).lower())
            if province:
                provinces.add(province)

        # Trust structured geography over fallback text. Source branding is not
        # geographic evidence and must not leak into province assignment.
        if provinces or districts:
            return sorted(str(province) for province in provinces), sorted(str(district) for district in districts)

        ai = story.get("ai_summary") if isinstance(story.get("ai_summary"), dict) else {}
        text = self._normalize_text(
            story.get("title"),
            ai.get("summary"),
            ai.get("headline"),
        )
        fallback_provinces, fallback_districts = self._extract_geo_from_text(text)
        provinces.update(fallback_provinces)
        districts.update(fallback_districts)

        return sorted(str(province) for province in provinces), sorted(str(district) for district in districts)

    def _extract_tweet_geo(self, tweet: dict[str, Any]) -> tuple[list[str], list[str]]:
        provinces = set(tweet.get("provinces") or [])
        districts = set()
        for district in tweet.get("districts") or []:
            normalized = normalize_district_name(str(district))
            if normalized:
                districts.add(normalized.lower())
        if provinces or districts:
            for district in list(districts):
                province = self.district_to_province.get(str(district).lower())
                if province:
                    provinces.add(province)
            return sorted(str(province) for province in provinces), sorted(str(district) for district in districts)

        text = self._normalize_text(tweet.get("text"), tweet.get("author_username"), tweet.get("author_name"))
        fallback_provinces, fallback_districts = self._extract_geo_from_text(text)
        provinces.update(fallback_provinces)
        districts.update(fallback_districts)
        for district in list(districts):
            province = self.district_to_province.get(str(district).lower())
            if province:
                provinces.add(province)
        return sorted(str(province) for province in provinces), sorted(str(district) for district in districts)

    def _threat_level(self, score: float, critical: int, high: int) -> str:
        if critical >= 4 or score >= 36:
            return "ELEVATED"
        if critical >= 1 or high >= 4 or score >= 18:
            return "GUARDED"
        return "STABLE"

    def _trajectory(self, score: float, story_count: int, critical: int, tweet_count: int) -> str:
        if critical >= 2 or score >= 28 or story_count >= 45 or tweet_count >= 8:
            return "RISING"
        return "STABLE"

    def _province_bluf(
        self,
        province_name: str,
        category_counter: Counter,
        severity_counter: Counter,
        districts: list[str],
        key_sources: list[dict[str, Any]],
        threat_level: str,
        tweet_count: int,
        tweet_category_counter: Counter,
    ) -> str:
        drivers = self._top_categories(category_counter)
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
            tweet_drivers = ", ".join(self._top_categories(tweet_category_counter, 2)) or "online reaction"
            sentence_four = f"Political tweet activity added a secondary signal, mainly around {tweet_drivers}."
        else:
            sentence_four = "Political tweet activity did not materially change the read."
        return " ".join([intro, sentence_two, sentence_three, sentence_four])

    def _category_note(self, province_name: str, category: str, stories: list[dict[str, Any]]) -> Optional[str]:
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

    async def _fetch_stories(self, since: datetime) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Story, StoryFeature.districts)
            .outerjoin(StoryFeature, Story.id == StoryFeature.story_id)
            .where(Story.created_at >= since)
            .order_by(desc(func.coalesce(Story.published_at, Story.created_at)))
        )
        rows = result.all()
        items: list[dict[str, Any]] = []
        for story, feature_districts in rows:
            items.append(
                {
                    "id": str(story.id),
                    "title": story.title,
                    "source_name": story.source_name or story.source_id,
                    "published_at": story.published_at.isoformat() if story.published_at else None,
                    "category": story.category,
                    "severity": story.severity,
                    "nepal_relevance": story.nepal_relevance,
                    "ai_summary": story.ai_summary,
                    "provinces": story.provinces or [],
                    "districts": feature_districts or story.districts or [],
                    "cluster_id": str(story.cluster_id) if story.cluster_id else None,
                }
            )
        return items

    async def _fetch_political_tweets(self, since: datetime) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Tweet)
            .where(Tweet.tweeted_at >= since)
            .where(func.lower(func.coalesce(Tweet.category, "")) == "political")
            .where(func.lower(func.coalesce(Tweet.nepal_relevance, "")) != "international")
            .order_by(desc(Tweet.tweeted_at))
        )
        tweets = result.scalars().all()
        items: list[dict[str, Any]] = []
        for tweet in tweets:
            items.append(
                {
                    "id": str(tweet.id),
                    "text": tweet.text,
                    "author_username": tweet.author_username,
                    "author_name": tweet.author_name,
                    "tweeted_at": tweet.tweeted_at.isoformat() if tweet.tweeted_at else None,
                    "nepal_relevance": tweet.nepal_relevance,
                    "category": tweet.category,
                    "severity": tweet.severity,
                    "provinces": tweet.provinces or [],
                    "districts": tweet.districts or [],
                }
            )
        return items

    def _build_base_payloads(self, stories: list[dict[str, Any]], tweets: list[dict[str, Any]], period_start: str, period_end: str) -> dict[str, Any]:
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
            story["_provinces"], story["_districts"] = self._extract_story_geo(story)
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
            tweet["_provinces"], tweet["_districts"] = self._extract_tweet_geo(tweet)
            category = (tweet.get("category") or "unknown").lower()
            tweet_category_counter[category] += 1
            account_counter[tweet.get("author_username") or tweet.get("author_name") or "unknown"] += 1
            for province in tweet["_provinces"]:
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
            threat_level = self._threat_level(score, critical, high)
            threat_trajectory = self._trajectory(score, story_count, critical, tweet_count)
            ranked_stories = sorted(
                stats["stories"],
                key=lambda story: (self.severity_weight.get(story["severity"], 0.5), story.get("published_at") or ""),
                reverse=True,
            )
            top_districts = [self._title_case_words(district) for district, _ in stats["district_counter"].most_common(3)]
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
                    "district": self._title_case_words(story["_districts"][0]) if story["_districts"] else None,
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
                        "district": self._title_case_words(lead["_districts"][0]) if lead["_districts"] else None,
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
                    "summary": self._province_bluf(
                        province_name,
                        stats["cat_counter"],
                        stats["sev_counter"],
                        top_districts,
                        key_sources,
                        threat_level,
                        tweet_count,
                        stats["tweet_cat_counter"],
                    ),
                    "political": self._category_note(province_name, "political", ranked_stories),
                    "economic": self._category_note(province_name, "economic", ranked_stories),
                    "security": self._category_note(province_name, "security", ranked_stories) or self._category_note(province_name, "disaster", ranked_stories),
                    "anomalies": anomalies,
                    "story_count": story_count,
                    "tweet_count": tweet_count,
                    "key_sources": key_sources,
                    "top_districts": top_districts,
                    "top_categories": self._top_categories(stats["cat_counter"], 3),
                }
            )
            ranking.append((province_name, score, story_count))

        ranking.sort(key=lambda item: item[1], reverse=True)
        watchlist = [province for province, _, story_count in ranking if story_count > 0][:4]

        province_lookup = {province["province_name"]: province for province in province_outputs}
        lead_stories = sorted(
            stories,
            key=lambda story: (self.severity_weight.get(story["severity"], 0.5), story.get("published_at") or ""),
            reverse=True,
        )

        brief_payload = {
            "period_start": period_start,
            "period_end": period_end,
            "national_summary": "",
            "national_analysis": {
                "source": "vps_openai_briefing",
                "method": "direct_db_plus_openai_4_1_mini",
                "news_count": len(stories),
                "political_tweet_count": len(tweets),
                "province_watchlist": watchlist,
                "top_storylines": [story["title"] for story in lead_stories[:8]],
            },
            "hotspots": hotspots[:6],
            "trend_vs_previous": "stable",
            "key_judgment": "",
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
            "provinces": [
                {
                    "province_id": province["province_id"],
                    "province_name": province["province_name"],
                    "threat_level": province["threat_level"],
                    "threat_trajectory": province["threat_trajectory"],
                    "summary": province["summary"],
                    "political": province["political"],
                    "economic": province["economic"],
                    "security": province["security"],
                    "anomalies": province["anomalies"],
                    "story_count": province["story_count"],
                    "tweet_count": province["tweet_count"],
                    "key_sources": province["key_sources"],
                }
                for province in province_outputs
            ],
        }

        return {
            "stories": stories,
            "tweets": tweets,
            "brief_payload": brief_payload,
            "province_payload": province_payload,
            "province_outputs": province_outputs,
            "watchlist": watchlist,
            "news_category_counter": news_category_counter,
            "news_severity_counter": news_severity_counter,
            "tweet_category_counter": tweet_category_counter,
            "source_counter": source_counter,
            "account_counter": account_counter,
            "lead_stories": lead_stories,
        }

    def _story_line(self, story: dict[str, Any]) -> str:
        province_text = ",".join(story.get("_provinces") or []) or "Unknown"
        district_text = ",".join(self._title_case_words(d) or d for d in (story.get("_districts") or [])[:2]) or "Unknown"
        return f"[{story.get('published_at') or '-'}] [{story.get('severity','low')}/{story.get('category','unknown')}] [{province_text} | {district_text}] {story.get('title','')}"

    def _tweet_line(self, tweet: dict[str, Any]) -> str:
        province_text = ",".join(tweet.get("_provinces") or []) or "Unknown"
        district_text = ",".join(self._title_case_words(d) or d for d in (tweet.get("_districts") or [])[:2]) or "Unknown"
        return f"[{tweet.get('tweeted_at') or '-'}] @{tweet.get('author_username') or tweet.get('author_name') or 'unknown'} [{province_text} | {district_text}] {tweet.get('text','')[:240]}"

    def _build_model_context(self, base: dict[str, Any], period_start: str, period_end: str) -> dict[str, Any]:
        return {
            "hours": self.hours,
            "period_start": period_start,
            "period_end": period_end,
            "stories_analyzed": len(base["stories"]),
            "political_tweets_analyzed": len(base["tweets"]),
            "watchlist": base["watchlist"],
            "top_story_categories": Counter(base["news_category_counter"]).most_common(8),
            "top_story_severities": Counter(base["news_severity_counter"]).most_common(8),
            "top_political_tweet_accounts": Counter(base["account_counter"]).most_common(20),
            "top_sources": Counter(base["source_counter"]).most_common(20),
            "province_digests": [
                {
                    "province_name": province["province_name"],
                    "threat_level": province["threat_level"],
                    "threat_trajectory": province["threat_trajectory"],
                    "story_count": province["story_count"],
                    "tweet_count": province["tweet_count"],
                    "top_districts": province["top_districts"],
                    "top_categories": province["top_categories"],
                    "lead_sources": province["key_sources"],
                    "current_summary": province["summary"],
                }
                for province in base["province_outputs"]
            ],
            "all_story_lines": [self._story_line(story) for story in base["stories"]],
            "all_political_tweet_lines": [self._tweet_line(tweet) for tweet in base["tweets"]],
        }

    async def _rewrite_with_openai(self, context: dict[str, Any]) -> dict[str, Any]:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "national_summary": {"type": "string"},
                "key_judgment": {"type": "string"},
                "province_summaries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "province_name": {"type": "string"},
                            "summary": {"type": "string"},
                        },
                        "required": ["province_name", "summary"],
                    },
                },
            },
            "required": ["national_summary", "key_judgment", "province_summaries"],
        }
        system_prompt = (
            "You write sober operational intelligence briefings for NepalOSINT. "
            "Use only the supplied data. Be specific, event-led, and analyst-oriented."
        )
        user_prompt = (
            "Rewrite the national summary, key judgment, and one summary per province. "
            "Use the full story list and the full political tweet list from the analysis window. "
            "Do not mention process, generation, APIs, models, dashboards, or counts as the opening frame. "
            "Prioritize Nepal-located developments, operational consequences, and provincial pressure points. "
            "National summary: 120-190 words. Key judgment: 80-140 words. Each province summary: 45-90 words.\n\n"
            f"Context JSON:\n{json_dumps(context)}"
        )
        return await self.openai.json_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema_name="vps_briefing",
            schema=schema,
            model=self.model,
            max_completion_tokens=self.settings.openai_briefing_completion_tokens,
            prompt_char_limit=self.settings.openai_briefing_prompt_chars,
            respect_structured_completion_cap=False,
            temperature=0.1,
            cache_scope=f"brief:{self.hours}:{context['period_start']}:{context['period_end']}",
            usage_bucket="structured",
        )

    async def _persist(self, brief_payload: dict[str, Any], province_payload: dict[str, Any]) -> tuple[SituationBrief, ProvinceAnomalyRun]:
        result = await self.db.execute(select(func.coalesce(func.max(SituationBrief.run_number), 0)))
        next_run = (result.scalar() or 0) + 1
        period_start = brief_payload["period_start"]
        period_end = brief_payload["period_end"]
        if isinstance(period_start, str):
            period_start = datetime.fromisoformat(period_start)
        if isinstance(period_end, str):
            period_end = datetime.fromisoformat(period_end)

        brief = SituationBrief(
            run_number=next_run,
            period_start=period_start,
            period_end=period_end,
            national_summary=brief_payload["national_summary"],
            national_analysis=brief_payload["national_analysis"],
            hotspots=brief_payload["hotspots"],
            trend_vs_previous=brief_payload["trend_vs_previous"],
            key_judgment=brief_payload["key_judgment"],
            stories_analyzed=brief_payload["stories_analyzed"],
            clusters_analyzed=brief_payload["clusters_analyzed"],
            claude_calls=brief_payload["claude_calls"],
            duration_seconds=brief_payload["duration_seconds"],
            status="completed",
        )
        self.db.add(brief)
        await self.db.flush()

        for sitrep in brief_payload["province_sitreps"]:
            self.db.add(
                ProvinceSitrep(
                    brief_id=brief.id,
                    province_id=sitrep["province_id"],
                    province_name=sitrep["province_name"],
                    bluf=sitrep["bluf"],
                    security=sitrep["security"],
                    political=sitrep["political"],
                    economic=sitrep["economic"],
                    disaster=sitrep["disaster"],
                    election=sitrep["election"],
                    threat_level=sitrep["threat_level"],
                    threat_trajectory=sitrep["threat_trajectory"],
                    hotspots=sitrep["hotspots"],
                    flagged_stories=sitrep["flagged_stories"],
                    story_count=sitrep["story_count"],
                )
            )

        run_now = datetime.now(timezone.utc)
        anomaly_run = ProvinceAnomalyRun(
            started_at=run_now,
            completed_at=run_now,
            status="completed",
            stories_analyzed=province_payload["stories_analyzed"],
            tweets_analyzed=province_payload["tweets_analyzed"],
            model_used=self.model,
        )
        self.db.add(anomaly_run)
        await self.db.flush()

        anomalies: list[ProvinceAnomaly] = []
        for province in province_payload["provinces"]:
            anomaly = ProvinceAnomaly(
                run_id=anomaly_run.id,
                province_id=province["province_id"],
                province_name=province["province_name"],
                threat_level=province["threat_level"],
                threat_trajectory=province["threat_trajectory"],
                summary=province["summary"],
                political=province["political"],
                economic=province["economic"],
                security=province["security"],
                anomalies_data=province["anomalies"],
                story_count=province["story_count"],
                tweet_count=province["tweet_count"],
                key_sources=province["key_sources"],
            )
            self.db.add(anomaly)
            anomalies.append(anomaly)

        await self.db.commit()

        try:
            await NotificationMatchingService(self.db).process_brief(brief)
            await NotificationMatchingService(self.db).process_province_anomalies(anomaly_run, anomalies)
        except Exception as exc:
            logger.warning("Notification generation failed after briefing run: %s", exc)

        return brief, anomaly_run

    async def run(self) -> dict[str, Any]:
        if not self.settings.openai_briefing_enabled:
            raise RuntimeError("OpenAI VPS briefing is disabled")
        if not self.openai.available:
            raise RuntimeError("OpenAI API key is not configured")

        period_end_dt = datetime.now(timezone.utc)
        period_start_dt = period_end_dt - timedelta(hours=self.hours)
        period_start = period_start_dt.isoformat()
        period_end = period_end_dt.isoformat()

        stories = await self._fetch_stories(period_start_dt)
        tweets = await self._fetch_political_tweets(period_start_dt)
        base = self._build_base_payloads(stories, tweets, period_start, period_end)
        context = self._build_model_context(base, period_start, period_end)
        model_result = await self._rewrite_with_openai(context)

        brief_payload = base["brief_payload"]
        province_payload = base["province_payload"]
        brief_payload["national_summary"] = model_result["national_summary"].strip()
        brief_payload["key_judgment"] = model_result["key_judgment"].strip()

        province_summary_map = {
            item["province_name"]: item["summary"].strip()
            for item in model_result.get("province_summaries", [])
            if item.get("province_name") and item.get("summary")
        }
        for sitrep in brief_payload["province_sitreps"]:
            sitrep["bluf"] = province_summary_map.get(sitrep["province_name"], sitrep["bluf"])
        for province in province_payload["provinces"]:
            province["summary"] = province_summary_map.get(province["province_name"], province["summary"])

        brief, anomaly_run = await self._persist(brief_payload, province_payload)
        return {
            "brief": brief,
            "province_anomaly_run": anomaly_run,
            "brief_payload": brief_payload,
            "province_payload": province_payload,
            "stories_analyzed": len(stories),
            "tweets_analyzed": len(tweets),
            "period_start": period_start,
            "period_end": period_end,
        }


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
