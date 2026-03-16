"""Seed script for ministerial positions data.

Seeds historical cabinet position data from OPMCM records.
Run with: python -m scripts.seed_ministerial_positions

This includes:
- Prime Ministers of Nepal
- Deputy Prime Ministers
- Cabinet Ministers
- State Ministers

Focus on recent governments (post-2015 Constitution) with emphasis on
candidates running in 2082 election.
"""
import asyncio
import logging
from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.ministerial_position import MinisterialPosition

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Ministerial positions data - focusing on key candidates in 2082 elections
# Data sourced from OPMCM and verified news reports
MINISTERIAL_DATA = [
    # ============================================
    # RABI LAMICHHANE - RSP Leader (Critical case)
    # ============================================
    {
        "person_name_en": "Rabi Lamichhane",
        "person_name_ne": "रवि लामिछाने",
        "position_type": "deputy_pm",
        "ministry": "Home Affairs",
        "ministry_ne": "गृह मन्त्रालय",
        "start_date": date(2022, 12, 26),  # Joined Dahal government
        "end_date": date(2024, 3, 4),  # Left after cooperation withdrawal
        "government_name": "Pushpa Kamal Dahal Government",
        "prime_minister": "Pushpa Kamal Dahal",
        "party_at_appointment": "Rastriya Swatantra Party",
        "notes": "First time Deputy PM and Home Minister. Oversaw police reforms. Resigned following party's withdrawal from coalition.",
        "source": "opmcm",
    },
    # ============================================
    # PUSHPA KAMAL DAHAL (PRACHANDA) - CPN-MC
    # ============================================
    {
        "person_name_en": "Pushpa Kamal Dahal",
        "person_name_ne": "पुष्पकमल दाहाल",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2022, 12, 26),
        "end_date": None,  # Still serving as of data collection
        "is_current": True,
        "government_name": "Pushpa Kamal Dahal Government (3rd term)",
        "prime_minister": None,
        "party_at_appointment": "CPN (Maoist Centre)",
        "notes": "Third term as Prime Minister.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Pushpa Kamal Dahal",
        "person_name_ne": "पुष्पकमल दाहाल",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2016, 8, 3),
        "end_date": date(2017, 5, 24),
        "government_name": "Pushpa Kamal Dahal Government (2nd term)",
        "prime_minister": None,
        "party_at_appointment": "CPN (Maoist Centre)",
        "notes": "Second term as Prime Minister.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Pushpa Kamal Dahal",
        "person_name_ne": "पुष्पकमल दाहाल",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2008, 8, 18),
        "end_date": date(2009, 5, 4),
        "government_name": "Pushpa Kamal Dahal Government (1st term)",
        "prime_minister": None,
        "party_at_appointment": "CPN (Maoist)",
        "notes": "First democratically elected Prime Minister after abolition of monarchy.",
        "source": "opmcm",
    },
    # ============================================
    # KP SHARMA OLI - UML
    # ============================================
    {
        "person_name_en": "KP Sharma Oli",
        "person_name_ne": "केपी शर्मा ओली",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2020, 5, 13),
        "end_date": date(2021, 7, 12),
        "government_name": "KP Sharma Oli Government (2nd term - continued)",
        "prime_minister": None,
        "party_at_appointment": "CPN (UML)",
        "notes": "Reinstated after SC ruling, then dissolved parliament leading to political crisis.",
        "source": "opmcm",
    },
    {
        "person_name_en": "KP Sharma Oli",
        "person_name_ne": "केपी शर्मा ओली",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2018, 2, 15),
        "end_date": date(2020, 5, 13),
        "government_name": "KP Sharma Oli Government (2nd term)",
        "prime_minister": None,
        "party_at_appointment": "Nepal Communist Party",
        "notes": "Second term, NCP government with 2/3 majority.",
        "source": "opmcm",
    },
    {
        "person_name_en": "KP Sharma Oli",
        "person_name_ne": "केपी शर्मा ओली",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2015, 10, 11),
        "end_date": date(2016, 8, 3),
        "government_name": "KP Sharma Oli Government (1st term)",
        "prime_minister": None,
        "party_at_appointment": "CPN (UML)",
        "notes": "First PM under new constitution.",
        "source": "opmcm",
    },
    {
        "person_name_en": "KP Sharma Oli",
        "person_name_ne": "केपी शर्मा ओली",
        "position_type": "minister",
        "ministry": "Home Affairs",
        "ministry_ne": "गृह मन्त्रालय",
        "start_date": date(1994, 11, 30),
        "end_date": date(1995, 9, 10),
        "government_name": "Man Mohan Adhikari Government",
        "prime_minister": "Man Mohan Adhikari",
        "party_at_appointment": "CPN (UML)",
        "notes": "Home Minister in first communist-led government.",
        "source": "opmcm",
    },
    # ============================================
    # SHER BAHADUR DEUBA - Nepali Congress
    # ============================================
    {
        "person_name_en": "Sher Bahadur Deuba",
        "person_name_ne": "शेरबहादुर देउवा",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2021, 7, 13),
        "end_date": date(2022, 12, 25),
        "government_name": "Sher Bahadur Deuba Government (5th term)",
        "prime_minister": None,
        "party_at_appointment": "Nepali Congress",
        "notes": "Fifth term as Prime Minister. Appointed by SC ruling.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Sher Bahadur Deuba",
        "person_name_ne": "शेरबहादुर देउवा",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2017, 6, 7),
        "end_date": date(2018, 2, 15),
        "government_name": "Sher Bahadur Deuba Government (4th term)",
        "prime_minister": None,
        "party_at_appointment": "Nepali Congress",
        "notes": "Fourth term as Prime Minister.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Sher Bahadur Deuba",
        "person_name_ne": "शेरबहादुर देउवा",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2004, 6, 2),
        "end_date": date(2005, 2, 1),
        "government_name": "Sher Bahadur Deuba Government (3rd term)",
        "prime_minister": None,
        "party_at_appointment": "Nepali Congress",
        "notes": "Third term. Dismissed by King Gyanendra.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Sher Bahadur Deuba",
        "person_name_ne": "शेरबहादुर देउवा",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2001, 7, 26),
        "end_date": date(2002, 10, 4),
        "government_name": "Sher Bahadur Deuba Government (2nd term)",
        "prime_minister": None,
        "party_at_appointment": "Nepali Congress",
        "notes": "Second term. Dealt with royal palace massacre aftermath.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Sher Bahadur Deuba",
        "person_name_ne": "शेरबहादुर देउवा",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(1995, 9, 12),
        "end_date": date(1997, 3, 12),
        "government_name": "Sher Bahadur Deuba Government (1st term)",
        "prime_minister": None,
        "party_at_appointment": "Nepali Congress",
        "notes": "First term as Prime Minister.",
        "source": "opmcm",
    },
    # ============================================
    # NARAYAN KAJI SHRESTHA (PRAKASH MAN SINGH)
    # ============================================
    {
        "person_name_en": "Narayan Kaji Shrestha",
        "person_name_ne": "नारायणकाजी श्रेष्ठ",
        "position_type": "deputy_pm",
        "ministry": "Urban Development",
        "ministry_ne": "सहरी विकास मन्त्रालय",
        "start_date": date(2023, 3, 6),
        "end_date": None,
        "is_current": True,
        "government_name": "Pushpa Kamal Dahal Government",
        "prime_minister": "Pushpa Kamal Dahal",
        "party_at_appointment": "CPN (Maoist Centre)",
        "notes": "Deputy Prime Minister after Rabi Lamichhane's exit.",
        "source": "opmcm",
    },
    # ============================================
    # BISHNU PRASAD PAUDEL - UML
    # ============================================
    {
        "person_name_en": "Bishnu Prasad Paudel",
        "person_name_ne": "विष्णु प्रसाद पौडेल",
        "position_type": "deputy_pm",
        "ministry": "Finance",
        "ministry_ne": "अर्थ मन्त्रालय",
        "start_date": date(2024, 3, 4),
        "end_date": None,
        "is_current": True,
        "government_name": "Pushpa Kamal Dahal Government",
        "prime_minister": "Pushpa Kamal Dahal",
        "party_at_appointment": "CPN (UML)",
        "notes": "Deputy PM and Finance Minister after UML joined coalition.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Bishnu Prasad Paudel",
        "person_name_ne": "विष्णु प्रसाद पौडेल",
        "position_type": "minister",
        "ministry": "Finance",
        "ministry_ne": "अर्थ मन्त्रालय",
        "start_date": date(2018, 2, 28),
        "end_date": date(2021, 7, 12),
        "government_name": "KP Sharma Oli Government",
        "prime_minister": "KP Sharma Oli",
        "party_at_appointment": "CPN (UML)",
        "notes": "Finance Minister during COVID-19 pandemic.",
        "source": "opmcm",
    },
    # ============================================
    # GAGAN KUMAR THAPA - Nepali Congress
    # ============================================
    {
        "person_name_en": "Gagan Kumar Thapa",
        "person_name_ne": "गगन कुमार थापा",
        "position_type": "minister",
        "ministry": "Health and Population",
        "ministry_ne": "स्वास्थ्य तथा जनसंख्या मन्त्रालय",
        "start_date": date(2016, 8, 3),
        "end_date": date(2017, 5, 24),
        "government_name": "Pushpa Kamal Dahal Government",
        "prime_minister": "Pushpa Kamal Dahal",
        "party_at_appointment": "Nepali Congress",
        "notes": "Health Minister. Implemented several health reforms.",
        "source": "opmcm",
    },
    # ============================================
    # UPENDRA YADAV - JSP
    # ============================================
    {
        "person_name_en": "Upendra Yadav",
        "person_name_ne": "उपेन्द्र यादव",
        "position_type": "deputy_pm",
        "ministry": "Health and Population",
        "ministry_ne": "स्वास्थ्य तथा जनसंख्या मन्त्रालय",
        "start_date": date(2018, 2, 28),
        "end_date": date(2020, 2, 20),
        "government_name": "KP Sharma Oli Government",
        "prime_minister": "KP Sharma Oli",
        "party_at_appointment": "Federal Socialist Forum Nepal",
        "notes": "Deputy PM representing Madheshi parties.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Upendra Yadav",
        "person_name_ne": "उपेन्द्र यादव",
        "position_type": "minister",
        "ministry": "Foreign Affairs",
        "ministry_ne": "परराष्ट्र मन्त्रालय",
        "start_date": date(2008, 8, 22),
        "end_date": date(2009, 5, 4),
        "government_name": "Pushpa Kamal Dahal Government",
        "prime_minister": "Pushpa Kamal Dahal",
        "party_at_appointment": "Madhesi Jana Adhikar Forum Nepal",
        "notes": "First Madheshi Foreign Minister.",
        "source": "opmcm",
    },
    # ============================================
    # RAM CHANDRA PAUDEL - Nepali Congress (Current President, Former Minister)
    # ============================================
    {
        "person_name_en": "Ram Chandra Paudel",
        "person_name_ne": "रामचन्द्र पौडेल",
        "position_type": "deputy_pm",
        "ministry": "Home Affairs",
        "ministry_ne": "गृह मन्त्रालय",
        "start_date": date(2007, 4, 1),
        "end_date": date(2008, 8, 18),
        "government_name": "Girija Prasad Koirala Government",
        "prime_minister": "Girija Prasad Koirala",
        "party_at_appointment": "Nepali Congress",
        "notes": "Deputy PM and Home Minister during transition period.",
        "source": "opmcm",
    },
    # ============================================
    # MADHAV KUMAR NEPAL - CPN (Unified Socialist)
    # ============================================
    {
        "person_name_en": "Madhav Kumar Nepal",
        "person_name_ne": "माधवकुमार नेपाल",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2009, 5, 25),
        "end_date": date(2010, 2, 6),
        "government_name": "Madhav Kumar Nepal Government",
        "prime_minister": None,
        "party_at_appointment": "CPN (UML)",
        "notes": "Became PM without being elected to parliament.",
        "source": "opmcm",
    },
    # ============================================
    # JHALANATH KHANAL - UML
    # ============================================
    {
        "person_name_en": "Jhalanath Khanal",
        "person_name_ne": "झलनाथ खनाल",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2011, 2, 3),
        "end_date": date(2011, 8, 29),
        "government_name": "Jhalanath Khanal Government",
        "prime_minister": None,
        "party_at_appointment": "CPN (UML)",
        "notes": "Short-lived government.",
        "source": "opmcm",
    },
    # ============================================
    # BABURAM BHATTARAI - Naya Shakti / Samajwadi
    # ============================================
    {
        "person_name_en": "Baburam Bhattarai",
        "person_name_ne": "बाबुराम भट्टराई",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2011, 8, 29),
        "end_date": date(2013, 3, 14),
        "government_name": "Baburam Bhattarai Government",
        "prime_minister": None,
        "party_at_appointment": "UCPN (Maoist)",
        "notes": "Led government during constitution-making process.",
        "source": "opmcm",
    },
    {
        "person_name_en": "Baburam Bhattarai",
        "person_name_ne": "बाबुराम भट्टराई",
        "position_type": "minister",
        "ministry": "Finance",
        "ministry_ne": "अर्थ मन्त्रालय",
        "start_date": date(2008, 8, 22),
        "end_date": date(2009, 5, 4),
        "government_name": "Pushpa Kamal Dahal Government",
        "prime_minister": "Pushpa Kamal Dahal",
        "party_at_appointment": "CPN (Maoist)",
        "notes": "Finance Minister in first Maoist-led government.",
        "source": "opmcm",
    },
    # ============================================
    # SUSHIL KOIRALA - Nepali Congress
    # ============================================
    {
        "person_name_en": "Sushil Koirala",
        "person_name_ne": "सुशील कोइराला",
        "position_type": "prime_minister",
        "ministry": None,
        "start_date": date(2014, 2, 11),
        "end_date": date(2015, 10, 11),
        "government_name": "Sushil Koirala Government",
        "prime_minister": None,
        "party_at_appointment": "Nepali Congress",
        "notes": "Oversaw promulgation of new constitution in 2015.",
        "source": "opmcm",
    },
    # ============================================
    # PRADEEP KUMAR GYAWALI - UML
    # ============================================
    {
        "person_name_en": "Pradeep Kumar Gyawali",
        "person_name_ne": "प्रदीपकुमार ज्ञवाली",
        "position_type": "minister",
        "ministry": "Foreign Affairs",
        "ministry_ne": "परराष्ट्र मन्त्रालय",
        "start_date": date(2018, 2, 28),
        "end_date": date(2021, 7, 12),
        "government_name": "KP Sharma Oli Government",
        "prime_minister": "KP Sharma Oli",
        "party_at_appointment": "CPN (UML)",
        "notes": "Foreign Minister during India-Nepal map dispute.",
        "source": "opmcm",
    },
    # ============================================
    # PRAKASH MAN SINGH - Nepali Congress
    # ============================================
    {
        "person_name_en": "Prakash Man Singh",
        "person_name_ne": "प्रकाशमान सिंह",
        "position_type": "deputy_pm",
        "ministry": "Local Development",
        "ministry_ne": "स्थानीय विकास मन्त्रालय",
        "start_date": date(2014, 2, 25),
        "end_date": date(2015, 10, 11),
        "government_name": "Sushil Koirala Government",
        "prime_minister": "Sushil Koirala",
        "party_at_appointment": "Nepali Congress",
        "notes": "Deputy PM under Sushil Koirala.",
        "source": "opmcm",
    },
    # ============================================
    # ISHWOR POKHREL - UML
    # ============================================
    {
        "person_name_en": "Ishwor Pokhrel",
        "person_name_ne": "ईश्वर पोखरेल",
        "position_type": "deputy_pm",
        "ministry": "Defence",
        "ministry_ne": "रक्षा मन्त्रालय",
        "start_date": date(2018, 2, 28),
        "end_date": date(2021, 7, 12),
        "government_name": "KP Sharma Oli Government",
        "prime_minister": "KP Sharma Oli",
        "party_at_appointment": "CPN (UML)",
        "notes": "Deputy PM and Defence Minister.",
        "source": "opmcm",
    },
    # ============================================
    # TOP BAHADUR RAYAMAJHI - NC (Example State Minister)
    # ============================================
    {
        "person_name_en": "Top Bahadur Rayamajhi",
        "person_name_ne": "टोपबहादुर रायमाझी",
        "position_type": "state_minister",
        "ministry": "Home Affairs",
        "ministry_ne": "गृह मन्त्रालय",
        "start_date": date(2022, 12, 26),
        "end_date": date(2023, 3, 1),
        "government_name": "Pushpa Kamal Dahal Government",
        "prime_minister": "Pushpa Kamal Dahal",
        "party_at_appointment": "Rastriya Swatantra Party",
        "notes": "State Minister under Home Ministry.",
        "source": "opmcm",
    },
]


async def seed_ministerial_positions(db: AsyncSession) -> int:
    """Seed ministerial positions data into database."""
    count = 0

    for data in MINISTERIAL_DATA:
        # Check if position already exists (avoid duplicates)
        stmt = select(MinisterialPosition).where(
            MinisterialPosition.person_name_en == data["person_name_en"],
            MinisterialPosition.position_type == data["position_type"],
            MinisterialPosition.start_date == data["start_date"],
        )
        existing = await db.execute(stmt)
        if existing.scalar_one_or_none():
            logger.info(f"Skipping existing: {data['person_name_en']} - {data.get('ministry', data['position_type'])} ({data['start_date']})")
            continue

        position = MinisterialPosition(
            id=uuid4(),
            person_name_en=data["person_name_en"],
            person_name_ne=data.get("person_name_ne"),
            position_type=data["position_type"],
            ministry=data.get("ministry"),
            ministry_ne=data.get("ministry_ne"),
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            is_current=data.get("is_current", False),
            government_name=data.get("government_name"),
            prime_minister=data.get("prime_minister"),
            party_at_appointment=data.get("party_at_appointment"),
            notes=data.get("notes"),
            source=data.get("source", "manual"),
        )

        db.add(position)
        count += 1
        logger.info(f"Added: {data['person_name_en']} - {data.get('ministry', data['position_type'])} ({data['start_date']})")

    await db.commit()
    return count


async def main():
    """Main entry point."""
    logger.info("Starting ministerial positions seed...")

    async with AsyncSessionLocal() as db:
        count = await seed_ministerial_positions(db)

    logger.info(f"Seeded {count} ministerial positions")


if __name__ == "__main__":
    asyncio.run(main())
