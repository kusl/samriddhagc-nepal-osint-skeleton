#!/usr/bin/env python3
"""Build entity relationships from co-mentions, party affiliations, and ministerial links.

1. Co-mention discovery from story_entity_links
2. PARTY_AFFILIATION relationships between entities and their party entities
3. Links entities to ministerial positions by name match
4. Cabinet-colleague relationships for current ministers

Usage:
    cd backend-v5
    venv/bin/python3 scripts/seed_relationships.py
"""
import asyncio
import sys
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models.political_entity import PoliticalEntity, EntityType
from app.models.entity_relationship import EntityRelationship, RelationshipType
from app.models.story_entity_link import StoryEntityLink
from app.models.ministerial_position import MinisterialPosition


async def build_co_mention_relationships(db) -> int:
    """Discover co-mention relationships from story_entity_links."""
    print("\n[1/4] Building co-mention relationships...")

    # Get all story-entity links
    result = await db.execute(
        select(StoryEntityLink.story_id, StoryEntityLink.entity_id)
    )
    links = result.all()

    if not links:
        print("  No story_entity_links found")
        return 0

    # Build story -> entities mapping
    story_entities: dict[str, set[str]] = defaultdict(set)
    for row in links:
        story_entities[str(row.story_id)].add(str(row.entity_id))

    print(f"  Found {len(links)} links across {len(story_entities)} stories")

    # Count co-mentions
    co_mentions: dict[tuple[str, str], int] = defaultdict(int)
    for story_id, entity_set in story_entities.items():
        ent_list = sorted(entity_set)
        for i in range(len(ent_list)):
            for j in range(i + 1, len(ent_list)):
                co_mentions[(ent_list[i], ent_list[j])] += 1

    # Filter: require at least 2 co-mentions
    significant = {pair: count for pair, count in co_mentions.items() if count >= 2}
    print(f"  Found {len(significant)} significant co-mention pairs (>= 2)")

    created = 0
    for (e1, e2), count in significant.items():
        from uuid import UUID
        src_id = UUID(e1)
        tgt_id = UUID(e2)

        # Check if relationship exists
        existing = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id == src_id,
                EntityRelationship.target_entity_id == tgt_id,
                EntityRelationship.relationship_type == RelationshipType.CO_MENTION,
            ).limit(1)
        )
        existing_rel = existing.scalar_one_or_none()
        if existing_rel:
            existing_rel.co_mention_count = count
            existing_rel.strength_score = min(1.0, count / 20.0)
            continue

        strength = min(1.0, count / 20.0)
        rel = EntityRelationship(
            source_entity_id=src_id,
            target_entity_id=tgt_id,
            relationship_type=RelationshipType.CO_MENTION,
            co_mention_count=count,
            strength_score=strength,
            confidence=0.8,
            notes=f"Auto-discovered from {count} story co-mentions",
            is_verified=False,
        )
        db.add(rel)
        created += 1

    await db.flush()
    print(f"  Created {created} co-mention relationships")
    return created


async def build_party_relationships(db) -> int:
    """Create PARTY_AFFILIATION relationships between person entities and party entities."""
    print("\n[2/4] Building party affiliation relationships...")

    # Get all party entities
    party_result = await db.execute(
        select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PARTY)
    )
    party_entities = {pe.name_en: pe for pe in party_result.scalars().all()}
    print(f"  Found {len(party_entities)} party entities")

    # Get all person entities with party field
    person_result = await db.execute(
        select(PoliticalEntity).where(
            PoliticalEntity.entity_type == EntityType.PERSON,
            PoliticalEntity.party.isnot(None),
        )
    )
    persons = person_result.scalars().all()

    created = 0
    for person in persons:
        # Try to find matching party entity
        party_entity = party_entities.get(person.party)
        if not party_entity:
            # Try partial match
            for pname, pentity in party_entities.items():
                if person.party and (
                    person.party.lower() in pname.lower()
                    or pname.lower() in person.party.lower()
                ):
                    party_entity = pentity
                    break

        if not party_entity:
            continue

        # Check if relationship exists
        existing = await db.execute(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id == person.id,
                EntityRelationship.target_entity_id == party_entity.id,
                EntityRelationship.relationship_type == RelationshipType.PARTY_AFFILIATION,
            )
        )
        if existing.scalar_one_or_none():
            continue

        rel = EntityRelationship(
            source_entity_id=person.id,
            target_entity_id=party_entity.id,
            relationship_type=RelationshipType.PARTY_AFFILIATION,
            strength_score=1.0,
            confidence=1.0,
            notes=f"{person.name_en} is member of {party_entity.name_en}",
            is_verified=True,
            verified_by="seed_relationships",
        )
        db.add(rel)
        created += 1

    await db.flush()
    print(f"  Created {created} party affiliation relationships")
    return created


async def link_entities_to_ministerial(db) -> int:
    """Link PoliticalEntity records to MinisterialPosition records by name match."""
    print("\n[3/4] Linking entities to ministerial positions...")

    # Get all entities (person type)
    result = await db.execute(
        select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PERSON)
    )
    entities = result.scalars().all()
    entity_name_map = {}
    for e in entities:
        entity_name_map[e.name_en.lower()] = e
        if e.aliases:
            for alias in e.aliases:
                if isinstance(alias, str):
                    entity_name_map[alias.lower()] = e

    # Get ministerial positions without linked entities
    min_result = await db.execute(
        select(MinisterialPosition)
    )
    positions = min_result.scalars().all()

    linked = 0
    for pos in positions:
        if not pos.person_name_en:
            continue

        matched = entity_name_map.get(pos.person_name_en.lower())
        if not matched and pos.person_name_ne:
            matched = entity_name_map.get(pos.person_name_ne.lower()) if pos.person_name_ne else None

        if matched:
            # We don't modify the ministerial position FK here since it
            # requires a candidate link, but this confirms the mapping exists
            linked += 1

    print(f"  Found {linked} entity-ministerial name matches out of {len(positions)} positions")
    return linked


async def build_cabinet_colleague_relationships(db) -> int:
    """Create relationships between current cabinet ministers."""
    print("\n[4/4] Building cabinet-colleague relationships...")

    # Get current ministers
    result = await db.execute(
        select(MinisterialPosition).where(MinisterialPosition.is_current == True)  # noqa: E712
    )
    current_positions = result.scalars().all()

    if len(current_positions) < 2:
        print(f"  Only {len(current_positions)} current positions, skipping")
        return 0

    # Map to entity IDs
    entities = []
    for pos in current_positions:
        ent_result = await db.execute(
            select(PoliticalEntity).where(
                func.lower(PoliticalEntity.name_en) == pos.person_name_en.lower()
            )
        )
        entity = ent_result.scalar_one_or_none()
        if entity:
            entities.append(entity)

    print(f"  Found {len(entities)} current ministers with entity records")

    created = 0
    for i in range(len(entities)):
        for j in range(i + 1, len(entities)):
            # Check if POLITICAL_ALLY relationship exists
            existing = await db.execute(
                select(EntityRelationship).where(
                    EntityRelationship.source_entity_id == entities[i].id,
                    EntityRelationship.target_entity_id == entities[j].id,
                    EntityRelationship.relationship_type == RelationshipType.POLITICAL_ALLY,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # Also check reverse direction
            existing_rev = await db.execute(
                select(EntityRelationship).where(
                    EntityRelationship.source_entity_id == entities[j].id,
                    EntityRelationship.target_entity_id == entities[i].id,
                    EntityRelationship.relationship_type == RelationshipType.POLITICAL_ALLY,
                )
            )
            if existing_rev.scalar_one_or_none():
                continue

            rel = EntityRelationship(
                source_entity_id=entities[i].id,
                target_entity_id=entities[j].id,
                relationship_type=RelationshipType.POLITICAL_ALLY,
                strength_score=0.7,
                confidence=1.0,
                notes="Cabinet colleagues in current government",
                is_verified=True,
                verified_by="seed_relationships",
            )
            db.add(rel)
            created += 1

    await db.flush()
    print(f"  Created {created} cabinet-colleague relationships")
    return created


async def seed_relationships():
    """Main entry point."""
    print("=" * 70)
    print("Building Entity Relationships")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        co_mention_count = await build_co_mention_relationships(db)
        party_count = await build_party_relationships(db)
        ministerial_count = await link_entities_to_ministerial(db)
        colleague_count = await build_cabinet_colleague_relationships(db)

        await db.commit()

    print("\n" + "=" * 70)
    print("Relationship building complete!")
    print(f"  Co-mention:    {co_mention_count}")
    print(f"  Party:         {party_count}")
    print(f"  Ministerial:   {ministerial_count} (name matches)")
    print(f"  Colleagues:    {colleague_count}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_relationships())
