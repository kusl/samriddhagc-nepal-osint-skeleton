#!/usr/bin/env python3
"""
Biography Enrichment Script for Election Candidates

This script searches for biographical information for notable candidates:
1. Checks Wikipedia for the candidate
2. Searches news sources for background
3. Identifies previous election wins and positions
4. Generates a short biography with source attribution

Usage:
    python scripts/enrich_biographies.py --year 2082 --limit 100
"""
import argparse
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional
import urllib.parse
import httpx

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Wikipedia API endpoint
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_NE_API = "https://ne.wikipedia.org/w/api.php"

# Rate limiting
REQUEST_DELAY = 1.0  # seconds between API calls


async def search_wikipedia(name: str, client: httpx.AsyncClient) -> Optional[dict]:
    """Search English Wikipedia for a person."""
    try:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f"{name} Nepal politician",
            "srwhat": "text",
            "srlimit": 5,
            "format": "json",
        }
        headers = {
            "User-Agent": "NepalOSINT/1.0 (https://narada.dev; contact@narada.dev) Python/httpx"
        }
        response = await client.get(WIKIPEDIA_API, params=params, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        results = data.get("query", {}).get("search", [])
        if results:
            name_parts = name.lower().split()
            surname = name_parts[-1] if name_parts else ""
            first_name = name_parts[0] if name_parts else ""

            # Get the first relevant result
            for result in results:
                title = result.get("title", "").lower()
                snippet = result.get("snippet", "").lower()

                # Strict matching: surname MUST be in title AND first name MUST be in title
                if surname not in title:
                    continue
                if first_name not in title:
                    continue

                # Article must be about Nepal
                nepal_mentioned = "nepal" in snippet or "nepalese" in snippet
                if nepal_mentioned:
                    return {
                        "title": result.get("title", ""),
                        "snippet": result.get("snippet", ""),
                        "pageid": result.get("pageid"),
                    }
        return None
    except Exception as e:
        logger.error(f"Wikipedia search error for {name}: {e}")
        return None


async def get_wikipedia_summary(title: str, client: httpx.AsyncClient) -> Optional[str]:
    """Get Wikipedia article summary."""
    try:
        params = {
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "format": "json",
        }
        headers = {
            "User-Agent": "NepalOSINT/1.0 (https://narada.dev; contact@narada.dev) Python/httpx"
        }
        response = await client.get(WIKIPEDIA_API, params=params, headers=headers, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id != "-1":
                extract = page.get("extract", "")
                if extract:
                    # Verify this is about a Nepalese person
                    extract_lower = extract.lower()
                    if "nepal" not in extract_lower and "nepalese" not in extract_lower:
                        logger.debug(f"Skipping {title} - not about Nepal")
                        return None

                    # Truncate to reasonable length
                    sentences = extract.split(". ")
                    summary = ". ".join(sentences[:3])
                    if len(summary) > 500:
                        summary = summary[:500] + "..."
                    return summary
        return None
    except Exception as e:
        logger.error(f"Wikipedia summary error for {title}: {e}")
        return None


def find_previous_wins(name_roman: str, current_candidate: dict, all_elections: dict) -> list[dict]:
    """Find previous election wins for a candidate.

    Uses strict matching with age validation to avoid false positives
    between different people with the same name.
    """
    previous_wins = []
    current_age = current_candidate.get("age")

    for year, data in all_elections.items():
        for constituency in data.get("results", []):
            for candidate in constituency.get("candidates", []):
                if candidate.get("is_winner"):
                    # Check if names match (strict: first + last name)
                    candidate_name = candidate.get("name_en_roman", "") or candidate.get("name_en", "")
                    if not name_matches(name_roman, candidate_name):
                        continue

                    # Age validation: if both have ages, project to same year and compare
                    prev_age = candidate.get("age")
                    if current_age and prev_age:
                        # Project previous candidate's age to 2082 for comparison
                        # Ages in data are at time of that election
                        year_diff = 2082 - year  # e.g., 2082 - 2074 = 8 years
                        projected_prev_age = prev_age + year_diff  # Age they would be in 2082

                        # If same person, ages should be very close (within 3 years for data errors)
                        age_diff = abs(current_age - projected_prev_age)
                        if age_diff > 3:
                            continue  # Age mismatch - likely different person

                    previous_wins.append({
                        "year": year,
                        "constituency": constituency.get("name_en"),
                        "district": constituency.get("district"),
                        "party": candidate.get("party"),
                        "votes": candidate.get("votes"),
                        "vote_pct": candidate.get("vote_pct"),
                    })
    return previous_wins


def name_matches(name1: str, name2: str) -> bool:
    """Check if two names likely refer to the same person.

    STRICT matching to avoid false positives:
    - Requires FIRST name AND LAST name to match exactly
    - Common middle names like Bahadur, Prasad, Kumar are excluded from matching
    """
    if not name1 or not name2:
        return False

    # Normalize names
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()

    # Exact match
    if n1 == n2:
        return True

    parts1 = n1.split()
    parts2 = n2.split()

    if len(parts1) >= 2 and len(parts2) >= 2:
        # STRICT: Both FIRST name AND LAST name must match exactly
        first1, last1 = parts1[0], parts1[-1]
        first2, last2 = parts2[0], parts2[-1]

        if first1 == first2 and last1 == last2:
            return True

    return False


def generate_biography(
    name_roman: str,
    party: str,
    constituency: str,
    district: str,
    previous_wins: list[dict],
    wiki_summary: Optional[str],
    age: Optional[int],
    education: Optional[str],
) -> tuple[str, Optional[str]]:
    """Generate a biography from available information."""
    bio_parts = []
    source = None

    # Start with Wikipedia info if available
    if wiki_summary:
        bio_parts.append(wiki_summary)
        source = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(name_roman.replace(" ", "_"))
    else:
        # Generate basic bio
        bio_parts.append(f"{name_roman} is a Nepali politician")
        if party:
            bio_parts.append(f"representing {party}")
        if constituency and district:
            bio_parts.append(f"from {constituency}, {district}")
        bio_parts[0] = " ".join(bio_parts) + "."
        bio_parts = [bio_parts[0]]

    # Add previous election wins
    if previous_wins:
        if len(previous_wins) == 1:
            win = previous_wins[0]
            bio_parts.append(
                f"Previously elected to parliament in {win['year']} BS from {win['constituency']}."
            )
        elif len(previous_wins) > 1:
            years = sorted([w['year'] for w in previous_wins])
            bio_parts.append(
                f"Elected to parliament {len(previous_wins)} times ({', '.join(map(str, years))} BS)."
            )

    # Add education if notable
    if education and education not in ["Literate (साक्षर)", "Below SLC"]:
        if "PhD" in education or "Master" in education or "Bachelor" in education:
            bio_parts.append(f"Education: {education}.")

    # Combine into final bio
    biography = " ".join(bio_parts)

    # If no real info found, add disclaimer
    if not wiki_summary and not previous_wins:
        biography = f"{name_roman} is a candidate for {party} in {constituency}. Detailed biographical information not available."
        source = None

    return biography, source


async def enrich_candidate_biographies(
    filepath: Path,
    output_path: Path,
    all_elections: dict,
    limit: Optional[int] = None,
) -> dict:
    """Enrich candidate biographies in an election file."""
    logger.info(f"Processing {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {
        'total_notable': 0,
        'with_wiki': 0,
        'with_previous_wins': 0,
        'processed': 0,
        'errors': 0,
    }

    async with httpx.AsyncClient() as client:
        processed = 0

        for constituency in data.get('results', []):
            for candidate in constituency.get('candidates', []):
                # Only process notable candidates
                if not candidate.get('is_notable'):
                    continue

                stats['total_notable'] += 1

                # Skip if already has biography
                if candidate.get('biography'):
                    continue

                # Apply limit
                if limit and processed >= limit:
                    continue

                name_roman = candidate.get('name_en_roman', '')
                if not name_roman:
                    continue

                processed += 1
                stats['processed'] += 1

                try:
                    # Rate limit
                    await asyncio.sleep(REQUEST_DELAY)

                    # Search Wikipedia
                    wiki_result = await search_wikipedia(name_roman, client)
                    wiki_summary = None

                    if wiki_result:
                        stats['with_wiki'] += 1
                        wiki_summary = await get_wikipedia_summary(wiki_result['title'], client)

                    # Find previous election wins
                    previous_wins = find_previous_wins(name_roman, candidate, all_elections)
                    if previous_wins:
                        stats['with_previous_wins'] += 1
                        candidate['previous_positions'] = previous_wins

                    # Generate biography
                    biography, source = generate_biography(
                        name_roman=name_roman,
                        party=candidate.get('party', ''),
                        constituency=constituency.get('name_en', ''),
                        district=constituency.get('district', ''),
                        previous_wins=previous_wins,
                        wiki_summary=wiki_summary,
                        age=candidate.get('age'),
                        education=candidate.get('education'),
                    )

                    candidate['biography'] = biography
                    candidate['biography_source'] = source

                    logger.info(f"Enriched: {name_roman} ({candidate.get('party')})")

                except Exception as e:
                    logger.error(f"Error processing {name_roman}: {e}")
                    stats['errors'] += 1

    # Save enriched data
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved enriched data to {output_path}")
    return stats


def load_all_elections(data_dir: Path) -> dict:
    """Load election files for cross-referencing.

    Note: Only 2079 is used for previous wins matching.
    2074 data has quality issues and is excluded.
    """
    elections = {}
    # Only load 2079 for cross-referencing (2074 has data quality issues)
    for year in [2079]:
        filepath = data_dir / f'election-results-{year}.json'
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                elections[year] = json.load(f)
    return elections


async def main():
    parser = argparse.ArgumentParser(description='Enrich candidate biographies')
    parser.add_argument('--year', type=int, default=2082, help='Election year (BS)')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of candidates to process')
    parser.add_argument('--data-dir', type=str,
                        default='../../frontend/public/data',
                        help='Directory for election JSON files')
    args = parser.parse_args()

    # Get script directory
    script_dir = Path(__file__).parent.resolve()
    data_dir = (script_dir / args.data_dir).resolve()

    input_file = data_dir / f'election-results-{args.year}.json'
    output_file = data_dir / f'election-results-{args.year}.json'

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    # Load all elections for cross-referencing
    all_elections = load_all_elections(data_dir)

    logger.info(f"Starting biography enrichment for {args.year} election")
    if args.limit:
        logger.info(f"Processing limit: {args.limit} candidates")

    stats = await enrich_candidate_biographies(
        input_file, output_file, all_elections, args.limit
    )

    logger.info("=" * 50)
    logger.info("BIOGRAPHY ENRICHMENT COMPLETE")
    logger.info(f"Total notable candidates: {stats['total_notable']}")
    logger.info(f"Processed: {stats['processed']}")
    logger.info(f"With Wikipedia info: {stats['with_wiki']}")
    logger.info(f"With previous wins: {stats['with_previous_wins']}")
    logger.info(f"Errors: {stats['errors']}")


if __name__ == '__main__':
    asyncio.run(main())
