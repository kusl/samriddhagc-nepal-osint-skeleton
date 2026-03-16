#!/usr/bin/env python3
"""
Backfill story_entity_links from existing StoryFeature.title_entities.

This script populates the story_entity_links table by:
1. Reading all story_features with title_entities populated
2. Mapping canonical_ids to political_entities
3. Creating StoryEntityLink records for each match
4. Updating mention counts on political_entities

Usage:
    cd backend-v5
    python scripts/backfill_entity_links.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, update
from sqlalchemy.dialects.postgresql import insert
from app.core.database import AsyncSessionLocal
from app.models.story import Story
from app.models.story_feature import StoryFeature
from app.models.political_entity import PoliticalEntity, EntityTrend
from app.models.story_entity_link import StoryEntityLink


async def get_entity_id_map(db) -> dict[str, str]:
    """Build a map of canonical_id -> entity UUID."""
    result = await db.execute(
        select(PoliticalEntity.canonical_id, PoliticalEntity.id)
    )
    return {row[0]: row[1] for row in result.all()}


async def backfill_entity_links():
    """Populate story_entity_links from existing title_entities."""
    print("=" * 70)
    print("Backfilling Story-Entity Links")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        # Get entity ID map
        entity_map = await get_entity_id_map(db)
        print(f"Found {len(entity_map)} political entities in KB")

        if not entity_map:
            print("ERROR: No political entities found. Run seed_political_entities.py first!")
            return

        # Get all stories with title_entities
        result = await db.execute(
            select(StoryFeature.story_id, StoryFeature.title_entities, Story.published_at)
            .join(Story, Story.id == StoryFeature.story_id)
            .where(StoryFeature.title_entities.isnot(None))
            .where(func.array_length(StoryFeature.title_entities, 1) > 0)
        )
        stories_with_entities = result.all()

        print(f"Found {len(stories_with_entities)} stories with title_entities")

        # Track stats
        links_created = 0
        links_skipped = 0
        unmatched_entities = defaultdict(int)

        # Process in batches
        batch_size = 100
        batch = []

        for story_id, title_entities, published_at in stories_with_entities:
            for canonical_id in title_entities:
                entity_id = entity_map.get(canonical_id)

                if not entity_id:
                    unmatched_entities[canonical_id] += 1
                    continue

                batch.append({
                    "story_id": story_id,
                    "entity_id": entity_id,
                    "is_title_mention": True,
                    "mention_count": 1,
                    "confidence": 0.95,  # High confidence for title matches
                })

                if len(batch) >= batch_size:
                    # Use INSERT ... ON CONFLICT DO NOTHING for upsert
                    stmt = insert(StoryEntityLink).values(batch)
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["story_id", "entity_id"]
                    )
                    result = await db.execute(stmt)
                    await db.commit()
                    links_created += result.rowcount
                    links_skipped += len(batch) - result.rowcount
                    batch = []

        # Process remaining batch
        if batch:
            stmt = insert(StoryEntityLink).values(batch)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["story_id", "entity_id"]
            )
            result = await db.execute(stmt)
            await db.commit()
            links_created += result.rowcount
            links_skipped += len(batch) - result.rowcount

        print(f"\nCreated {links_created} story-entity links")
        print(f"Skipped {links_skipped} duplicate links")

        if unmatched_entities:
            print(f"\nUnmatched canonical IDs (need to add to KB):")
            for canonical_id, count in sorted(unmatched_entities.items(), key=lambda x: -x[1]):
                print(f"  {canonical_id}: {count} occurrences")

        # Update mention counts
        print("\nUpdating entity mention counts...")
        await update_mention_counts(db)


async def update_mention_counts(db):
    """Update mention statistics on political_entities."""
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    # Get all entities
    result = await db.execute(select(PoliticalEntity))
    entities = result.scalars().all()

    for entity in entities:
        # Total mentions
        total_result = await db.execute(
            select(func.count(StoryEntityLink.id))
            .where(StoryEntityLink.entity_id == entity.id)
        )
        total_mentions = total_result.scalar() or 0

        # Mentions in last 24h
        result_24h = await db.execute(
            select(func.count(StoryEntityLink.id))
            .where(StoryEntityLink.entity_id == entity.id)
            .where(StoryEntityLink.created_at >= cutoff_24h)
        )
        mentions_24h = result_24h.scalar() or 0

        # Mentions in last 7d
        result_7d = await db.execute(
            select(func.count(StoryEntityLink.id))
            .where(StoryEntityLink.entity_id == entity.id)
            .where(StoryEntityLink.created_at >= cutoff_7d)
        )
        mentions_7d = result_7d.scalar() or 0

        # Get last mention timestamp
        last_mention_result = await db.execute(
            select(StoryEntityLink.created_at)
            .where(StoryEntityLink.entity_id == entity.id)
            .order_by(StoryEntityLink.created_at.desc())
            .limit(1)
        )
        last_mention_row = last_mention_result.first()
        last_mentioned_at = last_mention_row[0] if last_mention_row else None

        # Calculate trend
        # Simple heuristic: rising if 24h > avg daily rate from 7d
        avg_daily = mentions_7d / 7 if mentions_7d > 0 else 0
        if mentions_24h > avg_daily * 1.5 and mentions_24h > 2:
            trend = EntityTrend.RISING
        elif mentions_24h < avg_daily * 0.5 and avg_daily > 0:
            trend = EntityTrend.FALLING
        else:
            trend = EntityTrend.STABLE

        # Update entity
        await db.execute(
            update(PoliticalEntity)
            .where(PoliticalEntity.id == entity.id)
            .values(
                total_mentions=total_mentions,
                mentions_24h=mentions_24h,
                mentions_7d=mentions_7d,
                trend=trend,
                last_mentioned_at=last_mentioned_at,
                updated_at=now,
            )
        )

        if total_mentions > 0:
            print(f"  {entity.canonical_id:20} total={total_mentions:4} 24h={mentions_24h:3} 7d={mentions_7d:4} trend={trend.value}")

    await db.commit()
    print("\nMention counts updated successfully!")


async def main():
    """Main entry point."""
    await backfill_entity_links()

    # Print summary
    async with AsyncSessionLocal() as db:
        link_count = await db.execute(
            select(func.count(StoryEntityLink.id))
        )
        total_links = link_count.scalar() or 0

        entity_count = await db.execute(
            select(func.count(PoliticalEntity.id))
            .where(PoliticalEntity.total_mentions > 0)
        )
        active_entities = entity_count.scalar() or 0

        print("\n" + "=" * 70)
        print("Backfill Complete!")
        print("=" * 70)
        print(f"Total story-entity links: {total_links}")
        print(f"Entities with mentions: {active_entities}")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
