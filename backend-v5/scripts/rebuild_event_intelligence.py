#!/usr/bin/env python3
"""
Rebuild recent event-intelligence fields for stories, tweets, and clusters.

This is a local/operator tool for:
- re-extracting story enrichment fields
- reclustering recent stories into event objects
- relinking recent tweets into those events
- refreshing operational cluster metrics after social linkage
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ANALYSIS_DIR = ROOT / "analysis_output" / "event_intelligence"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild recent event-intelligence fields.")
    parser.add_argument("--hours", type=int, default=168, help="Recent window to rebuild.")
    parser.add_argument("--story-limit", type=int, default=2500, help="Max recent stories to re-enrich.")
    parser.add_argument("--tweet-limit", type=int, default=1200, help="Max recent tweets to relink.")
    parser.add_argument("--skip-clustering", action="store_true", help="Skip the cluster rebuild step.")
    return parser.parse_args()


async def upsert_story_features(session: AsyncSession, hours: int, story_limit: int) -> dict:
    from app.models.story import Story
    from app.models.story_feature import StoryFeature
    from app.services.clustering.feature_extractor import get_feature_extractor

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    extractor = get_feature_extractor()
    result = await session.execute(
        select(Story)
        .options(selectinload(Story.features))
        .where(
            Story.published_at >= cutoff,
            Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]),
        )
        .order_by(Story.published_at.desc().nullslast())
        .limit(story_limit)
    )
    stories = list(result.scalars().all())

    updated = 0
    created = 0
    for idx, story in enumerate(stories, start=1):
        features = extractor.extract(
            title=story.title,
            summary=story.summary,
            content=story.content,
            story_id=str(story.id),
            published_at=story.published_at,
        )
        record = story.features
        if record is None:
            record = StoryFeature(story_id=story.id)
            session.add(record)
            created += 1
        else:
            updated += 1

        record.content_minhash = features.content_minhash
        record.title_tokens = features.title_tokens
        record.districts = features.districts
        record.provinces = features.provinces
        record.municipalities = features.municipalities
        record.place_mentions = features.place_mentions
        record.constituencies = features.constituencies
        record.geo_confidence = features.geo_confidence
        record.primary_province = features.primary_province
        record.primary_municipality = features.primary_municipality
        record.key_terms = features.key_terms
        record.named_people = features.named_people or None
        record.named_orgs = features.named_orgs or None
        record.named_parties = features.named_parties or None
        record.named_infrastructure = features.named_infrastructure or None
        record.international_countries = features.international_countries
        record.topic = features.topic
        record.event_type = features.event_type
        record.operational_domain = features.operational_domain
        record.event_time = features.event_time
        record.freshness_score = features.freshness_score
        record.title_district = features.title_district
        record.title_country = features.title_country
        record.title_entities = features.title_entities or None
        record.title_action = features.title_action

        story.districts = features.districts or None
        story.provinces = features.provinces or None

        if idx % 200 == 0:
            await session.commit()

    await session.commit()
    return {"stories_scanned": len(stories), "features_created": created, "features_updated": updated}


async def summarize_recent_clusters(session: AsyncSession, hours: int) -> dict:
    from app.models.story_cluster import StoryCluster

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await session.execute(
        select(StoryCluster).where(StoryCluster.last_updated >= cutoff)
    )
    clusters = list(result.scalars().all())
    if not clusters:
        return {
            "recent_clusters": 0,
            "immediate": 0,
            "monitor": 0,
            "geo_known_share": 0.0,
            "event_type_known_share": 0.0,
            "avg_intelligence_score": 0.0,
            "avg_social_posts": 0.0,
        }

    immediate = sum(1 for c in clusters if c.actionability == "immediate")
    monitor = sum(1 for c in clusters if c.actionability == "monitor")
    geo_known = sum(1 for c in clusters if c.primary_province)
    event_type_known = sum(1 for c in clusters if c.event_type)
    avg_intelligence = sum(float(c.intelligence_score or 0.0) for c in clusters) / len(clusters)
    avg_social = sum(int(c.social_post_count or 0) for c in clusters) / len(clusters)
    top_clusters = sorted(
        clusters,
        key=lambda c: (float(c.intelligence_score or 0.0), c.story_count, c.source_count),
        reverse=True,
    )[:10]
    return {
        "recent_clusters": len(clusters),
        "immediate": immediate,
        "monitor": monitor,
        "geo_known_share": round(geo_known / len(clusters), 4),
        "event_type_known_share": round(event_type_known / len(clusters), 4),
        "avg_intelligence_score": round(avg_intelligence, 2),
        "avg_social_posts": round(avg_social, 2),
        "top_clusters": [
            {
                "headline": c.headline,
                "province": c.primary_province,
                "district": c.primary_district,
                "event_type": c.event_type,
                "severity": c.severity,
                "actionability": c.actionability,
                "intelligence_score": float(c.intelligence_score or 0.0),
                "story_count": c.story_count,
                "source_count": c.source_count,
                "social_post_count": c.social_post_count,
                "official_confirmation_count": c.official_confirmation_count,
            }
            for c in top_clusters
        ],
    }


async def main() -> None:
    args = parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(database_url, echo=False)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        from app.services.clustering.clustering_service import ClusteringService
        from app.services.twitter_service import TwitterService

        feature_stats = await upsert_story_features(session, args.hours, args.story_limit)

        clustering_stats = {"skipped": True}
        if not args.skip_clustering:
            clustering_service = ClusteringService(
                db=session,
                use_hybrid_semantic=True,
                use_llm_validation=False,
            )
            clustering_stats = await clustering_service.cluster_stories(hours=args.hours, min_cluster_size=2)
        else:
            clustering_service = ClusteringService(db=session, use_hybrid_semantic=True, use_llm_validation=False)

        twitter_service = TwitterService(session)
        tweet_stats = await twitter_service.backfill_recent_tweet_links(
            hours=args.hours,
            limit=args.tweet_limit,
        )
        cluster_refresh_stats = await clustering_service.refresh_recent_cluster_operational_fields(hours=args.hours)
        cluster_summary = await summarize_recent_clusters(session, args.hours)

    await engine.dispose()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours": args.hours,
        "feature_stats": feature_stats,
        "clustering_stats": clustering_stats,
        "tweet_stats": tweet_stats,
        "cluster_refresh_stats": cluster_refresh_stats,
        "cluster_summary": cluster_summary,
    }

    json_path = ANALYSIS_DIR / "rebuild_report.json"
    md_path = ANALYSIS_DIR / "rebuild_report.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# Event Intelligence Rebuild",
                "",
                f"- generated_at: {report['generated_at']}",
                f"- hours: {report['hours']}",
                "",
                "## Feature refresh",
                f"- stories_scanned: {feature_stats['stories_scanned']}",
                f"- features_created: {feature_stats['features_created']}",
                f"- features_updated: {feature_stats['features_updated']}",
                "",
                "## Clustering",
                *(f"- {k}: {v}" for k, v in clustering_stats.items()),
                "",
                "## Tweet linkage",
                *(f"- {k}: {v}" for k, v in tweet_stats.items()),
                "",
                "## Recent cluster summary",
                *(f"- {k}: {v}" for k, v in cluster_summary.items() if k != "top_clusters"),
                "",
                "## Top clusters",
                *[
                    f"- {item['actionability']} | {item['intelligence_score']:.1f} | {item['province'] or 'unknown'} | {item['event_type'] or 'unknown'} | {item['headline']}"
                    for item in cluster_summary.get("top_clusters", [])
                ],
            ]
        ),
        encoding="utf-8",
    )

    print(json_path)
    print(md_path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
