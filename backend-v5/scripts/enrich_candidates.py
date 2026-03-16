#!/usr/bin/env python3
"""
Candidate Data Enrichment Script

This script:
1. Transliterates Nepali candidate names to English (romanization)
2. Searches for biographical information for notable candidates
3. Updates the election JSON files with enriched data

Major parties prioritized:
- Nepali Congress
- CPN-UML
- CPN (Maoist Centre)
- Rastriya Swatantra Party (RSP)
- Janata Samajbadi Party (JSP)
- RPP
- Loktantrik Samajbadi Party
- And other major parties

Usage:
    python scripts/enrich_candidates.py --year 2082 --batch-size 50
"""
import argparse
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Nepali to English transliteration mapping
NEPALI_CONSONANTS = {
    'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
    'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
    'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
    'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
    'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
    'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'w', 'श': 'sh',
    'ष': 'sh', 'स': 's', 'ह': 'h', 'क्ष': 'ksh', 'त्र': 'tr',
    'ज्ञ': 'gya',
}

NEPALI_VOWELS = {
    'अ': 'a', 'आ': 'aa', 'इ': 'i', 'ई': 'ee', 'उ': 'u',
    'ऊ': 'oo', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
    'अं': 'am', 'अः': 'ah',
}

NEPALI_VOWEL_SIGNS = {
    'ा': 'a', 'ि': 'i', 'ी': 'ee', 'ु': 'u', 'ू': 'oo',
    'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'm',
    'ः': 'h', '्': '',  # Halant (removes inherent 'a')
    'ँ': 'n',  # Chandrabindu
}

# Special combinations
NEPALI_SPECIAL = {
    'ृ': 'ri', 'ॄ': 'ree',
}

# Major parties to prioritize for biography search
MAJOR_PARTIES = [
    'Nepali Congress', 'NC', 'Congress',
    'CPN-UML', 'UML', 'CPN (UML)',
    'CPN (Maoist Centre)', 'Maoist', 'CPN-MC', 'CPN (MC)',
    'Rastriya Swatantra Party', 'RSP',
    'Janata Samajbadi Party', 'JSP', 'JSP Nepal',
    'RPP', 'Rastriya Prajatantra Party',
    'Loktantrik Samajbadi Party', 'LSP',
    'Nagarik Unmukti Party', 'NUP',
    'Nepal Workers Peasants Party', 'NWPP',
    'Janamat Party',
    'Nepali Communist Party', 'NCP',
    'Nepal Samajbadi Party',
]


def transliterate_nepali(text: str) -> str:
    """Transliterate Nepali text to English/Roman script.

    Uses ISO 15919 inspired transliteration with common English adaptations.
    """
    if not text:
        return ""

    result = []
    i = 0
    text = text.strip()

    while i < len(text):
        char = text[i]

        # Check for space
        if char == ' ':
            result.append(' ')
            i += 1
            continue

        # Check for special combinations
        if char in NEPALI_SPECIAL:
            result.append(NEPALI_SPECIAL[char])
            i += 1
            continue

        # Check for standalone vowels
        if char in NEPALI_VOWELS:
            result.append(NEPALI_VOWELS[char])
            i += 1
            continue

        # Check for vowel signs (matras) - these replace inherent 'a'
        if char in NEPALI_VOWEL_SIGNS:
            result.append(NEPALI_VOWEL_SIGNS[char])
            i += 1
            continue

        # Check for consonants
        if char in NEPALI_CONSONANTS:
            result.append(NEPALI_CONSONANTS[char])
            i += 1

            # Look ahead for halant or vowel sign
            if i < len(text):
                next_char = text[i]
                if next_char == '्':  # Halant - no inherent vowel
                    i += 1
                elif next_char in NEPALI_VOWEL_SIGNS:
                    # Vowel sign will be processed in next iteration
                    pass
                elif next_char in NEPALI_CONSONANTS or next_char == ' ':
                    # Next is consonant or space - add inherent 'a'
                    result.append('a')
                elif next_char in NEPALI_VOWELS:
                    # Standalone vowel follows - add inherent 'a'
                    result.append('a')
            else:
                # End of string - add inherent 'a'
                result.append('a')
            continue

        # Pass through other characters (numbers, punctuation, etc.)
        result.append(char)
        i += 1

    # Clean up the result
    name = ''.join(result)

    # Post-processing fixes for common patterns
    # Remove trailing 'a' from words (common in Nepali names)
    words = name.split()
    fixed_words = []
    for word in words:
        # Remove trailing 'a' unless it's a short word or specific pattern
        if len(word) > 2 and word.endswith('a') and not word.endswith(('aa', 'ia', 'ua')):
            word = word[:-1]
        fixed_words.append(word)
    name = ' '.join(fixed_words)

    # Common name corrections (order matters - more specific first)
    corrections = [
        # Common surnames and titles
        (r'\bBahadur\b', 'Bahadur'),  # Keep as is
        (r'\bBahadura?\b', 'Bahadur'),
        (r'\bKumar\b', 'Kumar'),
        (r'\bSharm\b', 'Sharma'),
        (r'\bRawal\b', 'Rawal'),
        (r'\bShah\b', 'Shah'),
        (r'\bDahal\b', 'Dahal'),
        (r'\bThap\b', 'Thapa'),
        (r'\bKhadk\b', 'Khadka'),
        (r'\bGurung\b', 'Gurung'),
        (r'\bTamang\b', 'Tamang'),
        (r'\bShresth\b', 'Shrestha'),
        (r'\bPoudel\b', 'Poudel'),
        (r'\bPudel\b', 'Poudel'),
        (r'\bAdhikar\b', 'Adhikari'),
        (r'\bBhattara\b', 'Bhattarai'),
        (r'\bGauatam\b', 'Gautam'),
        (r'\bKc\b', 'KC'),
        (r'\bBk\b', 'BK'),
        # Common first names
        (r'\bRam\b', 'Ram'),
        (r'\bSher\b', 'Sher'),
        (r'\bBhim\b', 'Bhim'),
        (r'\bRab\b', 'Rabi'),
        (r'\bRaw\b', 'Ravi'),
        (r'\bOl\b', 'Oli'),
        (r'\bDipak\b', 'Dipak'),
        (r'\bDipk\b', 'Dipak'),
        (r'\bPushp\b', 'Pushpa'),
        (r'\bKamal\b', 'Kamal'),
        (r'\bGagan\b', 'Gagan'),
        (r'\bBishnu\b', 'Bishnu'),
        (r'\bWishnu\b', 'Bishnu'),
        (r'\bNarayan\b', 'Narayan'),
        (r'\bKaj\b', 'Kaji'),
        (r'\bDew\b', 'Deuba'),
        (r'\bDeuw\b', 'Deuba'),
        (r'\bKep\b', 'KP'),
        (r'\bSumd\b', 'Saund'),
        (r'\bSaumd\b', 'Saund'),
        (r'\bSwar\b', 'Swar'),
        (r'\bLokend\b', 'Lokendra'),
        (r'\bLokendr\b', 'Lokendra'),
        (r'\bLamichhan\b', 'Lamichhane'),
        (r'\bOmaprakash\b', 'Om Prakash'),
        (r'\bOmprakash\b', 'Om Prakash'),
        (r'\bBhem\b', 'Bhim'),
        (r'\bKepe\b', 'KP'),
        (r'\bOle\b', 'Oli'),
        (r'\bRawi\b', 'Rabi'),
        (r'\bShreshth\b', 'Shrestha'),
        (r'\bKaje\b', 'Kaji'),
        (r'\bPaudel\b', 'Poudel'),
        (r'\bPodel\b', 'Poudel'),
        (r'\bYadaw\b', 'Yadav'),
        (r'\bChaudhar\b', 'Chaudhary'),
        (r'\bMaharjan\b', 'Maharjan'),
        (r'\bManandhar\b', 'Manandhar'),
        (r'\bJosh\b', 'Joshi'),
        (r'\bKark\b', 'Karki'),
        (r'\bMall\b', 'Malla'),
        (r'\bNepal\b', 'Nepal'),
        (r'\bPradhan\b', 'Pradhan'),
        (r'\bSingh\b', 'Singh'),
        (r'\bLam\b', 'Lama'),
        (r'\bMagar\b', 'Magar'),
        (r'\bPant\b', 'Pant'),
        (r'\bRegm\b', 'Regmi'),
        (r'\bBasnet\b', 'Basnet'),
        (r'\bBhandari\b', 'Bhandari'),
        (r'\bOjha\b', 'Ojha'),
        (r'\bMishr\b', 'Mishra'),
        (r'\bPandit\b', 'Pandit'),
        (r'\bTiwar\b', 'Tiwari'),
        # Fix vowels
        (r'([aeiou])\1+', r'\1'),  # Remove repeated vowels
    ]
    for pattern, replacement in corrections:
        name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)

    name = re.sub(r'\s+', ' ', name)  # Multiple spaces to single
    name = name.strip()

    # Capitalize each word
    name = ' '.join(word.capitalize() for word in name.split())

    return name


def generate_aliases(nepali_name: str, roman_name: str) -> list[str]:
    """Generate common spelling variations for search."""
    aliases = set()

    if roman_name:
        aliases.add(roman_name)
        aliases.add(roman_name.lower())

        # Common variations
        variations = [
            (r'ee', 'i'),
            (r'oo', 'u'),
            (r'aa', 'a'),
            (r'ph', 'f'),
            (r'bh', 'v'),
            (r'chh', 'ch'),
            (r'shh', 'sh'),
        ]

        variant = roman_name.lower()
        for pattern, replacement in variations:
            variant = re.sub(pattern, replacement, variant)
        if variant != roman_name.lower():
            aliases.add(variant.title())

        # Extract surname (last word)
        parts = roman_name.split()
        if len(parts) > 1:
            aliases.add(parts[-1])  # Surname only
            if len(parts) > 2:
                aliases.add(f"{parts[0]} {parts[-1]}")  # First + Last

    return list(aliases)


def is_major_party(party: str) -> bool:
    """Check if candidate belongs to a major party."""
    if not party:
        return False
    party_lower = party.lower()
    for major in MAJOR_PARTIES:
        if major.lower() in party_lower or party_lower in major.lower():
            return True
    return False


async def search_candidate_info(name_roman: str, party: str, constituency: str) -> Optional[dict]:
    """Search for candidate biographical information online."""
    # This is a placeholder - in production, you would use:
    # 1. Wikipedia API
    # 2. News article search
    # 3. Government databases

    # For now, return None - we'll need to implement actual search
    # or use an AI service to generate summaries
    return None


def process_election_file(filepath: Path, output_path: Path) -> dict:
    """Process an election JSON file and add English names."""
    logger.info(f"Processing {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {
        'total_candidates': 0,
        'transliterated': 0,
        'major_party': 0,
        'errors': 0,
    }

    for constituency in data.get('results', []):
        for candidate in constituency.get('candidates', []):
            stats['total_candidates'] += 1

            try:
                # Get Nepali name (currently in name_en field incorrectly)
                nepali_name = candidate.get('name_ne') or candidate.get('name_en', '')

                # Transliterate to English
                roman_name = transliterate_nepali(nepali_name)

                if roman_name:
                    # Add new fields
                    candidate['name_en_roman'] = roman_name
                    candidate['aliases'] = generate_aliases(nepali_name, roman_name)
                    stats['transliterated'] += 1

                    # Check if major party
                    party = candidate.get('party', '')
                    if is_major_party(party):
                        stats['major_party'] += 1
                        candidate['is_notable'] = True
                    else:
                        candidate['is_notable'] = False

                    # Placeholder for biography (to be filled later)
                    candidate['biography'] = None
                    candidate['biography_source'] = None
                    candidate['previous_positions'] = None

            except Exception as e:
                logger.error(f"Error processing candidate {candidate.get('id')}: {e}")
                stats['errors'] += 1

    # Save enriched data
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved enriched data to {output_path}")
    return stats


def main():
    parser = argparse.ArgumentParser(description='Enrich candidate data with English names and bios')
    parser.add_argument('--year', type=int, default=2082, help='Election year (BS)')
    parser.add_argument('--input-dir', type=str,
                        default='../frontend/public/data',
                        help='Input directory for election JSON files')
    parser.add_argument('--output-dir', type=str,
                        default='../frontend/public/data',
                        help='Output directory for enriched JSON files')
    args = parser.parse_args()

    # Get script directory
    script_dir = Path(__file__).parent.resolve()
    input_dir = (script_dir / args.input_dir).resolve()
    output_dir = (script_dir / args.output_dir).resolve()

    input_file = input_dir / f'election-results-{args.year}.json'
    output_file = output_dir / f'election-results-{args.year}.json'

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    logger.info(f"Starting candidate enrichment for {args.year} election")
    stats = process_election_file(input_file, output_file)

    logger.info("=" * 50)
    logger.info("ENRICHMENT COMPLETE")
    logger.info(f"Total candidates: {stats['total_candidates']}")
    logger.info(f"Transliterated: {stats['transliterated']}")
    logger.info(f"Major party candidates: {stats['major_party']}")
    logger.info(f"Errors: {stats['errors']}")


if __name__ == '__main__':
    main()
