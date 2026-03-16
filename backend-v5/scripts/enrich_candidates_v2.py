#!/usr/bin/env python3
"""
Advanced Candidate Enrichment Script for Nepal OSINT

This script enriches 2082 election candidates with:
1. Corrected English names (fixing transliteration errors)
2. Search aliases (KP Oli, Prachanda, etc.)
3. Enhanced biographies with positions held
4. Verified data from web research

Usage:
    python scripts/enrich_candidates_v2.py
"""
import json
import re
from pathlib import Path
from typing import Optional

# Major political figures with verified data
NOTABLE_POLITICIANS = {
    # Key: name_en pattern to match -> enrichment data

    # PRIME MINISTERS & PARTY LEADERS
    "Ke.pe Sharma Ole": {
        "name_en_roman": "Khadga Prasad Sharma Oli",
        "aliases": ["KP Oli", "K.P. Oli", "Oli", "केपी ओली"],
        "biography": "Khadga Prasad Sharma Oli is a veteran Nepali politician who has served as Prime Minister four times (2015-2016, 2018-2021, 2021, 2024-2025). He is the Chairman of CPN-UML since 2014. Spent 14 years in prison (1973-1987) for pro-democracy activities. Key figure in Nepal's communist movement and known for releasing new map including Kalapani territory in 2020.",
        "biography_source": "https://en.wikipedia.org/wiki/KP_Sharma_Oli",
        "is_notable": True
    },
    "Pushp Kamal Dahal": {
        "name_en_roman": "Pushpa Kamal Dahal",
        "aliases": ["Prachanda", "प्रचण्ड", "Fierce One"],
        "biography": "Pushpa Kamal Dahal 'Prachanda' is a Nepali politician who served as Prime Minister three times (2008-2009, 2016-2017, 2022-2024). Former Maoist insurgent leader who led decade-long civil war (1996-2006). Key architect of 2006 peace process that ended monarchy. Currently Coordinator of the newly formed Nepali Communist Party.",
        "biography_source": "https://en.wikipedia.org/wiki/Pushpa_Kamal_Dahal",
        "is_notable": True
    },
    "Sher Bahadur Deub": {
        "name_en_roman": "Sher Bahadur Deuba",
        "aliases": ["SB Deuba", "Deuba"],
        "biography": "Sher Bahadur Deuba holds the record for most PM terms in Nepal's democratic history, serving five times (1995-1997, 2001-2002, 2004-2005, 2017-2018, 2021-2022). Former President of Nepali Congress (2016-2026). Imprisoned 10 years for political activities under Panchayat system. Signed Mahakali Treaty with India (1996).",
        "biography_source": "https://en.wikipedia.org/wiki/Sher_Bahadur_Deuba",
        "is_notable": True
    },
    "Rabi Lamichhane": {
        "name_en_roman": "Rabi Lamichhane",
        "aliases": ["Rabi", "रवि लामिछाने"],
        "biography": "Rabi Lamichhane is President of Rastriya Swatantra Party (RSP) which he founded in June 2022. Former investigative journalist and TV host of 'Sidha Kura Janata Sanga'. Served as Deputy Prime Minister and Home Minister (2022-2023, 2024). Guinness World Record holder for longest talk show (2013). RSP became 4th largest party in 2022 elections.",
        "biography_source": "https://en.wikipedia.org/wiki/Rabi_Lamichhane",
        "is_notable": True
    },
    "Madhaw Kumar Nepal": {
        "name_en_roman": "Madhav Kumar Nepal",
        "aliases": ["Madhav Nepal", "MK Nepal", "माधव नेपाल"],
        "biography": "Madhav Kumar Nepal served as Prime Minister (2009-2011) and was General Secretary of CPN-UML for 15 years. Key figure in 12-point peace accords that ended Maoist insurgency. Split from CPN-UML in 2021 to form CPN (Unified Socialist). Currently Co-coordinator of the merged Nepali Communist Party.",
        "biography_source": "https://en.wikipedia.org/wiki/Madhav_Kumar_Nepal",
        "is_notable": True
    },
    "Gagan Kumar Thap": {
        "name_en_roman": "Gagan Kumar Thapa",
        "aliases": ["Gagan Thapa", "गगन थापा"],
        "biography": "Gagan Kumar Thapa is the President of Nepali Congress and PM candidate for 2026 elections. Former Health Minister (2016-2017) and three-time MP. Young Global Leader of World Economic Forum. Declared Prisoner of Conscience by Amnesty International (2005) after being imprisoned during King Gyanendra's direct rule.",
        "biography_source": "https://en.wikipedia.org/wiki/Gagan_Thapa",
        "is_notable": True
    },
    "Kamal Thap": {
        "name_en_roman": "Kamal Thapa",
        "aliases": ["KT", "कमल थापा"],
        "biography": "Kamal Thapa is a veteran politician who served as Deputy Prime Minister three times and held over 12 ministerial portfolios including Home Minister and Foreign Minister. Former Chairman of RPP-Nepal (2022-2025). Former national level football player and President of All Nepal Football Association.",
        "biography_source": "https://en.wikipedia.org/wiki/Kamal_Thapa",
        "is_notable": True
    },
    "Swarnim Wagle": {
        "name_en_roman": "Swarnim Wagle",
        "aliases": ["Dr. Swarnim Wagle", "स्वर्णिम वाग्ले"],
        "biography": "Dr. Swarnim Wagle is an economist and senior leader of Rastriya Swatantra Party. Former Vice-Chairman of National Planning Commission. PhD in Economics. Known for his expertise in economic policy and development planning. Prominent voice for economic reform in Nepal.",
        "biography_source": "https://en.wikipedia.org/wiki/Swarnim_Wagle",
        "is_notable": True
    },
    "Renu Dahal": {
        "name_en_roman": "Renu Dahal",
        "aliases": ["रेणु दाहाल"],
        "biography": "Renu Dahal is a senior leader of Nepali Communist Party and daughter of former PM Pushpa Kamal Dahal (Prachanda). Former Mayor of Bharatpur Metropolitan City. Active in women's political empowerment and local governance.",
        "biography_source": None,
        "is_notable": True
    },
    "Balendra Shah": {
        "name_en_roman": "Balendra Shah",
        "aliases": ["Balen Shah", "Balen", "Mayor Balen", "बालेन शाह"],
        "biography": "Balendra 'Balen' Shah is the PM candidate of Rastriya Swatantra Party for 2026 elections. Former Mayor of Kathmandu (2022-2026) - first independent mayor elected. Rose to fame as hip-hop artist before politics. Civil engineer by profession. Symbolizes Gen Z political aspirations in Nepal.",
        "biography_source": "https://en.wikipedia.org/wiki/Balen_Shah",
        "is_notable": True
    },
    "Hark Sampang": {
        "name_en_roman": "Harka Raj Rai",
        "aliases": ["Harka Sampang", "Harka", "हर्क सम्पाङ"],
        "biography": "Harka Sampang is founder and Chairman of Shram Sanskriti Party (Labor Culture Party), formed in November 2025. Former Mayor of Dharan (2022-2026) - first independent mayor. Former migrant worker in Afghanistan. Led 'Gift a Tree' campaign planting 100,000+ saplings. Promotes 'Harkabad' philosophy of labor dignity and self-reliance.",
        "biography_source": "https://en.wikipedia.org/wiki/Harka_Sampang",
        "is_notable": True
    },
    "Upendra Yadav": {
        "name_en_roman": "Upendra Yadav",
        "aliases": ["Upendra", "उपेन्द्र यादव"],
        "biography": "Upendra Yadav is Chairman of Janata Samajbadi Party Nepal. Pioneer of Madheshi political movement. Served as Deputy Prime Minister (2018-2019, 2024), Foreign Minister (2008-2009, 2011), and Health Minister. Led first Madhesh Movement in 2007. Founder of Madheshi Jana Adhikar Forum.",
        "biography_source": "https://en.wikipedia.org/wiki/Upendra_Yadav",
        "is_notable": True
    },
    "Rajendra Lingden": {
        "name_en_roman": "Rajendra Prasad Lingden",
        "aliases": ["Lingden", "राजेन्द्र लिङ्देन"],
        "biography": "Rajendra Prasad Lingden is Chairman of Rastriya Prajatantra Party (RPP) since 2021. Served briefly as Deputy Prime Minister (2022-2023). Advocates for restoration of Hindu monarchy. Led RPP reunification with RPP-Nepal in December 2025.",
        "biography_source": "https://en.wikipedia.org/wiki/Rajendra_Lingden",
        "is_notable": True
    },
    "Bishnu Prasad Paudel": {
        "name_en_roman": "Bishnu Prasad Paudel",
        "aliases": ["Bishnu Poudel", "विष्णु पौडेल"],
        "biography": "Bishnu Prasad Paudel is Vice Chairman of CPN-UML. Served as Deputy Prime Minister and Finance Minister three times, Home Minister, and Defence Minister. Five-time parliamentarian from Rupandehi. Key figure in UML-Maoist unification (2018). Started career as primary school teacher.",
        "biography_source": "https://en.wikipedia.org/wiki/Bishnu_Prasad_Paudel",
        "is_notable": True
    },
    "Prakash Sharan Mahat": {
        "name_en_roman": "Prakash Sharan Mahat",
        "aliases": ["Dr. Mahat", "प्रकाश शरण महत"],
        "biography": "Dr. Prakash Sharan Mahat is a senior Nepali Congress leader and economist. Served as Foreign Minister and Finance Minister multiple times. PhD holder with expertise in economic policy. Key voice in Nepali Congress economic policies.",
        "biography_source": None,
        "is_notable": True
    },
    "Da Shekhar Koiral": {
        "name_en_roman": "Shashanka Koirala",
        "aliases": ["Dr. Shekhar Koirala", "Shekhar Koirala", "शेखर कोइराला"],
        "biography": "Dr. Shashanka Koirala is a senior Nepali Congress leader from the influential Koirala political family. Nephew of former PMs Girija Prasad Koirala and B.P. Koirala. Medical doctor and multiple-term parliamentarian. Contested for NC presidency multiple times.",
        "biography_source": "https://en.wikipedia.org/wiki/Shashanka_Koirala",
        "is_notable": True
    },
    "Narayan Kaji Shresth": {
        "name_en_roman": "Narayan Kaji Shrestha",
        "aliases": ["Prakash", "NK Shrestha", "नारायण काजी श्रेष्ठ"],
        "biography": "Narayan Kaji Shrestha 'Prakash' served as Deputy Prime Minister three times and Senior Vice Chair of CPN (Maoist Centre). Former Home Minister and Foreign Minister. Former mathematics lecturer. Key role in 12-point Understanding that ended civil war.",
        "biography_source": "https://en.wikipedia.org/wiki/Narayan_Kaji_Shrestha",
        "is_notable": True
    },
    "Janardan Sharma": {
        "name_en_roman": "Janardan Sharma",
        "aliases": ["Prabhakar", "जनार्दन शर्मा"],
        "biography": "Janardan Sharma 'Prabhakar' is Chairman of Progressive Campaign, Nepal. Former Finance Minister, Energy Minister (ended load-shedding crisis), Home Minister. Four-time MP from Western Rukum. Former Division Commander in Maoist insurgency. Split from Prachanda in 2025 after 42-year relationship.",
        "biography_source": "https://en.wikipedia.org/wiki/Janardan_Sharma",
        "is_notable": True
    },
    "Mahesh Basnet": {
        "name_en_roman": "Mahesh Basnet",
        "aliases": ["महेश बस्नेत"],
        "biography": "Mahesh Basnet is a CPN-UML leader and former Member of House of Representatives from Bhaktapur. PhD holder and senior academic. Active in local politics and party organization in Bhaktapur district.",
        "biography_source": None,
        "is_notable": True
    },
    "Resham Chaudhary": {
        "name_en_roman": "Resham Chaudhary",
        "aliases": ["रेशम चौधरी"],
        "biography": "Resham Chaudhary was the founder of Nagarik Unmukti Party, advocating for Tharu rights. Elected to parliament while serving life sentence for 2015 Tikapur massacre. Resigned from party in September 2025. Symbol of Tharu political mobilization.",
        "biography_source": "https://en.wikipedia.org/wiki/Resham_Chaudhary",
        "is_notable": True
    },
    "C.K. Raut": {
        "name_en_roman": "Chandra Kant Raut",
        "aliases": ["CK Raut", "Dr. CK Raut", "सी.के. राउत"],
        "biography": "Dr. C.K. Raut is Chairman of Janamat Party. Former US Defense programmer. Led separatist movement for independent Madhesh before surrendering in 2018. Founded Janamat Party in March 2019. Party holds Chief Minister position in Madhesh Province.",
        "biography_source": "https://en.wikipedia.org/wiki/C._K._Raut",
        "is_notable": True
    },
}

# Common transliteration fixes
NAME_FIXES = {
    # Pattern -> Replacement
    "Wahadur": "Bahadur",
    "Wohar": "Bohar",
    "Shahe": "Shahi",
    "Wi.k": "B.K.",
    "Bi.k": "B.K.",
    "Ke.se.": "K.C.",
    "Di.se.": "D.C.",
    "Ke.pe": "K.P.",
    "Ole": "Oli",
    "Thap ": "Thapa ",
    "Deub ": "Deuba ",
    "Shresh‍th": "Shrestha",
    "Rajawmshe": "Rajbanshi",
    "Chaudhare": "Chaudhary",
    "Kumwar": "Kunwar",
    "Gharti Magar": "Gharti",  # Remove redundant caste marker
}

# Party name standardization
PARTY_FIXES = {
    "Nepali Communist Party": "Nepali Communist Party",
    "CPN-UML": "CPN-UML",
    "Nepali Congress": "Nepali Congress",
    "Rastriya Swatantra Party": "Rastriya Swatantra Party",
    "RPP": "Rastriya Prajatantra Party",
    "CPN-Maoist Centre": "CPN-Maoist Centre",
    "Janata Samajbadi Party": "Janata Samajbadi Party",
    "Janamat Party": "Janamat Party",
    "Nagarik Unmukti Party": "Nagarik Unmukti Party",
    "Shram Sanskriti Party": "Shram Sanskriti Party",
}


def fix_transliteration(name: str) -> str:
    """Fix common transliteration errors in names."""
    fixed = name
    for pattern, replacement in NAME_FIXES.items():
        fixed = fixed.replace(pattern, replacement)
    return fixed


def find_notable_match(name_en: str, name_ne: Optional[str]) -> Optional[dict]:
    """Find if candidate matches a known notable politician."""
    name_lower = name_en.lower().strip()

    for pattern, data in NOTABLE_POLITICIANS.items():
        pattern_lower = pattern.lower()
        # Check if pattern is in the name
        if pattern_lower in name_lower or name_lower in pattern_lower:
            return data
        # Check aliases
        for alias in data.get("aliases", []):
            if alias.lower() in name_lower or name_lower in alias.lower():
                return data
    return None


def generate_basic_biography(candidate: dict, constituency: dict) -> str:
    """Generate a basic biography for non-notable candidates."""
    name = candidate.get("name_en_roman") or candidate.get("name_en", "")
    party = candidate.get("party", "")
    const_name = constituency.get("name_en", "")
    district = constituency.get("district", "")

    education = candidate.get("education", "")
    age = candidate.get("age")

    bio_parts = [f"{name} is a candidate for {party}"]
    if const_name and district:
        bio_parts.append(f"from {const_name}, {district}")

    bio = " ".join(bio_parts) + "."

    # Add education if notable
    if education and education not in ["Literate (साक्षर)", "Below SLC", "Can read and write"]:
        if "PhD" in education or "Master" in education or "Doctor" in education:
            bio += f" Education: {education}."

    return bio


def enrich_candidate(candidate: dict, constituency: dict) -> dict:
    """Enrich a single candidate with verified data."""
    name_en = candidate.get("name_en", "")
    name_ne = candidate.get("name_ne", "")

    # Fix transliteration in existing romanized name or create one
    if candidate.get("name_en_roman"):
        candidate["name_en_roman"] = fix_transliteration(candidate["name_en_roman"])
    else:
        # Create romanized name from name_en (which might be Nepali text)
        candidate["name_en_roman"] = fix_transliteration(name_en)

    # Check if this is a known notable politician
    notable_data = find_notable_match(name_en, name_ne)

    if notable_data:
        # Apply verified data
        if notable_data.get("name_en_roman"):
            candidate["name_en_roman"] = notable_data["name_en_roman"]
        if notable_data.get("aliases"):
            existing_aliases = set(candidate.get("aliases", []))
            existing_aliases.update(notable_data["aliases"])
            candidate["aliases"] = list(existing_aliases)
        if notable_data.get("biography"):
            candidate["biography"] = notable_data["biography"]
        if notable_data.get("biography_source"):
            candidate["biography_source"] = notable_data["biography_source"]
        candidate["is_notable"] = True
    else:
        # Ensure aliases list exists
        if not candidate.get("aliases"):
            candidate["aliases"] = []

        # Add name variations as aliases
        name_parts = candidate["name_en_roman"].split()
        if len(name_parts) >= 2:
            # Add surname as alias
            candidate["aliases"].append(name_parts[-1])
            # Add first + last as alias
            if len(name_parts) > 2:
                candidate["aliases"].append(f"{name_parts[0]} {name_parts[-1]}")

        # Generate basic biography if none exists
        if not candidate.get("biography"):
            candidate["biography"] = generate_basic_biography(candidate, constituency)

    # Deduplicate aliases
    if candidate.get("aliases"):
        candidate["aliases"] = list(set(candidate["aliases"]))

    return candidate


def process_election_file(filepath: Path) -> dict:
    """Process an election JSON file and enrich all candidates."""
    print(f"Processing {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {
        "total_candidates": 0,
        "notable_enriched": 0,
        "names_fixed": 0,
        "biographies_added": 0,
    }

    for constituency in data.get("results", []):
        for candidate in constituency.get("candidates", []):
            stats["total_candidates"] += 1

            original_name = candidate.get("name_en_roman", candidate.get("name_en", ""))
            had_biography = bool(candidate.get("biography"))

            # Enrich the candidate
            enrich_candidate(candidate, constituency)

            # Track stats
            new_name = candidate.get("name_en_roman", "")
            if new_name != original_name:
                stats["names_fixed"] += 1

            if candidate.get("is_notable") and find_notable_match(candidate.get("name_en", ""), None):
                stats["notable_enriched"] += 1

            if not had_biography and candidate.get("biography"):
                stats["biographies_added"] += 1

    # Save enriched data
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  Total candidates: {stats['total_candidates']}")
    print(f"  Notable politicians enriched: {stats['notable_enriched']}")
    print(f"  Names fixed: {stats['names_fixed']}")
    print(f"  Biographies added: {stats['biographies_added']}")

    return stats


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent.resolve()
    data_dir = (script_dir / "../../frontend/public/data").resolve()

    # Process 2082 election file
    election_file = data_dir / "election-results-2082.json"

    if not election_file.exists():
        print(f"Error: {election_file} not found")
        return

    print("=" * 60)
    print("ADVANCED CANDIDATE ENRICHMENT")
    print("=" * 60)

    stats = process_election_file(election_file)

    print("\n" + "=" * 60)
    print("ENRICHMENT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
