"""Query Balen Shah's entity relationships from the Nepal OSINT v5 database."""
import sys
import asyncio

# Ensure project root is on path
sys.path.insert(0, "/Users/samriddhagc/Desktop/Projects/nepal_osint_v5/backend-v5")

from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.political_entity import PoliticalEntity
from app.models.entity_relationship import EntityRelationship
from app.models.story_entity_link import StoryEntityLink
from app.models.election import Candidate
from app.models.parliament import MPPerformance
from app.models.ministerial_position import MinisterialPosition
from app.models.company import CompanyDirector


async def main():
    async with AsyncSessionLocal() as session:
        # ── 1. Find Balen's PoliticalEntity ──────────────────────────
        result = await session.execute(
            select(PoliticalEntity).where(PoliticalEntity.canonical_id == "balen")
        )
        balen = result.scalar_one_or_none()

        if not balen:
            print("ERROR: No PoliticalEntity found with canonical_id='balen'")
            return

        print("=" * 80)
        print("BALEN SHAH - PoliticalEntity")
        print("=" * 80)
        print(f"  id:              {balen.id}")
        print(f"  canonical_id:    {balen.canonical_id}")
        print(f"  name_en:         {balen.name_en}")
        print(f"  name_ne:         {balen.name_ne}")
        print(f"  entity_type:     {balen.entity_type}")
        print(f"  party:           {balen.party}")
        print(f"  role:            {balen.role}")
        print(f"  aliases:         {balen.aliases}")
        print(f"  former_parties:  {balen.former_parties}")
        bio_snippet = (balen.biography[:200] + "...") if balen.biography and len(balen.biography) > 200 else balen.biography
        print(f"  biography:       {bio_snippet}")
        print(f"  extra_data:      {balen.extra_data}")
        print(f"  total_mentions:  {balen.total_mentions}")
        print(f"  mentions_24h:    {balen.mentions_24h}")
        print(f"  mentions_7d:     {balen.mentions_7d}")
        print(f"  trend:           {balen.trend}")
        print(f"  is_active:       {balen.is_active}")
        print(f"  last_mentioned:  {balen.last_mentioned_at}")
        print(f"  created_at:      {balen.created_at}")

        balen_id = balen.id

        # ── 2. Entity Relationships ──────────────────────────────────
        print("\n" + "=" * 80)
        print("ENTITY RELATIONSHIPS (where Balen is source or target)")
        print("=" * 80)

        rels_result = await session.execute(
            select(EntityRelationship).where(
                or_(
                    EntityRelationship.source_entity_id == balen_id,
                    EntityRelationship.target_entity_id == balen_id,
                )
            )
        )
        relationships = rels_result.scalars().all()

        if not relationships:
            print("  (none found)")
        else:
            print(f"  Total relationships: {len(relationships)}\n")

            # Collect the other entity IDs so we can fetch their names in one query
            other_ids = set()
            for rel in relationships:
                other_id = rel.target_entity_id if rel.source_entity_id == balen_id else rel.source_entity_id
                other_ids.add(other_id)

            # Batch-fetch other entities
            if other_ids:
                others_result = await session.execute(
                    select(PoliticalEntity).where(PoliticalEntity.id.in_(other_ids))
                )
                others_map = {e.id: e for e in others_result.scalars().all()}
            else:
                others_map = {}

            for i, rel in enumerate(relationships, 1):
                is_source = rel.source_entity_id == balen_id
                other_id = rel.target_entity_id if is_source else rel.source_entity_id
                other = others_map.get(other_id)
                direction = "-->" if is_source else "<--"

                print(f"  [{i}] Balen {direction} {other.name_en if other else '???'} (canonical_id: {other.canonical_id if other else '???'})")
                print(f"      relationship_type: {rel.relationship_type.value}")
                print(f"      strength_score:    {rel.strength_score}")
                print(f"      co_mention_count:  {rel.co_mention_count}")
                print(f"      confidence:        {rel.confidence}")
                print(f"      notes:             {rel.notes}")
                print(f"      is_verified:       {rel.is_verified}")
                print(f"      first_co_mention:  {rel.first_co_mention_at}")
                print(f"      last_co_mention:   {rel.last_co_mention_at}")
                print()

        # ── 3. Linked Candidates ─────────────────────────────────────
        print("=" * 80)
        print("LINKED CANDIDATES (via linked_entity_id)")
        print("=" * 80)

        cands_result = await session.execute(
            select(Candidate).where(Candidate.linked_entity_id == balen_id)
        )
        candidates = cands_result.scalars().all()

        if not candidates:
            print("  (none found)")
        else:
            for c in candidates:
                print(f"  - {c.name_en} ({c.name_ne})")
                print(f"    party: {c.party}, votes: {c.votes}, vote_pct: {c.vote_pct}%, rank: {c.rank}, winner: {c.is_winner}")
                print(f"    constituency_id: {c.constituency_id}, election_id: {c.election_id}")
                print(f"    entity_link_confidence: {c.entity_link_confidence}")
                print()

        # ── 4. Linked MPPerformance ──────────────────────────────────
        print("=" * 80)
        print("LINKED MP PERFORMANCE (via linked_entity_id)")
        print("=" * 80)

        mp_result = await session.execute(
            select(MPPerformance).where(MPPerformance.linked_entity_id == balen_id)
        )
        mp_records = mp_result.scalars().all()

        if not mp_records:
            print("  (none found)")
        else:
            for mp in mp_records:
                print(f"  - {mp.name_en} ({mp.name_ne})")
                print(f"    party: {mp.party}, constituency: {mp.constituency}")
                print(f"    chamber: {mp.chamber}, term: {mp.term}")
                print(f"    performance_score: {mp.performance_score}, tier: {mp.performance_tier}")
                print(f"    bills_introduced: {mp.bills_introduced}, questions_asked: {mp.questions_asked}")
                print(f"    attendance: {mp.session_attendance_pct}%")
                print()

        # ── 5. Linked MinisterialPositions ───────────────────────────
        print("=" * 80)
        print("LINKED MINISTERIAL POSITIONS (via linked_entity_id)")
        print("=" * 80)

        min_result = await session.execute(
            select(MinisterialPosition).where(MinisterialPosition.linked_entity_id == balen_id)
        )
        positions = min_result.scalars().all()

        if not positions:
            print("  (none found)")
        else:
            for p in positions:
                print(f"  - {p.person_name_en} ({p.person_name_ne})")
                print(f"    position_type: {p.position_type}, ministry: {p.ministry}")
                print(f"    start: {p.start_date}, end: {p.end_date}, current: {p.is_current}")
                print(f"    government: {p.government_name}, PM: {p.prime_minister}")
                print()

        # ── 6. Linked CompanyDirectors ───────────────────────────────
        print("=" * 80)
        print("LINKED COMPANY DIRECTORS (via linked_entity_id)")
        print("=" * 80)

        dir_result = await session.execute(
            select(CompanyDirector).where(CompanyDirector.linked_entity_id == balen_id)
        )
        directors = dir_result.scalars().all()

        if not directors:
            print("  (none found)")
        else:
            for d in directors:
                print(f"  - {d.name_en} ({d.name_np})")
                print(f"    role: {d.role}, company_name_hint: {d.company_name_hint}")
                print(f"    source: {d.source}, confidence: {d.confidence}")
                print(f"    pan: {d.pan}, citizenship_no: {d.citizenship_no}")
                print()

        # ── 7. StoryEntityLink count ─────────────────────────────────
        print("=" * 80)
        print("STORY ENTITY LINKS")
        print("=" * 80)

        count_result = await session.execute(
            select(func.count(StoryEntityLink.id)).where(
                StoryEntityLink.entity_id == balen_id
            )
        )
        link_count = count_result.scalar()
        print(f"  Total StoryEntityLink rows for Balen: {link_count}")

        print("\n" + "=" * 80)
        print("DONE")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
