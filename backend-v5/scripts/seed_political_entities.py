#!/usr/bin/env python3
"""
Seed initial political entities for the Nepal OSINT Platform.

Creates canonical entities from NEPAL_ENTITY_ALIASES in feature_extractor.py.
These entities form the knowledge base for tracking political actors.

Usage:
    cd backend-v5
    python scripts/seed_political_entities.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.models.political_entity import PoliticalEntity, EntityType, EntityTrend


# Canonical entities derived from NEPAL_ENTITY_ALIASES in feature_extractor.py
# Extended with metadata for Palantir-grade entity tracking
POLITICAL_ENTITIES = [
    # ---------- Key Political Figures (PERSON) ----------
    {
        "canonical_id": "oli",
        "name_en": "KP Sharma Oli",
        "name_ne": "केपी शर्मा ओली",
        "entity_type": EntityType.PERSON,
        "party": "CPN-UML",
        "role": "Former Prime Minister, Party Chair",
        "aliases": ["ओली", "केपी ओली", "के.पी. ओली", "ओलीले", "ओलीको", "ओलीका", "ओलीलाई", "केपी", "kp oli", "k.p. oli"],
        "description": "Chairman of CPN-UML and former Prime Minister of Nepal.",
    },
    {
        "canonical_id": "prachanda",
        "name_en": "Pushpa Kamal Dahal",
        "name_ne": "पुष्पकमल दाहाल (प्रचण्ड)",
        "entity_type": EntityType.PERSON,
        "party": "CPN Maoist Centre",
        "role": "Former Prime Minister, Party Chair",
        "aliases": ["प्रचण्ड", "दाहाल", "प्रचण्डले", "प्रचण्डको", "dahal"],
        "description": "Chairman of CPN Maoist Centre and former Prime Minister.",
    },
    {
        "canonical_id": "deuba",
        "name_en": "Sher Bahadur Deuba",
        "name_ne": "शेर बहादुर देउवा",
        "entity_type": EntityType.PERSON,
        "party": "Nepali Congress",
        "role": "Party President, Former Prime Minister",
        "aliases": ["देउवा", "शेरबहादुर देउवा", "देउवाले", "देउवाको"],
        "description": "President of Nepali Congress and former Prime Minister.",
    },
    {
        "canonical_id": "karki",
        "name_en": "Sushila Karki",
        "name_ne": "सुशिला कार्की",
        "entity_type": EntityType.PERSON,
        "party": None,
        "role": "Prime Minister (Caretaker), Former Chief Justice",
        "aliases": ["कार्की", "कार्कीले", "कार्कीको", "कार्कीसँग", "प्रधानमन्त्री कार्की", "pm karki", "prime minister karki"],
        "description": "Caretaker Prime Minister of Nepal and former Chief Justice.",
    },
    {
        "canonical_id": "bhattarai",
        "name_en": "Baburam Bhattarai",
        "name_ne": "बाबुराम भट्टराई",
        "entity_type": EntityType.PERSON,
        "party": None,
        "role": "Former Prime Minister",
        "aliases": ["भट्टराई", "बाबुराम", "baburam"],
        "description": "Former Prime Minister and prominent political figure.",
    },
    {
        "canonical_id": "madhav_nepal",
        "name_en": "Madhav Kumar Nepal",
        "name_ne": "माधवकुमार नेपाल",
        "entity_type": EntityType.PERSON,
        "party": "CPN (Unified Socialist)",
        "role": "Party Chair, Former Prime Minister",
        "aliases": ["माधव नेपाल", "माधव कुमार नेपाल", "माधवले"],
        "description": "Chairman of CPN (Unified Socialist) and former Prime Minister.",
    },
    {
        "canonical_id": "upendra_yadav",
        "name_en": "Upendra Yadav",
        "name_ne": "उपेन्द्र यादव",
        "entity_type": EntityType.PERSON,
        "party": "Janata Samajbadi Party",
        "role": "Party Leader",
        "aliases": ["यादव", "उपेन्द्रले"],
        "description": "Leader of Janata Samajbadi Party.",
    },
    {
        "canonical_id": "lamichhane",
        "name_en": "Rabi Lamichhane",
        "name_ne": "रवि लामिछाने",
        "entity_type": EntityType.PERSON,
        "party": "Rastriya Swatantra Party",
        "role": "Party Chair, Former Home Minister",
        "aliases": ["लामिछाने", "रविले", "लामिछानेले", "rabi lamichhane"],
        "description": "Chairman of Rastriya Swatantra Party and former Home Minister.",
    },
    {
        "canonical_id": "gagan_thapa",
        "name_en": "Gagan Thapa",
        "name_ne": "गगन थापा",
        "entity_type": EntityType.PERSON,
        "party": "Nepali Congress",
        "role": "General Secretary",
        "aliases": ["गगनले", "थापा"],
        "description": "General Secretary of Nepali Congress.",
    },
    {
        "canonical_id": "balen",
        "name_en": "Balen Shah",
        "name_ne": "बालेन शाह",
        "entity_type": EntityType.PERSON,
        "party": "Independent",
        "role": "Mayor of Kathmandu",
        "aliases": ["बालेन"],
        "description": "Mayor of Kathmandu Metropolitan City.",
    },
    {
        "canonical_id": "rc_poudel",
        "name_en": "Ram Chandra Poudel",
        "name_ne": "रामचन्द्र पौडेल",
        "entity_type": EntityType.PERSON,
        "party": "Nepali Congress",
        "role": "President of Nepal",
        "aliases": ["पौडेल", "राष्ट्रपति पौडेल", "poudel"],
        "description": "President of Nepal.",
    },
    {
        "canonical_id": "bhandari",
        "name_en": "Bidya Devi Bhandari",
        "name_ne": "विद्यादेवी भण्डारी",
        "entity_type": EntityType.PERSON,
        "party": "CPN-UML",
        "role": "Former President",
        "aliases": ["भण्डारी"],
        "description": "Former President of Nepal.",
    },

    # ---------- Major Political Parties (PARTY) ----------
    {
        "canonical_id": "uml",
        "name_en": "CPN-UML",
        "name_ne": "नेकपा एमाले",
        "entity_type": EntityType.PARTY,
        "party": None,
        "role": "Major Political Party",
        "aliases": ["एमाले", "नेकपा (एमाले)", "एमालेले", "CPN UML", "Communist Party of Nepal UML"],
        "description": "Communist Party of Nepal (Unified Marxist-Leninist).",
    },
    {
        "canonical_id": "nc",
        "name_en": "Nepali Congress",
        "name_ne": "नेपाली कांग्रेस",
        "entity_type": EntityType.PARTY,
        "party": None,
        "role": "Major Political Party",
        "aliases": ["कांग्रेस", "कांग्रेसले", "Congress", "NC"],
        "description": "Nepali Congress - oldest democratic party in Nepal.",
    },
    {
        "canonical_id": "maoist",
        "name_en": "CPN Maoist Centre",
        "name_ne": "नेकपा माओवादी केन्द्र",
        "entity_type": EntityType.PARTY,
        "party": None,
        "role": "Major Political Party",
        "aliases": ["माओवादी", "माओवादी केन्द्र", "माओवादीले", "Maoist", "CPN-MC"],
        "description": "Communist Party of Nepal (Maoist Centre).",
    },
    {
        "canonical_id": "rsp",
        "name_en": "Rastriya Swatantra Party",
        "name_ne": "राष्ट्रिय स्वतन्त्र पार्टी",
        "entity_type": EntityType.PARTY,
        "party": None,
        "role": "Political Party",
        "aliases": ["रास्वपा", "स्वतन्त्र पार्टी", "RSP"],
        "description": "Rastriya Swatantra Party - new political party.",
    },
    {
        "canonical_id": "jsp",
        "name_en": "Janata Samajbadi Party",
        "name_ne": "जनता समाजवादी पार्टी",
        "entity_type": EntityType.PARTY,
        "party": None,
        "role": "Political Party",
        "aliases": ["जसपा", "जसपाले", "JSP"],
        "description": "Janata Samajbadi Party - Madhesh-based party.",
    },

    # ---------- Key Institutions (INSTITUTION) ----------
    {
        "canonical_id": "supreme_court",
        "name_en": "Supreme Court",
        "name_ne": "सर्वोच्च अदालत",
        "entity_type": EntityType.INSTITUTION,
        "party": None,
        "role": "Judiciary",
        "aliases": ["सर्वोच्च", "अदालत"],
        "description": "Supreme Court of Nepal - highest judicial body.",
    },
    {
        "canonical_id": "election_commission",
        "name_en": "Election Commission",
        "name_ne": "निर्वाचन आयोग",
        "entity_type": EntityType.INSTITUTION,
        "party": None,
        "role": "Constitutional Body",
        "aliases": ["निर्वाचन", "आयोग", "EC"],
        "description": "Election Commission of Nepal.",
    },
    {
        "canonical_id": "parliament",
        "name_en": "Parliament",
        "name_ne": "संसद",
        "entity_type": EntityType.INSTITUTION,
        "party": None,
        "role": "Legislature",
        "aliases": ["प्रतिनिधिसभा", "राष्ट्रियसभा", "House of Representatives", "National Assembly"],
        "description": "Federal Parliament of Nepal.",
    },
]


async def seed_political_entities():
    """Create political entities if they don't exist."""
    print("=" * 70)
    print("Seeding Political Entities for Nepal OSINT Platform")
    print("=" * 70)

    created_count = 0
    skipped_count = 0

    async with AsyncSessionLocal() as db:
        for entity_data in POLITICAL_ENTITIES:
            # Check if entity exists
            result = await db.execute(
                select(PoliticalEntity).where(
                    PoliticalEntity.canonical_id == entity_data["canonical_id"]
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                print(f"  [SKIP] {entity_data['canonical_id']:20} - {entity_data['name_en']}")
                skipped_count += 1
                continue

            # Create entity
            entity = PoliticalEntity(
                canonical_id=entity_data["canonical_id"],
                name_en=entity_data["name_en"],
                name_ne=entity_data.get("name_ne"),
                entity_type=entity_data["entity_type"],
                party=entity_data.get("party"),
                role=entity_data.get("role"),
                aliases=entity_data.get("aliases"),
                description=entity_data.get("description"),
                trend=EntityTrend.STABLE,
            )
            db.add(entity)
            await db.commit()
            print(f"  [CREATE] {entity_data['canonical_id']:20} - {entity_data['name_en']}")
            created_count += 1

    print("\n" + "=" * 70)
    print(f"Summary: {created_count} created, {skipped_count} skipped")
    print("=" * 70)

    # Print entity list for reference
    print("\nEntity Reference:")
    print("-" * 70)
    print(f"{'CANONICAL_ID':<20} {'TYPE':<12} {'NAME':<30}")
    print("-" * 70)
    for e in POLITICAL_ENTITIES:
        print(f"{e['canonical_id']:<20} {e['entity_type'].value:<12} {e['name_en']:<30}")
    print("-" * 70)


if __name__ == "__main__":
    asyncio.run(seed_political_entities())
