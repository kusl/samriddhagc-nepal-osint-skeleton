#!/usr/bin/env python3
"""Load election data (2079 + 2082) from frontend JSON into DB.

Replaces existing election data for these years with fresh data including
full candidate profiles (biography, aliases, photo_url, education, etc.).
Also creates PoliticalEntity records for notable winning candidates.

Usage:
    cd backend-v5
    venv/bin/python3 scripts/load_elections.py
"""
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, delete
from app.core.database import AsyncSessionLocal
from app.models.election import (
    Election, Constituency, Candidate,
    ElectionType, ElectionStatus, ConstituencyStatus,
)
from app.models.political_entity import PoliticalEntity, EntityType, EntityTrend

JSON_DATA_DIR = Path(__file__).parent.parent.parent / "frontend" / "public" / "data"

BS_TO_AD = {2079: 2022, 2082: 2025}
YEARS_TO_LOAD = [2079, 2082]


async def load_election_year(db, year_bs: int) -> dict:
    """Load a single election year. Returns stats dict."""
    json_file = JSON_DATA_DIR / f"election-results-{year_bs}.json"
    if not json_file.exists():
        print(f"  [ERROR] JSON file not found: {json_file}")
        return {"error": True}

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    print(f"\n  Loading {year_bs} BS ({BS_TO_AD.get(year_bs, '?')} AD) - {len(results)} constituencies")

    # Delete existing election data for this year (cascade deletes constituencies & candidates)
    existing = await db.execute(select(Election).where(Election.year_bs == year_bs))
    old_election = existing.scalar_one_or_none()
    if old_election:
        await db.delete(old_election)
        await db.flush()
        print(f"  Cleared existing {year_bs} data")

    # Compute national stats
    declared_count = sum(1 for r in results if r.get("status") == "declared")
    total_votes = sum(r.get("total_votes", 0) or 0 for r in results)

    if declared_count == len(results):
        status = ElectionStatus.COMPLETED.value
    elif declared_count > 0:
        status = ElectionStatus.ONGOING.value
    else:
        status = ElectionStatus.UPCOMING.value

    # Create Election
    election = Election(
        id=uuid4(),
        year_bs=year_bs,
        year_ad=BS_TO_AD.get(year_bs, year_bs - 57),
        election_type=ElectionType.PARLIAMENTARY.value,
        status=status,
        total_constituencies=data.get("total_constituencies", len(results)),
        total_votes_cast=total_votes if total_votes > 0 else None,
    )
    db.add(election)
    await db.flush()

    constituency_count = 0
    candidate_count = 0
    notable_winners = []

    for result_data in results:
        status_str = result_data.get("status", "pending")
        const_status = {
            "declared": ConstituencyStatus.DECLARED.value,
            "counting": ConstituencyStatus.COUNTING.value,
        }.get(status_str, ConstituencyStatus.PENDING.value)

        constituency = Constituency(
            id=uuid4(),
            election_id=election.id,
            constituency_code=result_data["constituency_id"],
            name_en=result_data["name_en"],
            name_ne=result_data.get("name_ne"),
            district=result_data["district"],
            province=result_data["province"],
            province_id=result_data["province_id"],
            status=const_status,
            total_votes_cast=result_data.get("total_votes"),
            turnout_pct=result_data.get("turnout_pct"),
            winner_party=result_data.get("winner_party"),
            winner_votes=result_data.get("winner_votes"),
        )
        db.add(constituency)
        await db.flush()
        constituency_count += 1

        winner_id = None
        candidates_data = result_data.get("candidates", [])

        for i, cand_data in enumerate(candidates_data):
            candidate = Candidate(
                id=uuid4(),
                election_id=election.id,
                constituency_id=constituency.id,
                external_id=cand_data["id"],
                name_en=cand_data["name_en"],
                name_ne=cand_data.get("name_ne"),
                party=cand_data["party"],
                party_ne=cand_data.get("party_ne"),
                votes=cand_data.get("votes", 0),
                vote_pct=cand_data.get("vote_pct", 0.0),
                rank=i + 1,
                is_winner=cand_data.get("is_winner", False),
                photo_url=cand_data.get("photo_url"),
                age=cand_data.get("age"),
                gender=cand_data.get("gender"),
                education=cand_data.get("education"),
                education_institution=cand_data.get("education_institution"),
                name_en_roman=cand_data.get("name_en_roman"),
                aliases=cand_data.get("aliases"),
                biography=cand_data.get("biography"),
                biography_source=cand_data.get("biography_source"),
                is_notable=cand_data.get("is_notable", False),
                previous_positions=cand_data.get("previous_positions"),
            )
            db.add(candidate)
            candidate_count += 1

            if cand_data.get("is_winner"):
                winner_id = candidate.id
                if cand_data.get("is_notable"):
                    notable_winners.append({
                        "name_en": cand_data.get("name_en_roman") or cand_data["name_en"],
                        "name_ne": cand_data.get("name_ne"),
                        "party": cand_data["party"],
                        "constituency": result_data["constituency_id"],
                        "aliases": cand_data.get("aliases"),
                    })

        await db.flush()

        # Set winner reference and margin
        if winner_id:
            constituency.winner_candidate_id = winner_id
            if len(candidates_data) >= 2:
                sorted_cands = sorted(candidates_data, key=lambda x: x.get("votes", 0), reverse=True)
                v1 = sorted_cands[0].get("votes", 0)
                v2 = sorted_cands[1].get("votes", 0)
                if v1 and v2:
                    constituency.winner_margin = v1 - v2

    await db.flush()
    print(f"  Imported {constituency_count} constituencies, {candidate_count} candidates")
    return {
        "constituencies": constituency_count,
        "candidates": candidate_count,
        "notable_winners": notable_winners,
    }


async def create_entities_for_winners(db, all_notable_winners: list) -> int:
    """Create PoliticalEntity records for notable winning candidates."""
    created = 0
    for winner in all_notable_winners:
        name = winner["name_en"]
        # Generate a canonical_id from name
        canonical = name.lower().replace(" ", "_").replace(".", "")
        # Truncate to 50 chars
        canonical = canonical[:50]

        # Check if entity already exists
        existing = await db.execute(
            select(PoliticalEntity).where(
                PoliticalEntity.canonical_id == canonical
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Also check by name match
        existing_name = await db.execute(
            select(PoliticalEntity).where(
                PoliticalEntity.name_en == name
            )
        )
        if existing_name.scalar_one_or_none():
            continue

        entity = PoliticalEntity(
            canonical_id=canonical,
            name_en=name,
            name_ne=winner.get("name_ne"),
            entity_type=EntityType.PERSON,
            party=winner["party"],
            role=f"Elected MP ({winner['constituency']})",
            aliases=winner.get("aliases"),
            description=f"Winning candidate from {winner['constituency']}.",
            trend=EntityTrend.STABLE,
            is_active=True,
        )
        db.add(entity)
        created += 1

    await db.flush()
    return created


async def load_elections():
    """Main entry point."""
    print("=" * 70)
    print("Loading Election Data (2079, 2082)")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        all_notable_winners = []

        for year_bs in YEARS_TO_LOAD:
            stats = await load_election_year(db, year_bs)
            if "error" not in stats:
                all_notable_winners.extend(stats.get("notable_winners", []))

        # Create entities for notable winners
        print(f"\n  Found {len(all_notable_winners)} notable winning candidates")
        entities_created = await create_entities_for_winners(db, all_notable_winners)
        print(f"  Created {entities_created} new PoliticalEntity records")

        await db.commit()

    print("\n" + "=" * 70)
    print("Election loading complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(load_elections())
