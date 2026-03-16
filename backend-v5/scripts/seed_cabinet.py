#!/usr/bin/env python3
"""Seed current cabinet data (Sushila Karki government).

Marks old ministerial positions as not current, inserts 11 current ministers,
creates/upserts PoliticalEntity records, and creates POLITICAL_ALLY relationships.

Usage:
    cd backend-v5
    venv/bin/python3 scripts/seed_cabinet.py
"""
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.models.ministerial_position import MinisterialPosition
from app.models.political_entity import PoliticalEntity, EntityType, EntityTrend
from app.models.entity_relationship import EntityRelationship, RelationshipType

# Current cabinet as of 2082 BS (Sushila Karki caretaker government)
CURRENT_CABINET = [
    {
        "name_en": "Sushila Karki",
        "name_ne": "सुशीला कार्की",
        "canonical_id": "karki",
        "position_type": "prime_minister",
        "ministries": [
            "Defence",
            "Communication and Information Technology",
            "Education, Science and Technology",
            "Youth and Sports",
        ],
        "party": None,
    },
    {
        "name_en": "Rameshwar Prasad Khanal",
        "name_ne": "रामेश्वर प्रसाद खनाल",
        "canonical_id": "rameshwar_khanal",
        "position_type": "minister",
        "ministries": ["Finance", "Federal Affairs and General Administration"],
        "party": None,
    },
    {
        "name_en": "Om Prakash Aryal",
        "name_ne": "ओम प्रकाश अर्याल",
        "canonical_id": "om_aryal",
        "position_type": "minister",
        "ministries": ["Home Affairs"],
        "party": None,
    },
    {
        "name_en": "Anil Kumar Sinha",
        "name_ne": "अनिलकुमार सिन्हा",
        "canonical_id": "anil_sinha",
        "position_type": "minister",
        "ministries": [
            "Industry, Commerce and Supplies",
            "Law, Justice and Parliamentary Affairs",
            "Culture, Tourism and Civil Aviation",
            "Energy, Water Resources and Irrigation",
        ],
        "party": None,
    },
    {
        "name_en": "Madan Prasad Pariyar",
        "name_ne": "मदनप्रसाद परियार",
        "canonical_id": "madan_pariyar",
        "position_type": "minister",
        "ministries": [
            "Agriculture and Livestock Development",
            "Water Supply",
        ],
        "party": None,
    },
    {
        "name_en": "Sudha Gautam",
        "name_ne": "सुधा गौतम",
        "canonical_id": "sudha_gautam",
        "position_type": "minister",
        "ministries": ["Health and Population"],
        "party": None,
    },
    {
        "name_en": "Kumar Ingnam",
        "name_ne": "कुमार इङ्नाम",
        "canonical_id": "kumar_ingnam",
        "position_type": "minister",
        "ministries": [
            "Land Management, Cooperatives and Poverty Alleviation",
            "Urban Development",
        ],
        "party": None,
    },
    {
        "name_en": "Rajendra Singh Bhandari",
        "name_ne": "राजेन्द्रसिंह भण्डारी",
        "canonical_id": "rajendra_bhandari",
        "position_type": "minister",
        "ministries": ["Labour, Employment and Social Security"],
        "party": None,
    },
    {
        "name_en": "Madhav Prasad Chaulagain",
        "name_ne": "माधवप्रसाद चौलागाई",
        "canonical_id": "madhav_chaulagain",
        "position_type": "minister",
        "ministries": [
            "Forests and Environment",
            "Physical Infrastructure and Transport",
        ],
        "party": None,
    },
    {
        "name_en": "Shradha Shrestha",
        "name_ne": "श्रद्धा श्रेष्ठ",
        "canonical_id": "shradha_shrestha",
        "position_type": "minister",
        "ministries": ["Women, Children and Senior Citizens"],
        "party": None,
    },
    {
        "name_en": "Balanand Sharma",
        "name_ne": "बालानन्द शर्मा",
        "canonical_id": "balanand_sharma",
        "position_type": "minister",
        "ministries": ["Foreign Affairs"],
        "party": None,
    },
]

GOVERNMENT_NAME = "Sushila Karki Caretaker Government"
START_DATE = date(2025, 1, 13)  # Approximate appointment date


async def seed_cabinet():
    """Seed current cabinet into DB."""
    print("=" * 70)
    print("Seeding Current Cabinet - Sushila Karki Government")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        # Step 1: Mark all current ministerial positions as not current
        result = await db.execute(
            update(MinisterialPosition)
            .where(MinisterialPosition.is_current == True)  # noqa: E712
            .values(is_current=False, end_date=date.today())
        )
        print(f"\n[1/4] Marked {result.rowcount} old positions as not current")

        # Step 2: Insert ministerial positions for each cabinet member
        positions_created = 0
        for member in CURRENT_CABINET:
            ministries_str = "; ".join(member["ministries"])

            # Check if already exists
            existing = await db.execute(
                select(MinisterialPosition).where(
                    MinisterialPosition.person_name_en == member["name_en"],
                    MinisterialPosition.start_date == START_DATE,
                    MinisterialPosition.is_current == True,  # noqa: E712
                )
            )
            if existing.scalar_one_or_none():
                print(f"  [SKIP] {member['name_en']} - already exists")
                continue

            pos = MinisterialPosition(
                id=uuid4(),
                person_name_en=member["name_en"],
                person_name_ne=member["name_ne"],
                position_type=member["position_type"],
                ministry=ministries_str,
                start_date=START_DATE,
                end_date=None,
                is_current=True,
                government_name=GOVERNMENT_NAME,
                prime_minister="Sushila Karki" if member["position_type"] != "prime_minister" else None,
                party_at_appointment=member["party"],
                source="opmcm",
                notes=f"Caretaker government. Portfolios: {ministries_str}",
            )
            db.add(pos)
            positions_created += 1
            print(f"  [CREATE] {member['name_en']:30} - {member['position_type']:15} ({ministries_str})")

        await db.flush()
        print(f"\n[2/4] Created {positions_created} ministerial positions")

        # Step 3: Create/upsert PoliticalEntity records for each minister
        entities_created = 0
        entity_ids = {}  # canonical_id -> entity UUID
        pm_entity_id = None

        for member in CURRENT_CABINET:
            result = await db.execute(
                select(PoliticalEntity).where(
                    PoliticalEntity.canonical_id == member["canonical_id"]
                )
            )
            existing_entity = result.scalar_one_or_none()

            if existing_entity:
                # Update role
                role = "Prime Minister (Caretaker)" if member["position_type"] == "prime_minister" else f"Minister ({'; '.join(member['ministries'])})"
                existing_entity.role = role
                existing_entity.is_active = True
                entity_ids[member["canonical_id"]] = existing_entity.id
                if member["position_type"] == "prime_minister":
                    pm_entity_id = existing_entity.id
                print(f"  [UPDATE] {member['canonical_id']:25} - updated role")
                entities_created += 0  # not counted as new
            else:
                role = "Prime Minister (Caretaker)" if member["position_type"] == "prime_minister" else f"Minister ({'; '.join(member['ministries'])})"
                entity = PoliticalEntity(
                    canonical_id=member["canonical_id"],
                    name_en=member["name_en"],
                    name_ne=member["name_ne"],
                    entity_type=EntityType.PERSON,
                    party=member["party"],
                    role=role,
                    aliases=[member["name_ne"]],
                    description=f"Member of {GOVERNMENT_NAME}.",
                    trend=EntityTrend.STABLE,
                    is_active=True,
                )
                db.add(entity)
                await db.flush()
                entity_ids[member["canonical_id"]] = entity.id
                if member["position_type"] == "prime_minister":
                    pm_entity_id = entity.id
                entities_created += 1
                print(f"  [CREATE] {member['canonical_id']:25} - {member['name_en']}")

        print(f"\n[3/4] Created {entities_created} new political entities")

        # Step 4: Create POLITICAL_ALLY relationships (all ministers -> PM)
        relationships_created = 0
        if pm_entity_id:
            for member in CURRENT_CABINET:
                if member["position_type"] == "prime_minister":
                    continue
                src_id = entity_ids.get(member["canonical_id"])
                if not src_id:
                    continue

                # Check if relationship already exists
                existing_rel = await db.execute(
                    select(EntityRelationship).where(
                        EntityRelationship.source_entity_id == src_id,
                        EntityRelationship.target_entity_id == pm_entity_id,
                        EntityRelationship.relationship_type == RelationshipType.POLITICAL_ALLY,
                    )
                )
                if existing_rel.scalar_one_or_none():
                    continue

                rel = EntityRelationship(
                    source_entity_id=src_id,
                    target_entity_id=pm_entity_id,
                    relationship_type=RelationshipType.POLITICAL_ALLY,
                    strength_score=0.9,
                    confidence=1.0,
                    co_mention_count=0,
                    notes=f"Cabinet colleague in {GOVERNMENT_NAME}",
                    is_verified=True,
                    verified_by="seed_cabinet",
                )
                db.add(rel)
                relationships_created += 1

        await db.commit()
        print(f"\n[4/4] Created {relationships_created} POLITICAL_ALLY relationships")

    print("\n" + "=" * 70)
    print("Cabinet seeding complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(seed_cabinet())
