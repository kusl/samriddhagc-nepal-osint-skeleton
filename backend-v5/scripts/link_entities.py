#!/usr/bin/env python3
"""
One-time backfill script: Link satellite records to PoliticalEntity hub.

Run after migration 037:
    cd backend-v5 && venv/bin/python3 scripts/link_entities.py

Phases:
0. Reset all links and delete auto-created entities with Devanagari name_en
1. Link existing PoliticalEntity → Candidate (by name matching)
2. Create new PoliticalEntity for unlinked winners not yet in KB
3. Link MPPerformance → PoliticalEntity (via candidate chain, then name)
4. Link MinisterialPosition → PoliticalEntity (via candidate/MP chain, then name)
5. Link CompanyDirector → PoliticalEntity (name match, threshold 0.80)
6. Absorb enrichments (bio, education, photo, position_history, former_parties)
6b. Fix entity names: replace Devanagari name_en with romanized English from best candidate
7. Backfill StoryEntityLinks for recent stories (last 7 days) using DatabaseEntityExtractor
"""
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, update, delete

from app.core.database import AsyncSessionLocal
from app.models.political_entity import PoliticalEntity, EntityType
from app.models.election import Candidate
from app.models.parliament import MPPerformance
from app.models.ministerial_position import MinisterialPosition
from app.models.company import CompanyDirector
from app.models.story import Story
from app.models.story_entity_link import StoryEntityLink


def _is_nepali(text: str) -> bool:
    """Check if text contains Devanagari characters."""
    return any('\u0900' <= c <= '\u097F' for c in (text or ""))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("link_entities")


async def phase_0_reset():
    """Reset all entity links and delete auto-created entities with Devanagari name_en."""
    async with AsyncSessionLocal() as db:
        logger.info("=" * 60)
        logger.info("Phase 0: Resetting all entity links...")

        # Clear linked_entity_id from all satellite tables
        await db.execute(
            update(Candidate).values(linked_entity_id=None, entity_link_confidence=None)
        )
        cand_count = (await db.execute(select(func.count(Candidate.id)))).scalar()
        logger.info(f"  Cleared linked_entity_id from {cand_count} candidates")

        await db.execute(
            update(MPPerformance).values(linked_entity_id=None, entity_link_confidence=None)
        )
        mp_count = (await db.execute(select(func.count(MPPerformance.id)))).scalar()
        logger.info(f"  Cleared linked_entity_id from {mp_count} MPs")

        await db.execute(
            update(MinisterialPosition).values(linked_entity_id=None, entity_link_confidence=None)
        )
        min_count = (await db.execute(select(func.count(MinisterialPosition.id)))).scalar()
        logger.info(f"  Cleared linked_entity_id from {min_count} ministers")

        await db.execute(
            update(CompanyDirector).values(linked_entity_id=None, entity_link_confidence=None)
        )
        dir_count = (await db.execute(select(func.count(CompanyDirector.id)))).scalar()
        logger.info(f"  Cleared linked_entity_id from {dir_count} directors")

        # Clear story_entity_links
        del_result = await db.execute(delete(StoryEntityLink))
        logger.info(f"  Deleted {del_result.rowcount} story-entity links")

        # Delete auto-created entities that have Devanagari in name_en
        # These were created by the buggy linker; they'll be recreated correctly
        result = await db.execute(
            select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PERSON)
        )
        entities = list(result.scalars().all())
        deleted = 0
        for ent in entities:
            if ent.name_en and _is_nepali(ent.name_en):
                await db.delete(ent)
                deleted += 1
        logger.info(f"  Deleted {deleted} auto-created entities with Devanagari name_en")

        # Clear enrichment fields on remaining entities so they get re-absorbed
        remaining = await db.execute(
            select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PERSON)
        )
        cleared = 0
        for ent in remaining.scalars().all():
            ent.biography = None
            ent.biography_source = None
            ent.education = None
            ent.education_institution = None
            ent.age = None
            ent.gender = None
            ent.current_position = None
            ent.position_history = None
            ent.total_mentions = 0
            cleared += 1
        logger.info(f"  Cleared enrichment fields on {cleared} remaining entities")

        await db.commit()
        logger.info("  Phase 0 reset complete")


async def phase_6b_fix_entity_names():
    """Fix entities where name_en still contains Devanagari after re-linking."""
    async with AsyncSessionLocal() as db:
        logger.info("=" * 60)
        logger.info("Phase 6b: Fixing entity names with Devanagari in name_en...")

        result = await db.execute(
            select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PERSON)
        )
        entities = list(result.scalars().all())
        fixed = 0
        aliases_merged = 0

        for ent in entities:
            # Fix name_en if it contains Devanagari
            if ent.name_en and _is_nepali(ent.name_en):
                # Find best linked candidate with name_en_roman
                cand_result = await db.execute(
                    select(Candidate)
                    .where(Candidate.linked_entity_id == ent.id)
                    .order_by(Candidate.entity_link_confidence.desc().nulls_last())
                    .limit(1)
                )
                best_cand = cand_result.scalar_one_or_none()
                if best_cand and best_cand.name_en_roman:
                    ent.name_en = best_cand.name_en_roman
                    fixed += 1

            # Merge candidate aliases into entity aliases
            cand_result = await db.execute(
                select(Candidate).where(Candidate.linked_entity_id == ent.id)
            )
            cands = cand_result.scalars().all()
            existing_aliases = set(ent.aliases or [])
            new_aliases = set()
            for cand in cands:
                if cand.aliases:
                    for alias in cand.aliases:
                        if alias and alias not in existing_aliases and alias != ent.name_en and alias != ent.name_ne:
                            new_aliases.add(alias)
                if cand.name_en_roman and cand.name_en_roman not in existing_aliases and cand.name_en_roman != ent.name_en:
                    new_aliases.add(cand.name_en_roman)

            if new_aliases:
                ent.aliases = list(existing_aliases | new_aliases)
                aliases_merged += 1

        await db.commit()
        logger.info(f"  Fixed {fixed} entity names, merged aliases for {aliases_merged} entities")


async def phase_1_to_6():
    """Run entity linking phases 1-6."""
    from app.services.entity_linker import EntityLinker

    async with AsyncSessionLocal() as db:
        linker = EntityLinker(db)

        # Phase 1-2: Link candidates (creates new entities for unlinked winners)
        logger.info("=" * 60)
        logger.info("Phase 1-2: Linking candidates to entities...")
        cand_stats = await linker.link_candidates_to_entities()
        logger.info(f"  Result: {cand_stats}")

        # Phase 3: Link MPs
        logger.info("=" * 60)
        logger.info("Phase 3: Linking MPs to entities...")
        mp_stats = await linker.link_mps_to_entities()
        logger.info(f"  Result: {mp_stats}")

        # Phase 4: Link ministers
        logger.info("=" * 60)
        logger.info("Phase 4: Linking ministers to entities...")
        minister_stats = await linker.link_ministers_to_entities()
        logger.info(f"  Result: {minister_stats}")

        # Phase 5: Link directors
        logger.info("=" * 60)
        logger.info("Phase 5: Linking directors to entities...")
        director_stats = await linker.link_directors_to_entities()
        logger.info(f"  Result: {director_stats}")

        # Phase 6: Absorb enrichments
        logger.info("=" * 60)
        logger.info("Phase 6: Absorbing enrichments into PoliticalEntity...")
        enrich_stats = await linker.absorb_enrichments()
        logger.info(f"  Result: {enrich_stats}")

        await db.commit()

        # Print summary
        entity_count_result = await db.execute(select(func.count(PoliticalEntity.id)))
        total_entities = entity_count_result.scalar()

        linked_cand_result = await db.execute(
            select(func.count(Candidate.id)).where(Candidate.linked_entity_id.isnot(None))
        )
        linked_candidates = linked_cand_result.scalar()

        linked_mp_result = await db.execute(
            select(func.count(MPPerformance.id)).where(MPPerformance.linked_entity_id.isnot(None))
        )
        linked_mps = linked_mp_result.scalar()

        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info(f"  Total PoliticalEntity records: {total_entities}")
        logger.info(f"  Linked candidates: {linked_candidates}")
        logger.info(f"  Linked MPs: {linked_mps}")


async def phase_7_backfill_story_links():
    """Backfill StoryEntityLinks for recent stories using NER."""
    from app.services.nlp.database_entity_extractor import (
        get_database_entity_extractor,
        initialize_entity_extractor,
    )

    async with AsyncSessionLocal() as db:
        logger.info("=" * 60)
        logger.info("Phase 7: Backfilling StoryEntityLinks (last 7 days)...")

        # Initialize entity extractor
        extractor = get_database_entity_extractor()
        if not extractor.is_initialized:
            await initialize_entity_extractor(db)
        logger.info(f"  Entity extractor: {extractor.pattern_count} patterns loaded")

        # Find stories without entity links from last 7 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        result = await db.execute(
            select(Story)
            .outerjoin(StoryEntityLink, StoryEntityLink.story_id == Story.id)
            .where(Story.created_at >= cutoff)
            .where(StoryEntityLink.id.is_(None))
            .where(Story.nepal_relevance != "international")
            .limit(2000)
        )
        stories = list(result.scalars().all())
        logger.info(f"  Found {len(stories)} stories without entity links")

        # Build canonical_id → entity UUID mapping
        entity_result = await db.execute(select(PoliticalEntity))
        entity_map = {}
        for entity in entity_result.scalars().all():
            entity_map[entity.canonical_id] = entity.id

        linked_count = 0
        link_count = 0

        for story in stories:
            text = f"{story.title} {story.summary or ''}"
            entities = await extractor.extract(text, min_confidence=0.6, session=db)

            story_linked = False
            for entity in entities:
                entity_uuid = entity_map.get(entity.canonical_id)
                if not entity_uuid:
                    continue

                # Check if link already exists
                existing = await db.execute(
                    select(StoryEntityLink.id).where(
                        StoryEntityLink.story_id == story.id,
                        StoryEntityLink.entity_id == entity_uuid,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                # Determine if title mention
                is_title = entity.text.lower() in story.title.lower() if story.title else False

                link = StoryEntityLink(
                    story_id=story.id,
                    entity_id=entity_uuid,
                    is_title_mention=is_title,
                    confidence=entity.confidence,
                )
                db.add(link)
                link_count += 1
                story_linked = True

            if story_linked:
                linked_count += 1

            # Batch commit every 100 linked stories
            if story_linked and linked_count > 0 and linked_count % 100 == 0:
                await db.commit()
                logger.info(f"  Progress: {linked_count} stories processed, {link_count} links created")

        await db.commit()
        logger.info(f"  Done: {linked_count} stories linked, {link_count} total links created")

    # Recount mentions
    async with AsyncSessionLocal() as db:
        logger.info("  Recounting entity mentions...")

        # Update total_mentions from StoryEntityLink count
        entities = await db.execute(select(PoliticalEntity))
        for entity in entities.scalars().all():
            count_result = await db.execute(
                select(func.count(StoryEntityLink.id))
                .where(StoryEntityLink.entity_id == entity.id)
            )
            total = count_result.scalar() or 0
            entity.total_mentions = total

        await db.commit()
        logger.info("  Mention counts updated")


async def main():
    logger.info("Starting entity linking backfill (with reset)...")
    logger.info("=" * 60)

    await phase_0_reset()
    await phase_1_to_6()
    await phase_6b_fix_entity_names()
    await phase_7_backfill_story_links()

    logger.info("=" * 60)
    logger.info("Entity linking backfill complete!")


if __name__ == "__main__":
    asyncio.run(main())
