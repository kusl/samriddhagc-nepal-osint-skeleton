#!/usr/bin/env python3
"""Load party switch data from JSON files into entity relationships.

Reads two JSON data files:
- party-switches-2082-vs-2079.json (30 records with Nepali names)
- party-changes-2079-2082.json (33 records with candidate IDs)

For each switch, finds the matching PoliticalEntity, updates the entity's
current party to the 2082 party, and creates PARTY_AFFILIATION relationships
to the new party entity.  Switch metadata (fromParty, toParty, votes, etc.)
is stored in the relationship's notes field for the graph service's
FORMER_PARTY_MEMBER edge builder to use.

Usage:
    cd backend-v5
    venv/bin/python3 scripts/load_party_switches.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.political_entity import PoliticalEntity, EntityType
from app.models.entity_relationship import EntityRelationship, RelationshipType

# Same normalization map from the graph service / enrich_party_data.py
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


async def load_switches():
    print("=" * 70)
    print("Loading Party Switch Data")
    print("=" * 70)

    repo_root = Path(__file__).resolve().parents[2]

    # Load both JSON files
    file1 = repo_root / "frontend" / "public" / "data" / "party-switches-2082-vs-2079.json"
    file2 = repo_root / "frontend" / "public" / "data" / "party-changes-2079-2082.json"

    switches: list[dict] = []
    if file1.exists():
        data1 = json.loads(file1.read_text(encoding="utf-8"))
        for rec in data1:
            switches.append({
                "name_ne": rec.get("name", ""),
                "from_party": normalize(rec.get("fromParty", "")),
                "to_party": normalize(rec.get("toParty", rec.get("toCode", ""))),
                "constituency": rec.get("constituency", ""),
                "district": rec.get("district", ""),
                "votes_2079": rec.get("votes2079"),
                "was_winner": rec.get("wasWinner", False),
                "verification": rec.get("verification", ""),
                "period": "2079-2082",
                "source": "party-switches-2082-vs-2079.json",
            })
        print(f"  Loaded {len(data1)} records from {file1.name}")
    else:
        print(f"  WARNING: {file1} not found")

    if file2.exists():
        data2 = json.loads(file2.read_text(encoding="utf-8"))
        for rec in data2:
            switches.append({
                "name_ne": rec.get("name", ""),
                "candidate_id": rec.get("candidate_id", ""),
                "from_party": normalize(rec.get("from_party", "")),
                "to_party": normalize(rec.get("to_party", "")),
                "district": rec.get("district", ""),
                "votes_2079": rec.get("votes_2079"),
                "was_winner": rec.get("was_elected_2079", False),
                "period": "2079-2082",
                "source": "party-changes-2079-2082.json",
            })
        print(f"  Loaded {len(data2)} records from {file2.name}")
    else:
        print(f"  WARNING: {file2} not found")

    # Load 2074-2079 party changes
    file3 = repo_root / "frontend" / "public" / "data" / "party-changes-2074-2079.json"
    if file3.exists():
        data3 = json.loads(file3.read_text(encoding="utf-8"))
        for rec in data3:
            switches.append({
                "name_ne": rec.get("name", ""),
                "candidate_id": rec.get("candidate_id", ""),
                "from_party": normalize(rec.get("from_party", "")),
                "to_party": normalize(rec.get("to_party", "")),
                "district": rec.get("district", ""),
                "votes_2079": rec.get("votes_2079"),
                "was_winner": rec.get("was_elected_2079", False),
                "period": "2074-2079",
                "source": "party-changes-2074-2079.json",
            })
        print(f"  Loaded {len(data3)} records from {file3.name}")
    else:
        print(f"  WARNING: {file3} not found")

    if not switches:
        print("  No switch data to process")
        return

    print(f"\n  Total switch records: {len(switches)}")

    async with AsyncSessionLocal() as db:
        # Load all person entities
        result = await db.execute(
            select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PERSON)
        )
        entities = result.scalars().all()

        # Build lookup maps: Nepali name → entity, aliases → entity
        ne_name_map: dict[str, PoliticalEntity] = {}
        en_name_map: dict[str, PoliticalEntity] = {}
        for ent in entities:
            if ent.name_ne:
                ne_name_map[ent.name_ne.strip()] = ent
            if ent.name_en:
                en_name_map[ent.name_en.strip().lower()] = ent
            if ent.aliases:
                for alias in ent.aliases:
                    if isinstance(alias, str) and len(alias) > 2:
                        en_name_map[alias.strip().lower()] = ent

        # Load all party entities for creating relationships
        party_result = await db.execute(
            select(PoliticalEntity).where(PoliticalEntity.entity_type == EntityType.PARTY)
        )
        party_entities = party_result.scalars().all()
        party_map: dict[str, PoliticalEntity] = {}
        for p in party_entities:
            canon = normalize(p.name_en)
            if canon:
                party_map[canon] = p

        matched = 0
        updated_party = 0
        rels_created = 0
        seen_switches: set[str] = set()

        for switch in switches:
            name_ne = switch["name_ne"]
            from_party = switch["from_party"]
            to_party = switch["to_party"]

            # Deduplicate by Nepali name
            dedup_key = f"{name_ne}:{from_party}:{to_party}"
            if dedup_key in seen_switches:
                continue
            seen_switches.add(dedup_key)

            # Try to match entity
            ent = ne_name_map.get(name_ne)
            if not ent:
                # Try partial Nepali name match
                for ne_key, ne_ent in ne_name_map.items():
                    if name_ne in ne_key or ne_key in name_ne:
                        ent = ne_ent
                        break

            if not ent:
                continue

            matched += 1

            # Update entity's current party to the 2082 party if it changed
            current_canon = normalize(ent.party)
            to_canon = normalize(to_party)
            if to_canon and to_canon != current_canon:
                ent.party = to_canon
                updated_party += 1

            # Store switch metadata in entity's extra_data
            period = switch.get("period", "2079-2082")
            switch_meta = {
                "party_switch": {
                    "from_party": from_party,
                    "to_party": to_party,
                    "period": period,
                    "votes_2079": switch.get("votes_2079"),
                    "constituency": switch.get("constituency", ""),
                    "district": switch.get("district", ""),
                    "was_winner_2079": switch.get("was_winner", False),
                }
            }
            if ent.extra_data:
                ent.extra_data = {**ent.extra_data, **switch_meta}
            else:
                ent.extra_data = switch_meta

            # Populate former_parties JSONB on entity
            former = list(ent.former_parties or [])
            entry = {"party": from_party, "period": period, "switched_to": to_party}
            if not any(fp.get("party") == from_party and fp.get("period") == period for fp in former):
                former.append(entry)
                ent.former_parties = former

            # Find the from_party entity to create a relationship
            from_canon = normalize(from_party)
            from_party_ent = party_map.get(from_canon)
            if from_party_ent:
                # Check if relationship already exists
                existing = await db.execute(
                    select(EntityRelationship).where(
                        EntityRelationship.source_entity_id == ent.id,
                        EntityRelationship.target_entity_id == from_party_ent.id,
                        EntityRelationship.relationship_type == RelationshipType.PARTY_AFFILIATION,
                    )
                )
                if not existing.scalar_one_or_none():
                    rel = EntityRelationship(
                        source_entity_id=ent.id,
                        target_entity_id=from_party_ent.id,
                        relationship_type=RelationshipType.PARTY_AFFILIATION,
                        strength_score=0.5,
                        confidence=0.9,
                        is_verified=True,
                        verified_by="party_switch_json",
                        notes=f"Former member (switched from {from_party} to {to_party} between 2079-2082)",
                    )
                    db.add(rel)
                    rels_created += 1

            print(f"  [MATCH] {ent.name_en:35} {from_party:25} → {to_party}")

        await db.commit()

    print(f"\n{'=' * 70}")
    print(f"Party Switch Summary")
    print(f"{'=' * 70}")
    print(f"  Records processed: {len(seen_switches)}")
    print(f"  Entities matched:  {matched}")
    print(f"  Parties updated:   {updated_party}")
    print(f"  Relationships created: {rels_created}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(load_switches())
