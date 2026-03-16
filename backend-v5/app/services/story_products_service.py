"""Services for event-level and narrative-level dashboard products."""
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from typing import Optional, Iterable
from uuid import uuid4

import numpy as np
from sqlalchemy import select, delete, text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.story import Story
from app.models.story_cluster import StoryCluster
from app.models.story_narrative import StoryNarrative, StoryNarrativeCluster
from app.models.story_feature import StoryFeature
from app.repositories.story_cluster import StoryClusterRepository
from app.services.editorial_control_service import EditorialControlService
from app.services.embeddings.service import EmbeddingService
from app.services.openai_runtime import get_openai_runtime

logger = logging.getLogger(__name__)


def _compute_development_stage(cluster: StoryCluster) -> str:
    if cluster.first_published and cluster.last_updated:
        spread_h = (cluster.last_updated - cluster.first_published).total_seconds() / 3600
        stale_h = (datetime.now(timezone.utc) - cluster.last_updated).total_seconds() / 3600
        if stale_h > 12:
            return "resolved"
        if spread_h > 12 and cluster.source_count >= 4:
            return "mature"
        if spread_h > 3 or cluster.source_count >= 3:
            return "developing"
    return "emerging"


def _severity_score(severity: Optional[str]) -> int:
    return {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
    }.get((severity or "").lower(), 1)


def _safe_story_time(story: Story) -> datetime:
    return story.published_at or story.created_at or datetime.min.replace(tzinfo=timezone.utc)


class DevelopingStoriesService:
    """Event-centric feed: fast-moving clusters with compact stored BLUFs."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StoryClusterRepository(db)
        self.openai = get_openai_runtime()
        self.control_service = EditorialControlService(db)

    async def list_entries(
        self,
        *,
        hours: int = 72,
        limit: int = 15,
        category: Optional[str] = None,
        refresh: bool = False,
    ) -> list[dict]:
        fetch_limit = min(limit * 4, 80)
        try:
            clusters = await self.repo.list_clusters(hours=hours, category=category, limit=fetch_limit)
        except Exception:
            logger.warning("Falling back to legacy-compatible developing-stories query", exc_info=True)
            await self.db.rollback()
            clusters = await self._list_clusters_compat(hours=hours, category=category, limit=fetch_limit)
        ranked = []
        now = datetime.now(timezone.utc)

        for cluster in clusters:
            if cluster.story_count < 2:
                continue
            if cluster.workflow_status == "rejected":
                continue
            stories_sorted = sorted(cluster.stories, key=_safe_story_time)
            recent_cutoff = now - timedelta(hours=6)
            recent_updates = [s for s in stories_sorted if (_safe_story_time(s) >= recent_cutoff)]
            new_sources_6h = len({s.source_id for s in recent_updates if s.source_id})
            update_velocity = len(recent_updates)
            cross_lingual = bool(cluster.cross_lingual_match)
            development_stage = _compute_development_stage(cluster)
            stage_bonus = {
                "emerging": 3.0,
                "developing": 2.0,
                "mature": 1.0,
                "resolved": 0.0,
            }.get(development_stage, 0.0)
            urgency_score = (
                (_severity_score(cluster.analyst_severity or cluster.severity) * 10)
                + (new_sources_6h * 4)
                + (update_velocity * 1.5)
                + stage_bonus
            )
            ranked.append({
                "cluster": cluster,
                "stories_sorted": stories_sorted,
                "new_sources_6h": new_sources_6h,
                "update_velocity": update_velocity,
                "urgency_score": urgency_score,
                "development_stage": development_stage,
                "cross_lingual": cross_lingual,
            })

        ranked.sort(
            key=lambda item: (
                -item["urgency_score"],
                -(item["cluster"].last_updated.timestamp() if item["cluster"].last_updated else 0),
            )
        )

        entries: list[dict] = []
        for item in ranked[:limit]:
            cluster: StoryCluster = item["cluster"]
            bluf = await self._resolve_event_bluf(cluster, allow_generate=refresh)
            timeline = [
                {
                    "source_name": s.source_name or s.source_id,
                    "title": s.title,
                    "published_at": s.published_at,
                    "url": s.url,
                }
                for s in item["stories_sorted"]
            ]
            entries.append({
                "cluster_id": cluster.id,
                "headline": cluster.analyst_headline or cluster.headline,
                "category": cluster.analyst_category or cluster.category,
                "severity": cluster.analyst_severity or cluster.severity,
                "event_type": cluster.event_type,
                "primary_province": cluster.primary_province,
                "primary_district": cluster.primary_district,
                "primary_municipality": cluster.primary_municipality,
                "geo_confidence": cluster.geo_confidence,
                "main_entities": cluster.main_entities or [],
                "story_count": cluster.story_count,
                "source_count": cluster.source_count,
                "first_published": cluster.first_published,
                "last_updated": cluster.last_updated,
                "diversity_score": cluster.diversity_score,
                "confidence_level": cluster.confidence_level,
                "event_confidence": cluster.event_confidence,
                "heat_score": cluster.heat_score,
                "spread_score": cluster.spread_score,
                "novelty_score": cluster.novelty_score,
                "intelligence_score": cluster.intelligence_score,
                "actionability": cluster.actionability,
                "bluf": bluf,
                "development_stage": item["development_stage"],
                "timeline": timeline,
                "new_sources_6h": item["new_sources_6h"],
                "update_velocity": item["update_velocity"],
                "urgency_score": item["urgency_score"],
                "cross_lingual": item["cross_lingual"],
            })
        return entries

    async def _list_clusters_compat(
        self,
        *,
        hours: int,
        category: Optional[str],
        limit: int,
    ) -> list[SimpleNamespace]:
        """Read clusters using only legacy-safe columns.

        Production can temporarily lag the newer event-intelligence schema, so
        this fallback intentionally selects only columns that existed before the
        new event fields landed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cluster_sql_text = """
            SELECT
                id,
                headline,
                summary,
                category,
                severity,
                story_count,
                source_count,
                diversity_score,
                confidence_level,
                first_published,
                last_updated,
                bluf,
                workflow_status,
                analyst_headline,
                analyst_summary,
                analyst_category,
                analyst_severity,
                cross_lingual_match
            FROM story_clusters
            WHERE first_published >= :cutoff
        """
        params = {
            "cutoff": cutoff,
            "limit": limit,
        }
        if category:
            cluster_sql_text += " AND category = :category"
            params["category"] = category
        cluster_sql_text += "\nORDER BY last_updated DESC NULLS LAST\nLIMIT :limit"
        cluster_sql = text(cluster_sql_text)
        cluster_result = await self.db.execute(
            cluster_sql,
            params,
        )
        cluster_rows = cluster_result.mappings().all()
        if not cluster_rows:
            return []

        cluster_ids = [row["id"] for row in cluster_rows]
        story_stmt = (
            select(
                Story.id,
                Story.cluster_id,
                Story.source_id,
                Story.source_name,
                Story.title,
                Story.url,
                Story.published_at,
                Story.created_at,
            )
            .where(Story.cluster_id.in_(bindparam("cluster_ids", expanding=True)))
        )
        story_result = await self.db.execute(story_stmt, {"cluster_ids": cluster_ids})
        story_rows = story_result.all()

        stories_by_cluster: dict = defaultdict(list)
        for row in story_rows:
            story = SimpleNamespace(
                id=row.id,
                cluster_id=row.cluster_id,
                source_id=row.source_id,
                source_name=row.source_name,
                title=row.title,
                url=row.url,
                published_at=row.published_at,
                created_at=row.created_at,
            )
            stories_by_cluster[row.cluster_id].append(story)

        clusters: list[SimpleNamespace] = []
        for row in cluster_rows:
            clusters.append(
                SimpleNamespace(
                    id=row["id"],
                    headline=row["headline"],
                    summary=row["summary"],
                    category=row["category"],
                    severity=row["severity"],
                    story_count=row["story_count"] or 0,
                    source_count=row["source_count"] or 0,
                    diversity_score=row["diversity_score"],
                    confidence_level=row["confidence_level"],
                    first_published=row["first_published"],
                    last_updated=row["last_updated"],
                    bluf=row["bluf"],
                    workflow_status=row["workflow_status"],
                    analyst_headline=row["analyst_headline"],
                    analyst_summary=row["analyst_summary"],
                    analyst_category=row["analyst_category"],
                    analyst_severity=row["analyst_severity"],
                    cross_lingual_match=bool(row["cross_lingual_match"]),
                    stories=stories_by_cluster.get(row["id"], []),
                    event_type=None,
                    primary_province=None,
                    primary_district=None,
                    primary_municipality=None,
                    geo_confidence=None,
                    main_entities=[],
                    event_confidence=None,
                    heat_score=None,
                    spread_score=None,
                    novelty_score=None,
                    intelligence_score=None,
                    actionability=None,
                )
            )
        return clusters

    async def _resolve_event_bluf(self, cluster: StoryCluster, *, allow_generate: bool) -> str:
        if cluster.bluf and len(cluster.bluf.strip()) >= 24:
            return cluster.bluf

        fallback = cluster.summary or cluster.analyst_summary or cluster.headline
        if not allow_generate or not self.openai.developing_stories_enabled:
            return fallback
        if not await self.control_service.is_enabled("developing_story_bluf"):
            return fallback

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "bluf": {"type": "string"},
            },
            "required": ["bluf"],
        }
        top_stories = sorted(cluster.stories, key=_safe_story_time, reverse=True)[:5]
        prompt_lines = [
            "Write a single concise event BLUF for a Nepal OSINT developing-stories feed.",
            "Keep it factual, one sentence, no hype, no speculation.",
            f"Cluster headline: {cluster.analyst_headline or cluster.headline}",
            f"Category: {cluster.analyst_category or cluster.category or 'unknown'}",
            f"Severity: {cluster.analyst_severity or cluster.severity or 'unknown'}",
            "Recent sources:",
        ]
        for story in top_stories:
            prompt_lines.append(f"- {story.source_name or story.source_id}: {story.title}")
        try:
            result = await self.openai.json_completion(
                system_prompt="You write concise event BLUFs for an intelligence dashboard.",
                user_prompt="\n".join(prompt_lines),
                schema_name="developing_story_bluf",
                schema=schema,
                model=self.openai.settings.openai_clustering_model,
                max_completion_tokens=80,
                temperature=0.0,
                cache_scope=f"developing-story:{cluster.id}:{cluster.story_count}:{cluster.source_count}",
            )
            cluster.bluf = result.get("bluf", fallback)
            await self.db.commit()
        except Exception:
            logger.warning("Failed to generate developing-story BLUF for cluster %s", cluster.id, exc_info=True)
            return fallback
        return cluster.bluf or fallback


class StoryTrackerService:
    """Narrative-centric tracker built across clusters, not within one event feed."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StoryClusterRepository(db)
        self.openai = get_openai_runtime()
        self.embedding_service = EmbeddingService(db)
        self.control_service = EditorialControlService(db)

    async def refresh_narratives(
        self,
        *,
        hours: int = 72,
        limit: int = 20,
        force: bool = False,
    ) -> list[StoryNarrative]:
        if not force and not await self.control_service.is_enabled("story_tracker_refresh"):
            return await self.list_narratives(hours=hours, limit=limit)
        clusters = await self._fetch_candidate_clusters(hours=hours, limit=120)
        grouped = await self._group_clusters_into_narratives(clusters)
        existing = await self.list_narratives(hours=max(hours, 168), limit=200)
        existing_meta: dict[tuple[str, ...], dict] = {}
        for narrative in existing:
            cluster_key = tuple(sorted(str(link.cluster_id) for link in narrative.cluster_links))
            existing_meta[cluster_key] = {
                "workflow_status": narrative.workflow_status,
                "review_notes": narrative.review_notes,
                "approved_by_id": narrative.approved_by_id,
                "approved_at": narrative.approved_at,
                "rejected_by_id": narrative.rejected_by_id,
                "rejected_at": narrative.rejected_at,
            }

        await self.db.execute(delete(StoryNarrativeCluster))
        await self.db.execute(delete(StoryNarrative))
        await self.db.flush()

        narratives: list[StoryNarrative] = []
        for group in grouped[:limit]:
            narrative = await self._persist_group(group, existing_meta=existing_meta)
            narratives.append(narrative)

        await self.db.commit()
        return narratives

    async def list_narratives(
        self,
        *,
        hours: int = 72,
        limit: int = 20,
    ) -> list[StoryNarrative]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(StoryNarrative)
            .options(
                selectinload(StoryNarrative.cluster_links)
                .selectinload(StoryNarrativeCluster.cluster)
                .selectinload(StoryCluster.stories)
            )
            .where(StoryNarrative.last_updated >= cutoff)
            .where(StoryNarrative.workflow_status != "rejected")
            .order_by(StoryNarrative.momentum_score.desc(), StoryNarrative.last_updated.desc())
            .limit(limit)
        )
        narratives = list(result.scalars().all())
        return narratives

    async def _fetch_candidate_clusters(self, *, hours: int, limit: int) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(StoryCluster)
            .options(
                selectinload(StoryCluster.stories).selectinload(Story.embedding),
                selectinload(StoryCluster.stories).selectinload(Story.features),
            )
            .where(StoryCluster.first_published >= cutoff)
            .order_by(StoryCluster.last_updated.desc().nullslast())
            .limit(limit)
        )
        clusters = list(result.scalars().all())
        payloads = []
        for cluster in clusters:
            if cluster.story_count < 2:
                continue
            if cluster.workflow_status == "rejected":
                continue
            await self._ensure_cluster_embeddings(cluster)
            embedding = self._mean_story_embedding(cluster.stories)
            if embedding is None:
                continue
            payloads.append({
                "cluster": cluster,
                "embedding": embedding,
                "text": " ".join(filter(None, [cluster.analyst_headline, cluster.headline, cluster.bluf, cluster.summary]))[:1200],
                "regions": self._collect_regions(cluster.stories),
                "entities": self._collect_entities(cluster.stories),
            })
        return payloads

    async def _ensure_cluster_embeddings(self, cluster: StoryCluster) -> None:
        """Backfill a small set of recent story embeddings for tracker grouping."""
        candidate_stories = sorted(
            list(cluster.stories or []),
            key=_safe_story_time,
            reverse=True,
        )[:6]
        for story in candidate_stories:
            if story.embedding and (
                story.embedding.embedding_vector is not None or
                story.embedding.embedding is not None
            ):
                continue
            embedding_record = await self.embedding_service.ensure_story_embedding(
                story_id=story.id,
                title=story.title,
                summary=story.summary,
                content=story.content,
                force=False,
            )
            if embedding_record is not None:
                story.embedding = embedding_record

    async def _group_clusters_into_narratives(self, cluster_payloads: list[dict]) -> list[list[dict]]:
        groups: list[list[dict]] = []
        threshold = self.openai.settings.openai_story_tracker_similarity_threshold

        for payload in cluster_payloads:
            best_index = None
            best_score = -1.0
            for idx, group in enumerate(groups):
                representative = group[0]
                cluster: StoryCluster = payload["cluster"]
                rep_cluster: StoryCluster = representative["cluster"]
                if (cluster.analyst_category or cluster.category) != (rep_cluster.analyst_category or rep_cluster.category):
                    continue
                score = float(np.dot(np.array(payload["embedding"]), np.array(representative["embedding"])))
                if score > best_score:
                    best_score = score
                    best_index = idx

            if best_index is None:
                groups.append([payload])
                continue

            if best_score >= threshold:
                groups[best_index].append(payload)
                continue

            if (
                self.openai.story_tracker_enabled and
                await self.control_service.is_enabled("story_tracker_refresh") and
                best_score >= threshold - 0.08 and
                await self._same_narrative(payload, groups[best_index][0], best_score)
            ):
                groups[best_index].append(payload)
            else:
                groups.append([payload])

        groups.sort(key=lambda g: self._group_momentum(g), reverse=True)
        return groups

    async def _same_narrative(self, candidate: dict, representative: dict, score: float) -> bool:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "same_narrative": {"type": "boolean"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["same_narrative", "confidence", "reason"],
        }
        candidate_cluster: StoryCluster = candidate["cluster"]
        rep_cluster: StoryCluster = representative["cluster"]
        try:
            result = await self.openai.json_completion(
                system_prompt=(
                    "You group event clusters into broader narratives for a Nepal OSINT tracker. "
                    "Narratives can span multiple related events, but must represent one coherent storyline."
                ),
                user_prompt=(
                    f"Representative cluster: {rep_cluster.analyst_headline or rep_cluster.headline}\n"
                    f"Representative BLUF: {rep_cluster.bluf or rep_cluster.summary or ''}\n"
                    f"Candidate cluster: {candidate_cluster.analyst_headline or candidate_cluster.headline}\n"
                    f"Candidate BLUF: {candidate_cluster.bluf or candidate_cluster.summary or ''}\n"
                    f"Category: {candidate_cluster.analyst_category or candidate_cluster.category or 'unknown'}\n"
                    f"Embedding similarity: {score:.3f}"
                ),
                schema_name="story_tracker_same_narrative",
                schema=schema,
                model=self.openai.settings.openai_clustering_model,
                max_completion_tokens=120,
                temperature=0.0,
                cache_scope=f"story-tracker-pair:{candidate_cluster.id}:{rep_cluster.id}",
            )
            return bool(result.get("same_narrative")) and float(result.get("confidence", 0.0)) >= 0.60
        except Exception:
            logger.warning(
                "Failed narrative pair judgment for clusters %s/%s",
                candidate_cluster.id,
                rep_cluster.id,
                exc_info=True,
            )
            return False

    async def _persist_group(self, group: list[dict], *, existing_meta: Optional[dict[tuple[str, ...], dict]] = None) -> StoryNarrative:
        clusters = [item["cluster"] for item in group]
        lead_regions = sorted({region for item in group for region in item["regions"]})[:6]
        lead_entities = sorted({entity for item in group for entity in item["entities"]})[:8]
        label, thesis, direction, confidence = await self._label_group(group)
        first_seen = min((c.first_published for c in clusters if c.first_published), default=None)
        last_updated = max((c.last_updated for c in clusters if c.last_updated), default=None)
        momentum = self._group_momentum(group)
        cluster_key = tuple(sorted(str(c.id) for c in clusters))
        preserved = (existing_meta or {}).get(cluster_key, {})
        narrative = StoryNarrative(
            id=uuid4(),
            category=clusters[0].analyst_category or clusters[0].category,
            label=label,
            thesis=thesis,
            direction=direction,
            momentum_score=momentum,
            confidence=confidence,
            cluster_count=len(clusters),
            lead_regions=lead_regions,
            lead_entities=lead_entities,
            workflow_status=preserved.get("workflow_status", "approved"),
            review_notes=preserved.get("review_notes"),
            approved_by_id=preserved.get("approved_by_id"),
            approved_at=preserved.get("approved_at"),
            rejected_by_id=preserved.get("rejected_by_id"),
            rejected_at=preserved.get("rejected_at"),
            metadata_json={
                "cluster_ids": [str(c.id) for c in clusters],
                "source_count": int(sum(c.source_count for c in clusters)),
                "event_types": sorted({c.event_type for c in clusters if c.event_type}),
                "primary_provinces": sorted({c.primary_province for c in clusters if c.primary_province}),
                "primary_districts": sorted({c.primary_district for c in clusters if c.primary_district}),
            },
            first_seen_at=first_seen,
            last_updated=last_updated,
        )
        self.db.add(narrative)
        await self.db.flush()

        ordered = sorted(
            group,
            key=lambda item: (
                -(item["cluster"].source_count or 0),
                -(item["cluster"].story_count or 0),
            ),
        )
        for idx, item in enumerate(ordered):
            score = float(np.dot(np.array(item["embedding"]), np.array(ordered[0]["embedding"])))
            self.db.add(
                StoryNarrativeCluster(
                    narrative_id=narrative.id,
                    cluster_id=item["cluster"].id,
                    position=idx,
                    similarity_score=score,
                )
            )
        return narrative

    async def _label_group(self, group: list[dict]) -> tuple[str, str, str, Optional[float]]:
        lead_cluster: StoryCluster = sorted(
            (item["cluster"] for item in group),
            key=lambda c: (c.source_count or 0, c.story_count or 0),
            reverse=True,
        )[0]
        fallback_label = (lead_cluster.analyst_headline or lead_cluster.headline)[:100]
        fallback_thesis = lead_cluster.bluf or lead_cluster.summary or fallback_label

        if not self.openai.story_tracker_enabled:
            return fallback_label, fallback_thesis, "stable", None
        if not await self.control_service.is_enabled("story_tracker_refresh"):
            return fallback_label, fallback_thesis, "stable", None

        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "label": {"type": "string"},
                "thesis": {"type": "string"},
                "direction": {"type": "string", "enum": ["rising", "stable", "fragmenting", "cooling"]},
                "confidence": {"type": "number"},
            },
            "required": ["label", "thesis", "direction", "confidence"],
        }
        lines = [
            "Create a strategic narrative label and thesis for these related Nepal OSINT clusters.",
            "This is for a slow-moving story tracker, not a breaking-news feed.",
        ]
        for item in group[:5]:
            cluster = item["cluster"]
            lines.append(f"- {cluster.analyst_headline or cluster.headline}")
            if cluster.bluf:
                lines.append(f"  BLUF: {cluster.bluf}")

        try:
            result = await self.openai.json_completion(
                system_prompt="You write strategic narrative labels for an intelligence dashboard.",
                user_prompt="\n".join(lines),
                schema_name="story_tracker_label",
                schema=schema,
                model=self.openai.settings.openai_clustering_model,
                max_completion_tokens=180,
                temperature=0.0,
                cache_scope="story-tracker-label:" + ":".join(sorted(str(item["cluster"].id) for item in group[:5])),
            )
            return (
                result.get("label", fallback_label),
                result.get("thesis", fallback_thesis),
                result.get("direction", "stable"),
                float(result.get("confidence", 0.0)) if result.get("confidence") is not None else None,
            )
        except Exception:
            logger.warning("Failed to label story-tracker narrative group", exc_info=True)
            return fallback_label, fallback_thesis, "stable", None

    def _group_momentum(self, group: list[dict]) -> float:
        total_sources = sum(item["cluster"].source_count or 0 for item in group)
        total_stories = sum(item["cluster"].story_count or 0 for item in group)
        freshness = max(
            (
                item["cluster"].last_updated.timestamp()
                for item in group
                if item["cluster"].last_updated
            ),
            default=0,
        )
        return (total_sources * 5.0) + (total_stories * 2.0) + (freshness / 100000.0)

    def _mean_story_embedding(self, stories: Iterable[Story]) -> Optional[list[float]]:
        vectors = []
        for story in stories:
            if story.embedding and story.embedding.embedding_vector is not None:
                vectors.append(np.array(story.embedding.embedding_vector, dtype=np.float32))
            elif story.embedding and story.embedding.embedding is not None:
                from app.services.embeddings.text_embedder import bytes_to_embedding
                vectors.append(np.array(bytes_to_embedding(story.embedding.embedding), dtype=np.float32))
        if not vectors:
            return None
        mean_vec = np.mean(vectors, axis=0)
        norm = np.linalg.norm(mean_vec)
        if norm <= 0:
            return None
        return (mean_vec / norm).tolist()

    def _collect_regions(self, stories: Iterable[Story]) -> list[str]:
        regions = set()
        for story in stories:
            for district in story.districts or []:
                regions.add(district)
            for province in story.provinces or []:
                regions.add(province)
            if story.features:
                for municipality in getattr(story.features, "municipalities", None) or []:
                    regions.add(municipality)
        return sorted(regions)

    def _collect_entities(self, stories: Iterable[Story]) -> list[str]:
        entities = Counter()
        for story in stories:
            if not story.features:
                continue
            entities.update(story.features.title_entities or [])
            entities.update(getattr(story.features, "named_people", None) or [])
            entities.update(getattr(story.features, "named_orgs", None) or [])
            entities.update(getattr(story.features, "named_parties", None) or [])
            entities.update(getattr(story.features, "named_infrastructure", None) or [])
        return [name for name, _ in entities.most_common(8)]
