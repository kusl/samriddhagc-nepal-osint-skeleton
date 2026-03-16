#!/usr/bin/env python3
"""Normalize party names + update entity.party from latest election data.

1. Normalize party name strings across all PoliticalEntity records.
2. For entities that ran in elections, update party to their LATEST candidacy.
3. Fix known cases (Balen Shah → RSP, etc.).
4. Deduplicate PARTY_AFFILIATION relationships after normalization.

Usage:
    cd backend-v5
    venv/bin/python3 scripts/enrich_party_data.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func, delete
from app.core.database import AsyncSessionLocal
from app.models.political_entity import PoliticalEntity, EntityType
from app.models.entity_relationship import EntityRelationship, RelationshipType
from app.models.election import Election, Candidate

# Same normalization map used by the graph service
_PARTY_CANONICAL: dict[str, str] = {
    "cpn-uml": "CPN-UML",
    "cpn (uml)": "CPN-UML",
    "cpn(uml)": "CPN-UML",
    "communist party of nepal (unified marxist-leninist)": "CPN-UML",
    "communist party of nepal uml": "CPN-UML",
    "nepali congress": "Nepali Congress",
    "nc": "Nepali Congress",
    "cpn maoist centre": "CPN Maoist Centre",
    "cpn-maoist centre": "CPN Maoist Centre",
    "cpn (maoist centre)": "CPN Maoist Centre",
    "cpn-mc": "CPN Maoist Centre",
    "cpn (maoist center)": "CPN Maoist Centre",
    "maoist centre": "CPN Maoist Centre",
    "rastriya swatantra party": "Rastriya Swatantra Party",
    "rsp": "Rastriya Swatantra Party",
    "janata samajbadi party": "Janata Samajbadi Party",
    "janata samajwadi party": "Janata Samajbadi Party",
    "jsp": "Janata Samajbadi Party",
    "cpn (unified socialist)": "CPN (Unified Socialist)",
    "cpn-unified socialist": "CPN (Unified Socialist)",
    "cpn unified socialist": "CPN (Unified Socialist)",
    "independent": "Independent",
    "rpp": "RPP",
    "rpp nepal": "RPP Nepal",
    "loktantrik samajbadi party": "Loktantrik Samajbadi Party",
    "nagarik unmukti party": "Nagarik Unmukti Party",
    "janamat party": "Janamat Party",
    "nepali communist party": "Nepali Communist Party",
    "nepal workers peasants party": "Nepal Workers Peasants Party",
}


def normalize(name: str | None) -> str:
    if not name:
        return ""
    stripped = name.strip()
    return _PARTY_CANONICAL.get(stripped.lower(), stripped)


async def step1_normalize_party_strings(db) -> int:
    """Normalize party name strings on all entities."""
    print("\n[1/4] Normalizing party strings on PoliticalEntity records...")
    result = await db.execute(
        select(PoliticalEntity).where(PoliticalEntity.party.isnot(None))
    )
    entities = result.scalars().all()
    changed = 0
    for ent in entities:
        canon = normalize(ent.party)
        if canon and canon != ent.party:
            print(f"  {ent.name_en:35} \"{ent.party}\" → \"{canon}\"")
            ent.party = canon
            changed += 1
    await db.flush()
    print(f"  Normalized {changed} entity party strings")
    return changed


async def step2_update_from_elections(db) -> int:
    """Update entity.party from their latest election candidacy."""
    print("\n[2/4] Updating entity.party from latest election data...")

    # Get all elections ordered by year
    elections = (await db.execute(
        select(Election).order_by(Election.year_bs.desc())
    )).scalars().all()

    if not elections:
        print("  No elections in DB")
        return 0

    # Get all person entities
    entities = (await db.execute(
        select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PERSON)
    )).scalars().all()

    # Build name lookup: lowercase name/alias → entity
    entity_by_name: dict[str, PoliticalEntity] = {}
    for ent in entities:
        if ent.name_en:
            entity_by_name[ent.name_en.lower()] = ent
        if ent.aliases:
            for alias in ent.aliases:
                if isinstance(alias, str) and len(alias) > 2:
                    entity_by_name[alias.lower()] = ent

    # For each election (newest first), find matching candidates
    # and update entity.party if different
    updated = 0
    already_updated: set[str] = set()  # entity canonical_ids we've already updated

    for election in elections:
        candidates = (await db.execute(
            select(Candidate).where(
                Candidate.election_id == election.id,
                Candidate.is_winner == True,  # noqa: E712
            )
        )).scalars().all()

        for cand in candidates:
            # Try to match candidate to entity
            cand_name = (cand.name_en_roman or cand.name_en or "").strip().lower()
            ent = entity_by_name.get(cand_name)

            # Also try aliases
            if not ent and cand.aliases:
                for alias in (cand.aliases if isinstance(cand.aliases, list) else []):
                    if isinstance(alias, str):
                        ent = entity_by_name.get(alias.lower())
                        if ent:
                            break

            if not ent or ent.canonical_id in already_updated:
                continue

            cand_party = normalize(cand.party)
            current_party = normalize(ent.party)

            if cand_party and cand_party != current_party:
                print(f"  {ent.name_en:35} \"{ent.party}\" → \"{cand_party}\" (from {election.year_bs} election)")
                ent.party = cand_party
                updated += 1

            already_updated.add(ent.canonical_id)

    await db.flush()
    print(f"  Updated {updated} entities from election data")
    return updated


async def step3_fix_known_cases(db) -> int:
    """Fix known party assignments that aren't covered by election data."""
    print("\n[3/4] Fixing known cases...")

    fixes = [
        # Balen Shah is now RSP (elected from Jhapa-5 in 2082 as RSP)
        ("balen", "Rastriya Swatantra Party", "Running from RSP in 2082 Jhapa-5"),
    ]

    fixed = 0
    for canonical_id, new_party, reason in fixes:
        result = await db.execute(
            select(PoliticalEntity).where(PoliticalEntity.canonical_id == canonical_id)
        )
        ent = result.scalar_one_or_none()
        if ent and normalize(ent.party) != normalize(new_party):
            print(f"  {ent.name_en:35} \"{ent.party}\" → \"{new_party}\" ({reason})")
            ent.party = new_party
            fixed += 1
        elif ent:
            print(f"  {ent.name_en:35} already \"{ent.party}\" [skip]")

    await db.flush()
    print(f"  Fixed {fixed} known cases")
    return fixed


async def step4_dedup_party_affiliations(db) -> int:
    """Remove duplicate PARTY_AFFILIATION relationships after normalization."""
    print("\n[4/4] Deduplicating PARTY_AFFILIATION relationships...")

    result = await db.execute(
        select(EntityRelationship).where(
            EntityRelationship.relationship_type == RelationshipType.PARTY_AFFILIATION
        )
    )
    rels = result.scalars().all()

    # Group by (source, target) to find duplicates
    seen: dict[tuple, EntityRelationship] = {}
    to_delete = []
    for rel in rels:
        key = (str(rel.source_entity_id), str(rel.target_entity_id))
        if key in seen:
            to_delete.append(rel.id)
        else:
            seen[key] = rel

    if to_delete:
        for rel_id in to_delete:
            await db.execute(
                delete(EntityRelationship).where(EntityRelationship.id == rel_id)
            )
        print(f"  Removed {len(to_delete)} duplicate PARTY_AFFILIATION relationships")
    else:
        print("  No duplicates found")

    await db.flush()
    return len(to_delete)


async def enrich():
    print("=" * 70)
    print("Enriching Party Data")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        n1 = await step1_normalize_party_strings(db)
        n2 = await step2_update_from_elections(db)
        n3 = await step3_fix_known_cases(db)
        n4 = await step4_dedup_party_affiliations(db)
        await db.commit()

    print("\n" + "=" * 70)
    print(f"Party enrichment complete: {n1} normalized, {n2} updated, {n3} fixed, {n4} deduped")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(enrich())
