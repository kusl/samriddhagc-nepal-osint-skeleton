"""Government decision extraction, review, and public-feed service."""
from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.announcement import GovtAnnouncement
from app.models.govt_decision import GovtDecisionItem
from app.models.govt_decision_review import GovtDecisionReview
from app.models.story import Story
from app.services.editorial_control_service import EditorialControlService
from app.services.openai_runtime import OpenAIUsageLimitExceeded, get_openai_runtime

logger = logging.getLogger(__name__)

ACTOR_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cabinet", ("cabinet", "council of ministers", "मन्त्रिपरिषद", "मन्त्रिपरिषद्")),
    ("government", ("government", "govt", "सरकार")),
    ("opmcm", ("opmcm", "prime minister", "pm", "प्रधानमन्त्री", "प्रधान मंत्री")),
    ("home_ministry", ("home ministry", "ministry of home affairs", "गृह मन्त्रालय")),
    ("finance_ministry", ("finance ministry", "ministry of finance", "अर्थ मन्त्रालय")),
    ("ministry", ("ministry", "मन्त्रालय")),
    ("department", ("department", "विभाग")),
    ("spokesperson", ("spokesperson", "प्रवक्ता")),
    ("committee", ("committee", "समिति")),
    ("administration", ("administration", "प्रशासन", "district administration office", "dao")),
)

ACTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("decided", ("decided", "decision", "decides", "निर्णय", "निर्णय गर्", "cabinet decision")),
    ("approved", ("approved", "approval", "approved to", "स्वीकृत")),
    ("ordered", ("ordered", "order", "directed", "instruction", "instructed", "आदेश", "निर्देशन")),
    ("formed", ("formed", "formation", "constituted", "formed committee", "गठन")),
    ("implemented", ("implemented", "implementation", "implement", "लागू", "कार्यान्वयन")),
    ("appointed", ("appointed", "appointment", "assigned", "assign", "नियुक्त", "तोक")),
    ("imposed", ("imposed", "impose", "suspended", "repealed", "launched", "launched reform", "खारेज")),
)

EXCLUSION_TERMS = (
    "speech", "addressed", "claimed", "promise", "promised", "pledged", "demanded",
    "allegation", "alleges", "campaign", "rally", "attended", "meeting with", "opinion", "editorial",
    "warning", "urged", "asked to", "calls for", "remarks", "office assumption", "sworn in",
    "शपथ", "भाषण", "दाबी", "आरोप", "अपिल", "सम्बोधन",
)

TRUSTED_NEWS_TOKENS = (
    "ekantipur", "kathmandu post", "kathmandupost", "the kathmandu post",
    "republica", "my republica", "himalayan", "onlinekhabar", "setopati",
    "nagarik", "ratopati", "khabarhub", "kantipur tv", "kantipurtv",
    "risingnepal", "the rising nepal",
)

STOPWORDS = {
    "the", "a", "an", "to", "for", "of", "and", "on", "after", "with", "in", "at", "from",
    "this", "that", "new", "government", "minister", "ministry", "cabinet",
}

PUBLIC_DEDUPE_STOPWORDS = STOPWORDS | {
    "decision", "decided", "directive", "directed", "order", "ordered", "issued",
    "implementation", "implemented", "approval", "approved", "announced", "announcement",
    "plan", "plans", "within", "hour", "hours", "day", "days", "government", "nepal",
}

DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")


@dataclass
class DecisionSource:
    kind: str
    id: str
    title: str
    summary: str
    source_name: str
    source_token: str
    url: str
    published_at: datetime
    cluster_id: Optional[str]
    is_official: bool


@dataclass
class DecisionSeed:
    seed_key: str
    event_key: str
    actor_key: str
    action_key: str
    published_at: datetime
    sources: list[DecisionSource]


class GovtDecisionService:
    """Persisted government decision automation with dev review support."""

    PUBLIC_STATUSES = {"Active", "Under Review", "Announced"}
    WORKFLOW_PENDING = {"draft", "needs_correction"}

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.openai = get_openai_runtime()
        self.control_service = EditorialControlService(db)

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()

    @classmethod
    def _keyword_slug(cls, value: str) -> str:
        tokens = [token for token in cls._normalize_text(value).split() if token and token not in STOPWORDS]
        return "-".join(tokens[:5]) or "generic"

    @classmethod
    def _contains_any(cls, text: str, patterns: tuple[str, ...]) -> bool:
        lowered = (text or "").lower()
        return any(pattern in lowered for pattern in patterns)

    @classmethod
    def _match_actor(cls, text: str) -> Optional[str]:
        for key, patterns in ACTOR_PATTERNS:
            if cls._contains_any(text, patterns):
                return key
        return None

    @classmethod
    def _match_action(cls, text: str) -> Optional[str]:
        for key, patterns in ACTION_PATTERNS:
            if cls._contains_any(text, patterns):
                return key
        return None

    @classmethod
    def _is_candidate_text(cls, text: str) -> bool:
        lowered = (text or "").lower()
        if not lowered:
            return False
        actor = cls._match_actor(lowered)
        action = cls._match_action(lowered)
        if not actor or not action:
            return False
        if any(term in lowered for term in EXCLUSION_TERMS):
            return False
        return True

    @classmethod
    def _is_trusted_story(cls, story: Story) -> bool:
        blob = " ".join(
            part for part in [story.source_id or "", story.source_name or "", story.url or ""]
            if part
        ).lower()
        return any(token in blob for token in TRUSTED_NEWS_TOKENS)

    @classmethod
    def _safe_dt(cls, value: Optional[datetime], fallback: Optional[datetime] = None) -> datetime:
        return value or fallback or datetime.now(timezone.utc)

    @classmethod
    def _source_token(cls, name: str, url: str) -> str:
        blob = cls._normalize_text(f"{name} {url}")
        for token in TRUSTED_NEWS_TOKENS:
            if token in blob:
                return token
        return blob.split()[0] if blob else "unknown"

    @classmethod
    def _build_event_key(cls, *, title: str, summary: str, published_at: datetime) -> tuple[str, str, str]:
        text = " ".join(part for part in [title, summary] if part)
        actor = cls._match_actor(text.lower()) or "other"
        action = cls._match_action(text.lower()) or "other"
        bucket = published_at.astimezone(timezone.utc).strftime("%Y%m%d")
        slug = cls._keyword_slug(title or summary)
        return f"{actor}:{action}:{bucket}:{slug}", actor, action

    @staticmethod
    def _signature_for_sources(sources: list[DecisionSource]) -> str:
        payload = [
            {
                "kind": source.kind,
                "id": source.id,
                "title": source.title,
                "url": source.url,
                "published_at": source.published_at.isoformat(),
            }
            for source in sorted(sources, key=lambda item: (item.kind, item.id))
        ]
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    @classmethod
    def _support_counts(cls, sources: list[DecisionSource]) -> tuple[int, int]:
        official_count = sum(1 for source in sources if source.is_official)
        trusted_tokens = {source.source_token for source in sources if not source.is_official}
        return official_count, len(trusted_tokens)

    @classmethod
    def _compact_supporting_sources(cls, sources: list[DecisionSource]) -> list[dict[str, Any]]:
        ordered = sorted(
            sources,
            key=lambda item: (
                0 if item.is_official else 1,
                -(int(item.published_at.timestamp()) if item.published_at else 0),
            ),
        )[:5]
        return [
            {
                "kind": source.kind,
                "id": source.id,
                "title": source.title,
                "summary": source.summary,
                "source_name": source.source_name,
                "source_token": source.source_token,
                "url": source.url,
                "published_at": source.published_at.isoformat(),
                "cluster_id": source.cluster_id,
                "is_official": source.is_official,
            }
            for source in ordered
        ]

    @classmethod
    def _choose_representative(cls, sources: list[DecisionSource]) -> DecisionSource:
        return sorted(
            sources,
            key=lambda item: (
                0 if item.is_official else 1,
                -(int(item.published_at.timestamp()) if item.published_at else 0),
            ),
        )[0]

    @staticmethod
    def _unique_ids(values: list[str]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
        return merged

    @staticmethod
    def _merge_supporting_sources_payload(
        left: list[dict[str, Any]],
        right: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for source in list(left or []) + list(right or []):
            key = (
                str(source.get("kind") or ""),
                str(source.get("id") or ""),
                str(source.get("url") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
        merged.sort(
            key=lambda item: (
                0 if item.get("is_official") else 1,
                str(item.get("published_at") or ""),
            ),
            reverse=False,
        )
        return merged[:8]

    @classmethod
    def _candidate_public_item(
        cls,
        extracted: dict[str, Any],
        representative: DecisionSource,
        published_at: datetime,
    ) -> dict[str, Any]:
        return {
            "title": extracted.get("decision_title"),
            "office": extracted.get("office"),
            "implementingMinistry": extracted.get("implementing_ministry"),
            "decisionType": extracted.get("decision_type"),
            "decision": extracted.get("decision_summary"),
            "status": extracted.get("status"),
            "evidenceNote": extracted.get("evidence_summary"),
            "sourceName": representative.source_name,
            "sourceUrl": representative.url,
            "publishedAt": published_at,
        }

    async def _fetch_story_candidates(self, since: datetime) -> list[DecisionSeed]:
        stmt = (
            select(Story)
            .where(
                or_(Story.published_at >= since, Story.created_at >= since),
                or_(Story.nepal_relevance.is_(None), Story.nepal_relevance != "INTERNATIONAL"),
            )
            .order_by(Story.published_at.desc().nullslast(), Story.created_at.desc())
            .limit(400)
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        cluster_groups: dict[str, list[DecisionSource]] = defaultdict(list)
        loose_sources: list[DecisionSource] = []
        for story in rows:
            if not self._is_trusted_story(story):
                continue
            text = " ".join(part for part in [story.title or "", story.summary or ""] if part)
            if not self._is_candidate_text(text):
                continue
            source = DecisionSource(
                kind="story",
                id=str(story.id),
                title=story.title,
                summary=(story.summary or "")[:320],
                source_name=story.source_name or story.source_id,
                source_token=self._source_token(story.source_name or story.source_id or "", story.url or ""),
                url=story.url,
                published_at=self._safe_dt(story.published_at, story.created_at),
                cluster_id=str(story.cluster_id) if story.cluster_id else None,
                is_official=False,
            )
            if story.cluster_id:
                cluster_groups[str(story.cluster_id)].append(source)
            else:
                loose_sources.append(source)

        seeds: list[DecisionSeed] = []
        for cluster_id, sources in cluster_groups.items():
            rep = self._choose_representative(sources)
            event_key, actor, action = self._build_event_key(
                title=rep.title,
                summary=rep.summary,
                published_at=rep.published_at,
            )
            seeds.append(
                DecisionSeed(
                    seed_key=f"cluster:{cluster_id}",
                    event_key=event_key,
                    actor_key=actor,
                    action_key=action,
                    published_at=rep.published_at,
                    sources=sources,
                )
            )
        for source in loose_sources:
            event_key, actor, action = self._build_event_key(
                title=source.title,
                summary=source.summary,
                published_at=source.published_at,
            )
            seeds.append(
                DecisionSeed(
                    seed_key=f"story:{source.id}",
                    event_key=event_key,
                    actor_key=actor,
                    action_key=action,
                    published_at=source.published_at,
                    sources=[source],
                )
            )
        return seeds

    async def _fetch_announcement_candidates(self, since: datetime) -> list[DecisionSeed]:
        stmt = (
            select(GovtAnnouncement)
            .where(or_(GovtAnnouncement.published_at >= since, GovtAnnouncement.created_at >= since))
            .order_by(GovtAnnouncement.published_at.desc().nullslast(), GovtAnnouncement.created_at.desc())
            .limit(250)
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        seeds: list[DecisionSeed] = []
        for announcement in rows:
            summary = (announcement.content or "")[:320]
            text = " ".join(part for part in [announcement.title or "", summary] if part)
            if not self._is_candidate_text(text):
                continue
            source = DecisionSource(
                kind="announcement",
                id=str(announcement.id),
                title=announcement.title,
                summary=summary,
                source_name=announcement.source_name,
                source_token=self._source_token(announcement.source_name or "", announcement.url or ""),
                url=announcement.url,
                published_at=self._safe_dt(announcement.published_at, announcement.created_at),
                cluster_id=None,
                is_official=True,
            )
            event_key, actor, action = self._build_event_key(
                title=source.title,
                summary=source.summary,
                published_at=source.published_at,
            )
            seeds.append(
                DecisionSeed(
                    seed_key=f"announcement:{source.id}",
                    event_key=event_key,
                    actor_key=actor,
                    action_key=action,
                    published_at=source.published_at,
                    sources=[source],
                )
            )
        return seeds

    @classmethod
    def _merge_seeds(cls, seeds: list[DecisionSeed]) -> list[DecisionSeed]:
        grouped: dict[str, DecisionSeed] = {}
        for seed in sorted(seeds, key=lambda item: item.published_at, reverse=True):
            existing = grouped.get(seed.event_key)
            if not existing:
                grouped[seed.event_key] = DecisionSeed(
                    seed_key=seed.seed_key,
                    event_key=seed.event_key,
                    actor_key=seed.actor_key,
                    action_key=seed.action_key,
                    published_at=seed.published_at,
                    sources=list(seed.sources),
                )
                continue
            existing.sources.extend(seed.sources)
            if seed.published_at > existing.published_at:
                existing.published_at = seed.published_at
                existing.seed_key = seed.seed_key
        return sorted(grouped.values(), key=lambda item: item.published_at, reverse=True)

    async def _extract_candidate(self, seed: DecisionSeed) -> dict[str, Any]:
        if not self.openai.available:
            raise RuntimeError("OpenAI API key is not configured")

        sources = self._compact_supporting_sources(seed.sources)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_actual_decision": {"type": "boolean"},
                "office": {"type": "string"},
                "implementing_ministry": {"type": "string"},
                "decision_type": {
                    "type": "string",
                    "enum": [
                        "Cabinet Decision",
                        "Administrative Order",
                        "Operational Security Order",
                        "Governance Reform",
                        "Communications Assignment",
                        "Implementation Order",
                        "Non-Decision",
                    ],
                },
                "decision_title": {"type": "string"},
                "decision_summary": {"type": "string"},
                "status": {"type": "string"},
                "evidence_summary": {"type": "string"},
                "published_at": {"type": "string"},
                "confidence": {"type": "number"},
                "why_rejected": {"type": "string"},
            },
            "required": [
                "is_actual_decision",
                "office",
                "implementing_ministry",
                "decision_type",
                "decision_title",
                "decision_summary",
                "status",
                "evidence_summary",
                "published_at",
                "confidence",
                "why_rejected",
            ],
        }
        prompt_lines = [
            "Determine whether the following Nepal governance reporting describes an actual government decision.",
            "Use only the source snippets below. Do not infer missing ministries or offices.",
            "Distinguish actual decisions from speeches, promises, allegations, office assumption coverage, or commentary.",
            "Return every output field in English only. Translate Nepali source material into concise English.",
            "Do not return Nepali or Devanagari script in any JSON field.",
            "Supporting sources:",
        ]
        for index, source in enumerate(sources, start=1):
            prompt_lines.append(
                f"{index}. [{source['kind']}] {source['source_name']} | {source['published_at']} | {source['title']}"
            )
            if source.get("summary"):
                prompt_lines.append(f"   Summary: {source['summary']}")
            prompt_lines.append(f"   URL: {source['url']}")

        return await self.openai.json_completion(
            system_prompt=(
                "You extract concrete government decisions for a Nepal OSINT dashboard. "
                "Return strict JSON only. If the item is not an actual decision, mark is_actual_decision false and explain why_rejected."
            ),
            user_prompt="\n".join(prompt_lines),
            schema_name="govt_decision_extraction",
            schema=schema,
            model=self.settings.openai_clustering_model,
            max_completion_tokens=260,
            prompt_char_limit=4200,
            temperature=0.0,
            cache_scope=f"govt-decision:{seed.event_key}:{self._signature_for_sources(seed.sources)}",
            usage_bucket="govt_decision",
        )

    async def _find_duplicate_item(
        self,
        *,
        seed: DecisionSeed,
        extracted: dict[str, Any],
        representative: DecisionSource,
    ) -> Optional[GovtDecisionItem]:
        candidate_public = self._candidate_public_item(extracted, representative, seed.published_at)
        window_start = seed.published_at - timedelta(days=7)
        window_end = seed.published_at + timedelta(days=7)
        rows = (
            await self.db.execute(
                select(GovtDecisionItem)
                .options(selectinload(GovtDecisionItem.review))
                .where(
                    GovtDecisionItem.published_at >= window_start,
                    GovtDecisionItem.published_at <= window_end,
                )
                .order_by(GovtDecisionItem.published_at.desc().nullslast())
            )
        ).scalars().all()
        for item in rows:
            review = item.review
            if review and review.workflow_status in {"rejected", "superseded"}:
                continue
            existing_public = self.serialize_public_item(item)
            if self._public_items_match(existing_public, candidate_public):
                return item
        return None

    def _merge_into_existing_item(
        self,
        *,
        item: GovtDecisionItem,
        seed: DecisionSeed,
        extracted: dict[str, Any],
        signature: str,
        representative: DecisionSource,
        official_count: int,
        trusted_count: int,
        confidence: float,
        is_actual: bool,
    ) -> GovtDecisionItem:
        existing_payload = item.raw_model_payload or {}
        merged_supporting = self._merge_supporting_sources_payload(
            existing_payload.get("supporting_sources", []),
            self._compact_supporting_sources(seed.sources),
        )
        item.source_story_ids = self._unique_ids(list(item.source_story_ids or []) + [source.id for source in seed.sources if source.kind == "story"])
        item.source_announcement_ids = self._unique_ids(list(item.source_announcement_ids or []) + [source.id for source in seed.sources if source.kind == "announcement"])
        item.raw_model_payload = {
            **existing_payload,
            "candidate_signature": signature,
            "event_key": existing_payload.get("event_key") or seed.event_key,
            "actor_key": existing_payload.get("actor_key") or seed.actor_key,
            "action_key": existing_payload.get("action_key") or seed.action_key,
            "supporting_sources": merged_supporting,
            "official_support_count": max(int(existing_payload.get("official_support_count") or 0), official_count),
            "trusted_support_count": max(int(existing_payload.get("trusted_support_count") or 0), trusted_count),
            "model_output": extracted,
            "merged_duplicate": True,
        }
        if representative.is_official and representative.url:
            item.representative_url = representative.url
            item.source_name = representative.source_name
            item.representative_title = representative.title
        elif not item.representative_url:
            item.representative_url = representative.url
            item.source_name = representative.source_name
            item.representative_title = representative.title

        if confidence >= float(item.confidence or 0.0):
            item.office = extracted.get("office") or item.office
            item.implementing_ministry = extracted.get("implementing_ministry") or item.implementing_ministry
            item.decision_type = extracted.get("decision_type") or item.decision_type
            item.decision_title = extracted.get("decision_title") or item.decision_title
            item.decision_summary = extracted.get("decision_summary") or item.decision_summary
            item.status = extracted.get("status") or item.status
            item.evidence_summary = extracted.get("evidence_summary") or item.evidence_summary
            item.confidence = confidence
            item.is_actual_decision = is_actual
            item.published_at = min(
                [
                    dt for dt in [item.published_at, self._parse_model_datetime(extracted.get("published_at"), seed.published_at)]
                    if dt is not None
                ],
                default=self._parse_model_datetime(extracted.get("published_at"), seed.published_at),
            )
        return item

    async def _upsert_candidate(self, seed: DecisionSeed, extracted: dict[str, Any]) -> Optional[GovtDecisionItem]:
        signature = self._signature_for_sources(seed.sources)
        external_key = hashlib.sha1(f"{seed.event_key}:{signature}".encode("utf-8")).hexdigest()
        existing = (
            await self.db.execute(
                select(GovtDecisionItem)
                .options(selectinload(GovtDecisionItem.review))
                .where(GovtDecisionItem.external_key == external_key)
            )
        ).scalar_one_or_none()
        if existing and existing.review and not existing.review.needs_rerun:
            return None

        representative = self._choose_representative(seed.sources)
        official_count, trusted_count = self._support_counts(seed.sources)
        confidence = float(extracted.get("confidence", 0.0) or 0.0)
        is_actual = bool(extracted.get("is_actual_decision"))
        fields_complete = all(
            bool((extracted.get(field) or "").strip())
            for field in ("decision_title", "decision_summary", "decision_type", "office")
        )

        duplicate = None
        if existing is None:
            duplicate = await self._find_duplicate_item(
                seed=seed,
                extracted=extracted,
                representative=representative,
            )
            if duplicate is not None:
                existing = duplicate

        raw_payload = {
            "candidate_signature": signature,
            "event_key": seed.event_key,
            "actor_key": seed.actor_key,
            "action_key": seed.action_key,
            "supporting_sources": self._compact_supporting_sources(seed.sources),
            "official_support_count": official_count,
            "trusted_support_count": trusted_count,
            "model_output": extracted,
        }

        item = existing or GovtDecisionItem(
            external_key=external_key,
            event_key=seed.event_key,
            candidate_signature=signature,
        )
        if existing is None:
            self.db.add(item)
            await self.db.flush()
        elif duplicate is not None:
            item = self._merge_into_existing_item(
                item=item,
                seed=seed,
                extracted=extracted,
                signature=signature,
                representative=representative,
                official_count=official_count,
                trusted_count=trusted_count,
                confidence=confidence,
                is_actual=is_actual,
            )

        if duplicate is None:
            item.source_story_ids = [source.id for source in seed.sources if source.kind == "story"]
            item.source_announcement_ids = [source.id for source in seed.sources if source.kind == "announcement"]
            item.representative_title = representative.title
            item.representative_url = representative.url
            item.office = extracted.get("office") or None
            item.implementing_ministry = extracted.get("implementing_ministry") or None
            item.decision_type = extracted.get("decision_type") or None
            item.decision_title = extracted.get("decision_title") or None
            item.decision_summary = extracted.get("decision_summary") or None
            item.status = extracted.get("status") or None
            item.evidence_summary = extracted.get("evidence_summary") or None
            item.source_name = representative.source_name
            item.published_at = self._parse_model_datetime(extracted.get("published_at"), seed.published_at)
            item.confidence = confidence
            item.is_actual_decision = is_actual
            item.raw_model_payload = raw_payload
            item.candidate_signature = signature

        review = existing.review if existing else None
        if review is None:
            review = GovtDecisionReview(govt_decision_item_id=item.id)
            item.review = review
            self.db.add(review)

        if is_actual and confidence >= 0.92 and fields_complete and (official_count >= 1 or trusted_count >= 2):
            review.workflow_status = "approved"
            review.final_office = item.office
            review.final_implementing_ministry = item.implementing_ministry
            review.final_decision_type = item.decision_type
            review.final_decision_title = item.decision_title
            review.final_decision_summary = item.decision_summary
            review.final_status = item.status
            review.final_source_url = item.representative_url
            review.final_evidence_note = item.evidence_summary
            review.final_confidence = item.confidence
            review.reviewer_note = "System auto-approved due to high-confidence multi-source decision extraction."
            review.approved_at = datetime.now(timezone.utc)
            review.rejected_at = None
            review.rejected_by_id = None
            review.rejection_reason = None
            review.needs_rerun = False
        elif (not is_actual) or confidence < 0.70:
            review.workflow_status = "rejected"
            review.rejected_at = datetime.now(timezone.utc)
            review.rejection_reason = extracted.get("why_rejected") or "Rejected by automation."
            review.approved_at = None
            review.approved_by_id = None
            review.needs_rerun = False
        else:
            review.workflow_status = "needs_correction"
            review.approved_at = None
            review.approved_by_id = None
            review.rejected_at = None
            review.rejected_by_id = None
            review.rejection_reason = None
            review.reviewer_note = extracted.get("why_rejected") or "Requires editorial review."
            review.needs_rerun = False

        await self.db.flush()
        if review.workflow_status == "approved":
            await self._supersede_older_items(item)
        return item

    @staticmethod
    def _parse_model_datetime(value: Any, fallback: datetime) -> datetime:
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                return fallback
        return fallback

    async def _supersede_older_items(self, winner: GovtDecisionItem) -> None:
        rows = (
            await self.db.execute(
                select(GovtDecisionItem)
                .options(selectinload(GovtDecisionItem.review))
                .where(
                    GovtDecisionItem.event_key == winner.event_key,
                    GovtDecisionItem.id != winner.id,
                )
            )
        ).scalars().all()
        for item in rows:
            review = item.review
            if not review or review.workflow_status in {"rejected", "superseded"}:
                continue
            review.workflow_status = "superseded"
            review.reviewer_note = "Superseded by a newer approved extraction for the same decision event."
            review.approved_at = None

    async def run_generation(self, *, force: bool = False, max_candidates: int = 40) -> dict[str, Any]:
        if not self.openai.available:
            raise RuntimeError("OpenAI API key is not configured")
        if not force and not await self.control_service.is_enabled("govt_decision_generation"):
            return {"status": "paused", "processed": 0, "created": 0, "updated": 0, "skipped": 0}

        control = await self.control_service.get_control("govt_decision_generation")
        base_since = control.last_success_at or (datetime.now(timezone.utc) - timedelta(hours=24))
        since = base_since - timedelta(hours=12)

        story_seeds = await self._fetch_story_candidates(since)
        announcement_seeds = await self._fetch_announcement_candidates(since)
        merged = self._merge_seeds(story_seeds + announcement_seeds)[:max_candidates]

        stats = {"status": "ok", "processed": 0, "created": 0, "updated": 0, "skipped": 0}
        for seed in merged:
            stats["processed"] += 1
            try:
                before = (
                    await self.db.execute(
                        select(func.count())
                        .select_from(GovtDecisionItem)
                        .where(GovtDecisionItem.event_key == seed.event_key)
                    )
                ).scalar_one()
                extracted = await self._extract_candidate(seed)
                item = await self._upsert_candidate(seed, extracted)
                if item is None:
                    stats["skipped"] += 1
                elif before:
                    stats["updated"] += 1
                else:
                    stats["created"] += 1
            except OpenAIUsageLimitExceeded:
                raise
            except Exception:
                logger.warning("Government decision extraction failed for %s", seed.event_key, exc_info=True)
                stats["skipped"] += 1
                await self.db.rollback()
        await self.db.commit()
        return stats

    async def list_inbox(
        self,
        *,
        workflow_statuses: Optional[list[str]] = None,
        page: int = 1,
        per_page: int = 40,
    ) -> dict[str, Any]:
        stmt = (
            select(GovtDecisionItem)
            .outerjoin(GovtDecisionReview, GovtDecisionReview.govt_decision_item_id == GovtDecisionItem.id)
            .options(selectinload(GovtDecisionItem.review))
            .order_by(
                case(
                    (GovtDecisionReview.workflow_status.in_(["draft", "needs_correction"]), 0),
                    (GovtDecisionReview.workflow_status == "approved", 1),
                    (GovtDecisionReview.workflow_status == "superseded", 2),
                    else_=3,
                ),
                GovtDecisionItem.published_at.desc().nullslast(),
            )
        )
        count_stmt = (
            select(func.count(GovtDecisionItem.id))
            .select_from(GovtDecisionItem)
            .outerjoin(GovtDecisionReview, GovtDecisionReview.govt_decision_item_id == GovtDecisionItem.id)
        )
        if workflow_statuses:
            stmt = stmt.where(
                GovtDecisionReview.workflow_status.in_(workflow_statuses)
            )
            count_stmt = count_stmt.where(GovtDecisionReview.workflow_status.in_(workflow_statuses))
        total = int((await self.db.execute(count_stmt)).scalar() or 0)
        rows = (
            await self.db.execute(
                stmt.offset((page - 1) * per_page).limit(per_page)
            )
        ).scalars().all()
        return {
            "items": [self.serialize_editorial_item(item) for item in rows],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page if per_page else 0,
        }

    async def get_item(self, item_id: UUID) -> GovtDecisionItem | None:
        return (
            await self.db.execute(
                select(GovtDecisionItem)
                .options(selectinload(GovtDecisionItem.review))
                .where(GovtDecisionItem.id == item_id)
            )
        ).scalar_one_or_none()

    @classmethod
    def _encode_public_cursor(cls, published_at: Any, item_id: Any) -> str:
        timestamp = cls._parse_public_time(published_at).isoformat()
        raw = f"{timestamp}|{item_id}"
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")

    @classmethod
    def _decode_public_cursor(cls, cursor: str) -> tuple[datetime, UUID]:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode((cursor + padding).encode("utf-8")).decode("utf-8")
        published_at_raw, item_id_raw = decoded.split("|", 1)
        return cls._parse_public_time(published_at_raw), UUID(item_id_raw)

    async def list_public(
        self,
        *,
        limit: int = 25,
        dedupe: bool = False,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        stmt = (
            select(GovtDecisionItem)
            .join(GovtDecisionReview, GovtDecisionReview.govt_decision_item_id == GovtDecisionItem.id)
            .options(selectinload(GovtDecisionItem.review))
            .where(GovtDecisionReview.workflow_status == "approved")
            .order_by(GovtDecisionItem.published_at.desc().nullslast(), GovtDecisionItem.id.desc())
        )

        if cursor:
            try:
                cursor_published_at, cursor_id = self._decode_public_cursor(cursor)
                stmt = stmt.where(
                    or_(
                        GovtDecisionItem.published_at < cursor_published_at,
                        and_(
                            GovtDecisionItem.published_at == cursor_published_at,
                            GovtDecisionItem.id < cursor_id,
                        ),
                    )
                )
            except (ValueError, TypeError):
                logger.warning("Ignoring invalid govt-decision cursor: %s", cursor)

        fetch_limit = max(limit * (5 if dedupe else 1), 100 if dedupe else limit) + 1
        rows = (await self.db.execute(stmt.limit(fetch_limit))).scalars().all()
        public_rows = [self.serialize_public_item(item) for item in rows]

        if not dedupe:
            page_items = public_rows[:limit]
            has_more = len(public_rows) > limit
            next_cursor = (
                self._encode_public_cursor(rows[limit - 1].published_at, rows[limit - 1].id)
                if has_more and len(rows) >= limit
                else None
            )
            return {
                "items": page_items,
                "limit": limit,
                "has_more": has_more,
                "next_cursor": next_cursor,
            }

        deduped: list[dict[str, Any]] = []
        for row in public_rows:
            match_index = next(
                (idx for idx, existing in enumerate(deduped) if self._public_items_match(existing, row)),
                None,
            )
            if match_index is None:
                deduped.append(row)
                continue

            existing = deduped[match_index]
            existing_score = self._public_item_score(existing)
            candidate_score = self._public_item_score(row)
            if candidate_score > existing_score:
                deduped[match_index] = row
            elif candidate_score == existing_score:
                existing_time = self._parse_public_time(existing.get("publishedAt"))
                candidate_time = self._parse_public_time(row.get("publishedAt"))
                if candidate_time > existing_time:
                    deduped[match_index] = row

        deduped.sort(key=lambda item: self._parse_public_time(item.get("publishedAt")), reverse=True)
        page_items = deduped[:limit]
        has_more = len(deduped) > limit or len(rows) > limit
        next_cursor = (
            self._encode_public_cursor(page_items[-1].get("publishedAt"), page_items[-1].get("id"))
            if has_more and page_items
            else None
        )
        return {
            "items": page_items,
            "limit": limit,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def serialize_editorial_item(self, item: GovtDecisionItem) -> dict[str, Any]:
        review = item.review
        effective = self._effective_fields(item)
        raw_support = (item.raw_model_payload or {}).get("supporting_sources", [])
        return {
            "item_id": str(item.id),
            "external_key": item.external_key,
            "event_key": item.event_key,
            "representative_title": item.representative_title,
            "representative_url": item.representative_url,
            "source_name": item.source_name,
            "published_at": item.published_at,
            "source_story_ids": item.source_story_ids or [],
            "source_announcement_ids": item.source_announcement_ids or [],
            "source_count": len(item.source_story_ids or []) + len(item.source_announcement_ids or []),
            "raw": {
                "office": item.office,
                "implementing_ministry": item.implementing_ministry,
                "decision_type": item.decision_type,
                "decision_title": item.decision_title,
                "decision_summary": item.decision_summary,
                "status": item.status,
                "evidence_summary": item.evidence_summary,
                "confidence": item.confidence,
                "is_actual_decision": item.is_actual_decision,
                "supporting_sources": raw_support,
                "model_payload": item.raw_model_payload,
            },
            "review": {
                "workflow_status": review.workflow_status if review else "draft",
                "final_office": review.final_office if review else None,
                "final_implementing_ministry": review.final_implementing_ministry if review else None,
                "final_decision_type": review.final_decision_type if review else None,
                "final_decision_title": review.final_decision_title if review else None,
                "final_decision_summary": review.final_decision_summary if review else None,
                "final_status": review.final_status if review else None,
                "final_source_url": review.final_source_url if review else None,
                "final_evidence_note": review.final_evidence_note if review else None,
                "final_confidence": review.final_confidence if review else None,
                "reviewer_note": review.reviewer_note if review else None,
                "approved_at": review.approved_at if review else None,
                "rejected_at": review.rejected_at if review else None,
                "rejection_reason": review.rejection_reason if review else None,
                "needs_rerun": review.needs_rerun if review else False,
                "rerun_requested_at": review.rerun_requested_at if review else None,
            },
            "effective": effective,
        }

    def serialize_public_item(self, item: GovtDecisionItem) -> dict[str, Any]:
        effective = self._effective_fields(item)
        return {
            "id": str(item.id),
            "title": effective["decision_title"],
            "office": effective["office"],
            "implementingMinistry": effective["implementing_ministry"],
            "decisionType": effective["decision_type"],
            "decision": effective["decision_summary"],
            "status": effective["status"],
            "evidenceNote": effective["evidence_note"],
            "sourceName": item.source_name,
            "sourceUrl": effective["source_url"],
            "publishedAt": item.published_at,
        }

    @staticmethod
    def _contains_devanagari(value: str | None) -> bool:
        return bool(value and DEVANAGARI_PATTERN.search(value))

    @classmethod
    def _public_core_tokens(cls, item: dict[str, Any]) -> set[str]:
        text = str(item.get("title") or "").strip() or str(item.get("decision") or "").strip()
        return {
            token
            for token in cls._normalize_text(text).split()
            if token and token not in PUBLIC_DEDUPE_STOPWORDS and len(token) > 1
        }

    @classmethod
    def _public_text_signature(cls, item: dict[str, Any]) -> str:
        parts = [
            str(item.get("title") or ""),
            str(item.get("decision") or ""),
            str(item.get("office") or ""),
            str(item.get("implementingMinistry") or ""),
        ]
        normalized = cls._normalize_text(" ".join(parts))
        normalized = normalized.replace("applications", "apps")
        normalized = normalized.replace("application", "app")
        normalized = normalized.replace("websites", "website")
        normalized = normalized.replace("arrangements", "arrange")
        normalized = normalized.replace("treatment arrangements", "treatment")
        normalized = normalized.replace("effective treatment", "treatment")
        normalized = normalized.replace("district court kathmandu", "kathmandu district court")
        return normalized.strip()

    @staticmethod
    def _parse_public_time(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    @classmethod
    def _public_items_match(cls, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_time = cls._parse_public_time(left.get("publishedAt"))
        right_time = cls._parse_public_time(right.get("publishedAt"))

        left_tokens = cls._public_core_tokens(left)
        right_tokens = cls._public_core_tokens(right)
        if not left_tokens or not right_tokens:
            return False

        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        if union == 0:
            return False

        jaccard = intersection / union
        overlap = intersection / min(len(left_tokens), len(right_tokens))
        same_office = cls._normalize_text(str(left.get("office") or "")) == cls._normalize_text(str(right.get("office") or ""))
        same_ministry = cls._normalize_text(str(left.get("implementingMinistry") or "")) == cls._normalize_text(str(right.get("implementingMinistry") or ""))
        same_type = cls._normalize_text(str(left.get("decisionType") or "")) == cls._normalize_text(str(right.get("decisionType") or ""))
        left_signature = cls._public_text_signature(left)
        right_signature = cls._public_text_signature(right)
        text_ratio = SequenceMatcher(None, left_signature, right_signature).ratio() if left_signature and right_signature else 0.0
        max_age_gap = 60 * 24 * 3600 if same_office and intersection >= 4 else 7 * 24 * 3600
        if abs((left_time - right_time).total_seconds()) > max_age_gap:
            return False
        if same_ministry and intersection >= 4 and (jaccard >= 0.40 or overlap >= 0.65):
            return True
        if same_type and (same_office or same_ministry) and intersection >= 4:
            return True
        if same_type and (same_office or same_ministry) and (jaccard >= 0.55 or overlap >= 0.70):
            return True
        if (same_office or same_ministry or same_type) and text_ratio >= 0.62 and intersection >= 3:
            return True
        if intersection >= 4 and overlap >= 0.55:
            return True
        return jaccard >= 0.70 or (intersection >= 4 and overlap >= 0.70)

    @classmethod
    def _public_item_score(cls, item: dict[str, Any]) -> tuple[int, int]:
        text_blob = " ".join(
            str(item.get(field) or "")
            for field in ("title", "decision", "office", "implementingMinistry")
        )
        score = 0
        if not cls._contains_devanagari(text_blob):
            score += 100
        if item.get("implementingMinistry"):
            score += 10
        if item.get("office"):
            score += 5
        if item.get("decision"):
            score += 5
        if item.get("evidenceNote"):
            score += 2
        return score, int(cls._parse_public_time(item.get("publishedAt")).timestamp())

    @staticmethod
    def _effective_fields(item: GovtDecisionItem) -> dict[str, Any]:
        review = item.review
        use_review = bool(review and review.workflow_status == "approved")
        return {
            "office": review.final_office if use_review and review.final_office else item.office,
            "implementing_ministry": review.final_implementing_ministry if use_review and review.final_implementing_ministry else item.implementing_ministry,
            "decision_type": review.final_decision_type if use_review and review.final_decision_type else item.decision_type,
            "decision_title": review.final_decision_title if use_review and review.final_decision_title else item.decision_title,
            "decision_summary": review.final_decision_summary if use_review and review.final_decision_summary else item.decision_summary,
            "status": review.final_status if use_review and review.final_status else item.status,
            "source_url": review.final_source_url if use_review and review.final_source_url else item.representative_url,
            "evidence_note": review.final_evidence_note if use_review and review.final_evidence_note else item.evidence_summary,
            "confidence": review.final_confidence if use_review and review.final_confidence is not None else item.confidence,
        }
