"""Automated source reliability scoring from story history."""
from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.annotation import SourceReliability
from app.models.story import Story
from app.models.story_cluster import StoryCluster
from app.services.openai_runtime import OpenAIUsageLimitExceeded, get_openai_runtime

logger = logging.getLogger(__name__)

OFFICIAL_TERMS = (
    "ministry", "department", "court", "supreme court", "police", "army", "commission",
    "cabinet", "parliament", "municipality", "office", "authority", "bank", "notice",
    "circular", "press release", "gazette", "filing", "registry", "bureau", "secretariat",
    "मन्त्रालय", "विभाग", "अदालत", "आयोग", "कार्यालय", "नगरपालिका", "प्रेस विज्ञप्ति", "राजपत्र",
)
DOCUMENT_TERMS = (
    "document", "report", "filing", "letter", "notice", "circular", "directive", "decision",
    "minutes", "budget", "order", "dataset", "transcript", "pdf", "notice", "पत्र", "निर्णय",
    "सूचना", "प्रतिवेदन", "विवरण", "बिज्ञापन", "प्रतिवेदन", "दस्तावेज", "राजपत्र",
)
AGGREGATION_TERMS = (
    "according to", "as reported by", "reported by", "via", "agency", "syndicated",
    "reposted", "picked up from", "source said", "बताएको", "अनुसार", "जनाइएको", "एजेन्सी",
)
UNCERTAIN_TERMS = (
    "alleged", "reportedly", "said to", "unconfirmed", "claim", "claims", "may", "might",
    "possible", "likely", "developing", "preliminary", "आशंका", "सम्भावना", "बताइएको", "दाबी",
)
LOADED_TERMS = (
    "shocking", "massive", "explosive", "stunning", "exposed", "must read", "huge",
    "dramatic", "chaos", "भयावह", "सनसनी", "अत्यन्त", "भयंकर",
)
PRIMARY_SOURCE_TERMS = (
    "statement", "spokesperson", "filing", "court order", "official record", "press release",
    "communique", "transcript", "verdict", "gazette", "board decision", "says ministry",
    "विज्ञप्ति", "निर्णय", "सूचना", "पत्र", "आदेश", "प्रतिवेदन",
)
CLICKBAIT_TERMS = (
    "you won't believe", "what happened next", "watch", "must see", "viral", "here is why",
    "किन ?", "हेर्नुहोस्", "यस्तो भयो", "भिडियो",
)


@dataclass
class SourceCandidate:
    source_id: str
    source_name: str
    source_type: str
    story_count: int
    latest_story_at: Optional[datetime]


@dataclass
class SourceProfile:
    reliability_rating: str
    credibility_rating: int
    confidence_score: int
    notes: str
    metrics: dict[str, Any]


class SourceReliabilityScoringService:
    """Compute automated source reliability from story history."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.openai = get_openai_runtime()

    @staticmethod
    def classify_source_type(source_id: str, source_name: str) -> str:
        text = f"{source_id} {source_name}".lower()
        if ".gov.np" in text or "ministry" in text or "department" in text or "municipality" in text:
            return "government"
        if "twitter" in text or "facebook" in text or "youtube" in text or "tiktok" in text:
            return "social"
        if any(token in text for token in ("reuters", "ap ", "associated press", "afp", "ani", "xinhua")):
            return "wire"
        return "rss"

    @staticmethod
    def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))

    @staticmethod
    def _count_hits(text: str, terms: tuple[str, ...]) -> int:
        lowered = text.lower()
        return sum(lowered.count(term) for term in terms)

    @staticmethod
    def _effective_dt(row: Any) -> datetime:
        return row.published_at or row.created_at or datetime.now(timezone.utc)

    @classmethod
    def _recency_weight(cls, timestamp: datetime, lookback_days: int) -> float:
        age_days = max(0.0, (datetime.now(timezone.utc) - timestamp).total_seconds() / 86400.0)
        half_life = max(7.0, float(lookback_days))
        return math.exp(-age_days / half_life)

    @classmethod
    def _story_text(cls, row: Any) -> str:
        return " ".join(
            part.strip()
            for part in [row.title or "", row.summary or "", row.content or ""]
            if part and part.strip()
        )

    @classmethod
    def _content_hash(cls, row: Any) -> str:
        raw = cls._story_text(row).encode("utf-8", errors="ignore")
        return hashlib.sha1(raw).hexdigest()

    @classmethod
    def estimate_story_signals(cls, row: Any, source_type: str) -> dict[str, float]:
        text = cls._story_text(row)
        title = (row.title or "").strip()
        source_count = int(getattr(row, "source_count", 0) or 0)
        story_count = int(getattr(row, "story_count", 0) or 0)
        confidence_level = (getattr(row, "confidence_level", None) or "").lower()

        official_hits = cls._count_hits(text, OFFICIAL_TERMS)
        document_hits = cls._count_hits(text, DOCUMENT_TERMS)
        primary_hits = cls._count_hits(text, PRIMARY_SOURCE_TERMS)
        aggregation_hits = cls._count_hits(text, AGGREGATION_TERMS)
        uncertain_hits = cls._count_hits(text, UNCERTAIN_TERMS)
        loaded_hits = cls._count_hits(text, LOADED_TERMS)
        clickbait_hits = cls._count_hits(title, CLICKBAIT_TERMS)
        quote_hits = text.count('"') + text.count("“") + text.count("”")
        numeric_hits = len(re.findall(r"\b\d[\d,./:-]*\b", text))
        named_source_hits = len(re.findall(r"\b(?:Minister|Prime Minister|Spokesperson|Mayor|Secretary|Chief|Court|Commission)\b", text, flags=re.I))
        uppercase_ratio = 0.0
        alpha_chars = [char for char in title if char.isalpha()]
        if alpha_chars:
            uppercase_ratio = sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)

        corroboration_strength = 0.24
        if source_count > 1:
            corroboration_strength = 0.48 + min(0.38, (source_count - 1) * 0.1)
        if story_count > 3:
            corroboration_strength += 0.06
        if confidence_level in {"corroborated", "well_corroborated", "highly_corroborated"}:
            corroboration_strength += 0.08
        corroboration_strength = cls._clip(corroboration_strength)

        aggregation_penalty = cls._clip(
            0.12
            + min(0.45, aggregation_hits * 0.08)
            + (0.15 if source_type == "wire" else 0.0)
            + (0.12 if source_count <= 1 and quote_hits == 0 else 0.0)
            - min(0.15, primary_hits * 0.05)
        )

        sensationalism_penalty = cls._clip(
            0.06
            + min(0.35, loaded_hits * 0.12)
            + min(0.18, clickbait_hits * 0.18)
            + (0.12 if title.count("!") >= 1 else 0.0)
            + (0.08 if title.count("?") >= 1 else 0.0)
            + max(0.0, uppercase_ratio - 0.35) * 0.4
        )

        evidence_quality = cls._clip(
            0.18
            + min(0.25, official_hits * 0.05)
            + min(0.18, document_hits * 0.05)
            + min(0.12, primary_hits * 0.04)
            + min(0.1, numeric_hits * 0.01)
            + min(0.1, quote_hits * 0.02)
            + min(0.08, named_source_hits * 0.03)
            + corroboration_strength * 0.18
            - aggregation_penalty * 0.18
        )

        primary_proximity = cls._clip(
            0.1
            + min(0.25, primary_hits * 0.08)
            + min(0.18, official_hits * 0.04)
            + min(0.16, document_hits * 0.04)
            + min(0.12, named_source_hits * 0.05)
            + min(0.08, quote_hits * 0.02)
            - aggregation_penalty * 0.15
        )

        uncertainty_hygiene = 0.58
        if uncertain_hits > 0:
            uncertainty_hygiene = cls._clip(0.72 + min(0.18, uncertain_hits * 0.04) - sensationalism_penalty * 0.18)
        elif sensationalism_penalty > 0.35 and source_count <= 1:
            uncertainty_hygiene = 0.34

        discipline_signal = cls._clip(
            0.34 * corroboration_strength
            + 0.24 * evidence_quality
            + 0.16 * primary_proximity
            + 0.14 * (1.0 - aggregation_penalty)
            + 0.06 * (1.0 - sensationalism_penalty)
            + 0.06 * uncertainty_hygiene
        )

        return {
            "corroboration_strength": round(corroboration_strength, 4),
            "evidence_quality": round(evidence_quality, 4),
            "primary_proximity": round(primary_proximity, 4),
            "aggregation_penalty": round(aggregation_penalty, 4),
            "sensationalism_penalty": round(sensationalism_penalty, 4),
            "uncertainty_hygiene": round(uncertainty_hygiene, 4),
            "discipline_signal": round(discipline_signal, 4),
        }

    @staticmethod
    def map_reliability_letter(score: float, *, provisional: bool) -> str:
        if score >= 0.86:
            letter = "A"
        elif score >= 0.72:
            letter = "B"
        elif score >= 0.56:
            letter = "C"
        elif score >= 0.44:
            letter = "D"
        else:
            letter = "E"
        if provisional and letter == "A":
            return "B"
        return letter

    @staticmethod
    def map_sourcing_number(score: float) -> int:
        if score >= 0.82:
            return 1
        if score >= 0.68:
            return 2
        if score >= 0.54:
            return 3
        return 4

    @staticmethod
    def compute_confidence_band(sample_size: int) -> float:
        if sample_size <= 0:
            return 18.0
        return round(max(3.0, min(18.0, 18.0 / math.sqrt(sample_size))), 1)

    @staticmethod
    def build_reason_line(
        *,
        corroboration_strength: float,
        evidence_quality: float,
        primary_proximity: float,
        aggregation_penalty: float,
        sensationalism_penalty: float,
        provisional: bool,
        openai_partial: bool,
    ) -> str:
        strengths: list[str] = []
        cautions: list[str] = []

        if corroboration_strength >= 0.72:
            strengths.append("strong multi-source corroboration")
        elif corroboration_strength >= 0.55:
            strengths.append("moderate corroboration")

        if evidence_quality >= 0.7:
            strengths.append("solid evidence cues")
        elif primary_proximity >= 0.65:
            strengths.append("frequent primary-source references")

        if aggregation_penalty >= 0.55:
            cautions.append("high aggregation dependence")
        elif aggregation_penalty >= 0.4:
            cautions.append("moderate pickup/rewrite behavior")

        if sensationalism_penalty >= 0.42:
            cautions.append("headline inflation risk")

        text = ", ".join(strengths) if strengths else "recent newsroom behavior is mixed"
        if cautions:
            text = f"{text}; caution: {', '.join(cautions)}"
        if provisional:
            text = f"{text}. Provisional due to limited recent sample."
        elif openai_partial:
            text = f"{text}. Automated rating used heuristics-first scoring."
        return text[:280]

    async def _fetch_candidates(
        self,
        *,
        source_id: Optional[str],
        limit: int,
        lookback_days: int,
    ) -> list[SourceCandidate]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        effective_ts = func.coalesce(Story.published_at, Story.created_at)

        query = (
            select(
                Story.source_id.label("source_id"),
                func.coalesce(func.max(Story.source_name), Story.source_id).label("source_name"),
                func.count(Story.id).label("story_count"),
                func.max(effective_ts).label("latest_story_at"),
            )
            .where(
                or_(
                    Story.published_at >= cutoff,
                    and_(Story.published_at.is_(None), Story.created_at >= cutoff),
                ),
                Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]),
            )
            .group_by(Story.source_id)
        )
        if source_id:
            query = query.where(Story.source_id == source_id)

        query = query.order_by(func.count(Story.id).desc(), func.max(effective_ts).desc()).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()
        return [
            SourceCandidate(
                source_id=str(row.source_id),
                source_name=str(row.source_name or row.source_id),
                source_type=self.classify_source_type(str(row.source_id), str(row.source_name or row.source_id)),
                story_count=int(row.story_count or 0),
                latest_story_at=row.latest_story_at,
            )
            for row in rows
        ]

    async def ensure_source_rows(self, *, limit: int = 20, lookback_days: int = 90) -> None:
        candidates = await self._fetch_candidates(source_id=None, limit=max(limit, 20), lookback_days=lookback_days)
        if not candidates:
            return

        candidate_ids = [candidate.source_id for candidate in candidates]
        existing_result = await self.db.execute(
            select(SourceReliability).where(SourceReliability.source_id.in_(candidate_ids))
        )
        existing_by_id = {row.source_id: row for row in existing_result.scalars().all()}

        changed = False
        for candidate in candidates:
            source = existing_by_id.get(candidate.source_id)
            if source is None:
                source = SourceReliability(
                    source_id=candidate.source_id,
                    source_name=candidate.source_name,
                    source_type=candidate.source_type,
                    reliability_rating="C",
                    credibility_rating=3,
                    confidence_score=55,
                    total_stories=candidate.story_count,
                    notes="Awaiting automated source reliability recompute.",
                )
                self.db.add(source)
                existing_by_id[candidate.source_id] = source
                changed = True
                continue

            if source.source_name != candidate.source_name:
                source.source_name = candidate.source_name
                changed = True
            if source.source_type != candidate.source_type:
                source.source_type = candidate.source_type
                changed = True
            if source.total_stories != candidate.story_count:
                source.total_stories = candidate.story_count
                changed = True

        if changed:
            await self.db.commit()

    async def _fetch_source_stories(self, source_id: str, lookback_days: int, limit: int = 200) -> list[Any]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        effective_ts = func.coalesce(Story.published_at, Story.created_at)
        query = (
            select(
                Story.id,
                Story.title,
                Story.summary,
                Story.content,
                Story.url,
                Story.language,
                Story.published_at,
                Story.created_at,
                Story.cluster_id,
                Story.source_name,
                StoryCluster.source_count,
                StoryCluster.story_count,
                StoryCluster.confidence_level,
            )
            .outerjoin(StoryCluster, Story.cluster_id == StoryCluster.id)
            .where(
                Story.source_id == source_id,
                Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]),
                or_(
                    Story.published_at >= cutoff,
                    and_(Story.published_at.is_(None), Story.created_at >= cutoff),
                ),
            )
            .order_by(effective_ts.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.all())

    async def _openai_enrichment_enabled(self) -> bool:
        return self.openai.available and self.openai.settings.openai_source_reliability_enabled

    async def _enrich_story_with_openai(self, row: Any, heuristic: dict[str, float]) -> tuple[dict[str, float], Optional[str], bool]:
        if not await self._openai_enrichment_enabled():
            return heuristic, None, False

        text = self._story_text(row)
        if not text:
            return heuristic, None, False

        content_hash = self._content_hash(row)
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "evidence_quality": {"type": "number"},
                "primary_proximity": {"type": "number"},
                "aggregation_penalty": {"type": "number"},
                "sensationalism_penalty": {"type": "number"},
                "uncertainty_hygiene": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": [
                "evidence_quality",
                "primary_proximity",
                "aggregation_penalty",
                "sensationalism_penalty",
                "uncertainty_hygiene",
                "reason",
            ],
        }
        try:
            result = await self.openai.json_completion(
                system_prompt=(
                    "You score news sourcing quality on a 0-1 scale. Be conservative. "
                    "Prefer the article text itself, not outlet reputation. "
                    "Higher evidence_quality means stronger documentary or attributed support. "
                    "Higher primary_proximity means closer to official records, documents, or direct participants. "
                    "Higher aggregation_penalty means more rewritten or pickup-style reporting. "
                    "Higher sensationalism_penalty means clickbait or exaggerated framing. "
                    "Higher uncertainty_hygiene means the article is honest about uncertainty."
                ),
                user_prompt=(
                    f"Story id: {row.id}\n"
                    f"Title: {row.title or ''}\n"
                    f"Summary: {(row.summary or '')[:500]}\n"
                    f"Body: {(row.content or '')[:1600]}\n"
                    f"Cluster source count: {int(getattr(row, 'source_count', 0) or 0)}\n"
                    f"Heuristic seed: {heuristic}\n"
                    "Return calibrated scores only."
                ),
                schema_name="source_reliability_story_score",
                schema=schema,
                max_completion_tokens=180,
                cache_scope=f"source-reliability:{row.id}:{content_hash}",
            )
        except OpenAIUsageLimitExceeded:
            logger.info("OpenAI budget cap hit during source reliability scoring")
            return heuristic, None, True
        except Exception:
            logger.warning("OpenAI source reliability enrichment failed for %s", row.id, exc_info=True)
            return heuristic, None, True

        blended = dict(heuristic)
        for key in (
            "evidence_quality",
            "primary_proximity",
            "aggregation_penalty",
            "sensationalism_penalty",
            "uncertainty_hygiene",
        ):
            if key in result:
                blended[key] = round((heuristic[key] * 0.65) + (self._clip(float(result[key])) * 0.35), 4)
        blended["discipline_signal"] = round(
            self._clip(
                0.34 * blended["corroboration_strength"]
                + 0.24 * blended["evidence_quality"]
                + 0.16 * blended["primary_proximity"]
                + 0.14 * (1.0 - blended["aggregation_penalty"])
                + 0.06 * (1.0 - blended["sensationalism_penalty"])
                + 0.06 * blended["uncertainty_hygiene"]
            ),
            4,
        )
        return blended, str(result.get("reason") or "").strip() or None, False

    async def _score_candidate(self, candidate: SourceCandidate, *, lookback_days: int) -> Optional[SourceProfile]:
        story_rows = await self._fetch_source_stories(candidate.source_id, lookback_days=lookback_days)
        if not story_rows:
            return None

        total_weight = 0.0
        weighted_discipline = 0.0
        weighted_corroboration = 0.0
        weighted_evidence = 0.0
        weighted_primary = 0.0
        weighted_aggregation = 0.0
        weighted_sensationalism = 0.0
        weighted_uncertainty = 0.0
        openai_used = 0
        openai_partial = False
        story_samples: list[dict[str, Any]] = []

        ambiguous_budget = self.openai.settings.openai_source_reliability_story_sample_size

        for row in story_rows:
            heuristic = self.estimate_story_signals(row, candidate.source_type)
            should_enrich = (
                ambiguous_budget > 0
                and (
                    0.4 <= heuristic["evidence_quality"] <= 0.72
                    or 0.35 <= heuristic["primary_proximity"] <= 0.68
                    or heuristic["aggregation_penalty"] >= 0.45
                )
            )
            story_signal = heuristic
            openai_reason = None
            if should_enrich:
                story_signal, openai_reason, partial = await self._enrich_story_with_openai(row, heuristic)
                if partial:
                    openai_partial = True
                elif story_signal is not heuristic:
                    ambiguous_budget -= 1
                    openai_used += 1

            weight = self._recency_weight(self._effective_dt(row), lookback_days)
            total_weight += weight
            weighted_discipline += weight * story_signal["discipline_signal"]
            weighted_corroboration += weight * story_signal["corroboration_strength"]
            weighted_evidence += weight * story_signal["evidence_quality"]
            weighted_primary += weight * story_signal["primary_proximity"]
            weighted_aggregation += weight * story_signal["aggregation_penalty"]
            weighted_sensationalism += weight * story_signal["sensationalism_penalty"]
            weighted_uncertainty += weight * story_signal["uncertainty_hygiene"]

            if len(story_samples) < 5:
                story_samples.append(
                    {
                        "story_id": str(row.id),
                        "title": row.title,
                        "published_at": self._effective_dt(row).isoformat(),
                        "signals": story_signal,
                        "openai_reason": openai_reason,
                    }
                )

        if total_weight <= 0:
            return None

        prior_mean = 0.78
        prior_weight = 8.0
        sample_size = len(story_rows)
        discipline_score = ((prior_weight * prior_mean) + weighted_discipline) / (prior_weight + total_weight)
        evidence_score = weighted_evidence / total_weight
        primary_score = weighted_primary / total_weight
        aggregation_score = weighted_aggregation / total_weight
        sensationalism_score = weighted_sensationalism / total_weight
        uncertainty_score = weighted_uncertainty / total_weight
        reliability_effective = self._clip(0.35 + (0.55 * discipline_score))
        sourcing_score = self._clip(
            0.50
            + (0.35 * evidence_score)
            + (0.25 * primary_score)
            - (0.08 * aggregation_score)
        )
        effective_score = self._clip(
            (0.58 * reliability_effective)
            + (0.42 * sourcing_score)
        )
        provisional = sample_size < 15
        reliability_rating = self.map_reliability_letter(reliability_effective, provisional=provisional)
        credibility_rating = self.map_sourcing_number(sourcing_score)
        confidence_score = int(round(self._clip(effective_score) * 100))
        confidence_band = self.compute_confidence_band(sample_size)

        reason_line = self.build_reason_line(
            corroboration_strength=weighted_corroboration / total_weight if total_weight else 0.0,
            evidence_quality=evidence_score,
            primary_proximity=primary_score,
            aggregation_penalty=aggregation_score,
            sensationalism_penalty=sensationalism_score,
            provisional=provisional,
            openai_partial=openai_partial and openai_used == 0,
        )

        metrics = {
            "automated_rating": {
                "reliability_rating": reliability_rating,
                "credibility_rating": credibility_rating,
                "confidence_score": confidence_score,
                "notes": reason_line,
            },
            "provisional": provisional,
            "sample_size": sample_size,
            "confidence_band": confidence_band,
            "score_breakdown": {
                "discipline": round(discipline_score, 4),
                "reliability_effective": round(reliability_effective, 4),
                "sourcing_quality": round(sourcing_score, 4),
                "corroboration_strength": round(weighted_corroboration / total_weight, 4),
                "evidence_quality": round(evidence_score, 4),
                "primary_proximity": round(primary_score, 4),
                "aggregation_penalty": round(aggregation_score, 4),
                "sensationalism_penalty": round(sensationalism_score, 4),
                "uncertainty_hygiene": round(uncertainty_score, 4),
            },
            "openai": {
                "enabled": await self._openai_enrichment_enabled(),
                "stories_enriched": openai_used,
                "partial_fallback": openai_partial,
            },
            "story_samples": story_samples,
            "last_story_at": candidate.latest_story_at.isoformat() if candidate.latest_story_at else None,
            "reason_line": reason_line,
        }

        return SourceProfile(
            reliability_rating=reliability_rating,
            credibility_rating=credibility_rating,
            confidence_score=confidence_score,
            notes=reason_line,
            metrics=metrics,
        )

    @staticmethod
    def _apply_automated_rating(source: SourceReliability, profile: SourceProfile) -> None:
        source.reliability_rating = profile.reliability_rating
        source.credibility_rating = profile.credibility_rating
        source.confidence_score = profile.confidence_score
        source.notes = profile.notes

    @staticmethod
    def restore_automated_rating(source: SourceReliability) -> None:
        metrics = source.automation_metrics or {}
        automated = metrics.get("automated_rating") or {}
        source.reliability_rating = automated.get("reliability_rating", source.reliability_rating)
        source.credibility_rating = automated.get("credibility_rating", source.credibility_rating)
        source.confidence_score = automated.get("confidence_score", source.confidence_score)
        source.notes = automated.get("notes", source.notes)

    async def recompute_active_sources(
        self,
        *,
        source_id: Optional[str] = None,
        limit: int = 20,
        lookback_days: int = 90,
        force: bool = False,
    ) -> dict[str, Any]:
        await self.ensure_source_rows(limit=limit, lookback_days=lookback_days)
        candidates = await self._fetch_candidates(source_id=source_id, limit=limit, lookback_days=lookback_days)
        if not candidates:
            return {"processed": 0, "updated": 0, "skipped": 0}

        source_ids = [candidate.source_id for candidate in candidates]
        existing_result = await self.db.execute(
            select(SourceReliability).where(SourceReliability.source_id.in_(source_ids))
        )
        existing_by_id = {row.source_id: row for row in existing_result.scalars().all()}

        updated = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        for candidate in candidates:
            source = existing_by_id.get(candidate.source_id)
            if source is None:
                continue

            source.source_name = candidate.source_name
            source.source_type = candidate.source_type
            source.total_stories = candidate.story_count

            if (
                not force
                and source.automation_updated_at
                and candidate.latest_story_at
                and candidate.latest_story_at <= source.automation_updated_at
                and source.automation_metrics
            ):
                skipped += 1
                continue

            profile = await self._score_candidate(candidate, lookback_days=lookback_days)
            if profile is None:
                skipped += 1
                continue

            source.automation_metrics = profile.metrics
            source.automation_updated_at = now
            if not source.override_pinned:
                self._apply_automated_rating(source, profile)
            updated += 1

        await self.db.commit()
        return {
            "processed": len(candidates),
            "updated": updated,
            "skipped": skipped,
        }
