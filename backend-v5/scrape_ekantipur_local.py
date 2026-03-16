#!/usr/bin/env python3
"""Local ekantipur election scraper — runs on Mac, POSTs to VPS.

Scrapes ekantipur.com for vote data, matches candidates to ECN IDs
using the static election-results-2082.json (Nepali name matching),
and POSTs vote counts to the VPS ingest endpoint.

Usage:
    python3 scrape_ekantipur_local.py           # one-shot
    python3 scrape_ekantipur_local.py --loop 60  # repeat every 60s
"""
import json
import os
import re
import sys
import time
import logging
from pathlib import Path
from difflib import SequenceMatcher

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

VPS_BASE = "http://3.148.250.92/api/v1"
EKANTIPUR_URL = "https://election.ekantipur.com/?lng=eng"
STATIC_JSON = Path(__file__).parent / "static" / "election-results-2082.json"

EMAIL = os.environ.get("OSINT_EMAIL", "dev@narada.dev")
PASSWORD = os.environ.get("OSINT_PASSWORD", "")


def normalize_ne(name: str) -> str:
    """Normalize Nepali name — strip zero-width chars, extra spaces."""
    # Remove zero-width joiners/non-joiners and normalize spaces
    name = re.sub(r'[\u200b\u200c\u200d\u00ad]', '', name)
    return re.sub(r'\s+', ' ', name).strip()


def fuzzy_match(a: str, b: str) -> float:
    """Return similarity ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def load_candidate_map() -> tuple[dict, dict]:
    """Build lookup indexes from static election JSON.

    Returns:
        by_const_nepali: {(slug, nepali_name_normalized) -> ecn_id}
        by_const_party: {(slug, party_lower) -> [(ecn_id, nepali_name, roman_name)]}
    """
    with open(STATIC_JSON) as f:
        data = json.load(f)

    # Primary: exact Nepali name match per constituency
    by_const_nepali: dict[tuple, int] = {}
    # Secondary: party-based match per constituency
    by_const_party: dict[tuple, list] = {}

    for r in data["results"]:
        slug = r["constituency_id"]  # e.g. "kathmandu-8"
        for c in r["candidates"]:
            ecn_id = int(c["id"])
            nepali_name = normalize_ne(c.get("name_en", ""))  # name_en is actually Nepali in our data
            roman_name = (c.get("name_en_roman", "") or "").lower()
            party = (c.get("party", "") or "").lower()

            # Nepali name index
            if nepali_name:
                by_const_nepali[(slug, nepali_name)] = ecn_id

            # Party index
            by_const_party.setdefault((slug, party), []).append(
                (ecn_id, nepali_name, roman_name)
            )

            # Also index by roman name aliases
            for alias in c.get("aliases", []):
                alias_key = (slug, alias.lower().strip())
                by_const_party.setdefault(alias_key, []).append(
                    (ecn_id, nepali_name, roman_name)
                )

    return by_const_nepali, by_const_party


# Ekantipur slug → our static JSON slug mapping
SLUG_MAP = {
    "rukumeast-1": "rukum-east-1",
    "rukumwest-1": "rukum-west-1",
    "rauthat-1": "rautahat-1",
    "rauthat-2": "rautahat-2",
    "rauthat-3": "rautahat-3",
    "rauthat-4": "rautahat-4",
}


def normalize_slug(slug: str) -> str:
    return SLUG_MAP.get(slug, slug)


# Ekantipur party → our static JSON party name mapping
PARTY_MAP = {
    "rastirya swatantra party": "rastriya swatantra party",
    "rastriya prajatantra party": "rpp",
    "nepal communist party (maoist)": "cpn-maoist",
    "janata samjbadi party-nepal": "jsp-nepal",
    "janata samajbadi party (ekal chunab chinha)": "jsp",
    "rastriya mukti party nepal (ekal chunab chinha)": "rastriya mukti party",
}


def normalize_party(name: str) -> str:
    key = name.lower().strip()
    return PARTY_MAP.get(key, key)


def match_candidate(
    slug: str,
    ek_name: str,
    ek_party: str,
    by_const_nepali: dict,
    by_const_party: dict,
) -> int | None:
    """Match an ekantipur candidate to ECN candidate ID."""

    # Strategy 1: Direct English/Roman name match by constituency + name
    name_key = (slug, ek_name.lower().strip())
    # Check if this exact name appears as a roman alias in our party index
    candidates = by_const_party.get(name_key, [])
    if len(candidates) == 1:
        return candidates[0][0]

    # Strategy 2: Match by constituency + party (unique party per constituency)
    party_norm = normalize_party(ek_party)
    party_key = (slug, party_norm)
    candidates = by_const_party.get(party_key, [])
    if len(candidates) == 1:
        return candidates[0][0]

    # Strategy 3: Fuzzy match on roman name within same party
    if candidates:
        best_score = 0
        best_id = None
        for ecn_id, _, roman in candidates:
            score = fuzzy_match(ek_name.lower(), roman)
            if score > best_score:
                best_score = score
                best_id = ecn_id
        if best_score > 0.45:
            return best_id

    # Strategy 4: Fuzzy party name match across all parties in constituency
    for (s, p), cands in by_const_party.items():
        if s != slug:
            continue
        if fuzzy_match(party_norm, p) > 0.7:
            if len(cands) == 1:
                return cands[0][0]
            best_score = 0
            best_id = None
            for ecn_id, _, roman in cands:
                score = fuzzy_match(ek_name.lower(), roman)
                if score > best_score:
                    best_score = score
                    best_id = ecn_id
            if best_score > 0.4:
                return best_id

    return None


def scrape_ekantipur() -> list[dict]:
    """Scrape ekantipur.com and return candidates with vote data."""
    logger.info("Fetching ekantipur...")

    client = httpx.Client(
        timeout=30.0, verify=False, follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
    )

    r = client.get(EKANTIPUR_URL)
    r.raise_for_status()
    html = r.text
    logger.info("Page: %d bytes", len(html))

    # Extract competiviveDist (competitive constituencies with full candidate data)
    m = re.search(r'competiviveDist\s*=\s*(\{.+?\});\s*(?:\n|var|let|const)', html, re.DOTALL)
    if not m:
        logger.warning("competitiveDist not found")
        return []

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s", e)
        return []

    logger.info("Parsed %d constituencies from competitiveDist", len(data))

    # Load candidate map
    by_const_nepali, by_const_party = load_candidate_map()

    results = []
    matched = 0
    unmatched = 0
    unmatched_with_votes = []

    for raw_slug, candidates in data.items():
        const_slug = normalize_slug(raw_slug)
        for c in candidates:
            vote_count = c.get("vote_count", 0) or 0
            is_win = bool(c.get("is_win", 0))
            is_lead = bool(c.get("is_lead", 0))

            if vote_count <= 0 and not is_win and not is_lead:
                continue

            name = c.get("name", "").strip()
            party = c.get("party_name", "").strip()

            ecn_id = match_candidate(const_slug, name, party, by_const_nepali, by_const_party)

            if ecn_id:
                results.append({
                    "ecn_candidate_id": ecn_id,
                    "vote_count": vote_count,
                    "is_win": is_win,
                    "is_lead": is_lead,
                })
                matched += 1
            else:
                unmatched += 1
                if vote_count > 0:
                    unmatched_with_votes.append(f"{name} ({party}) in {const_slug}: {vote_count}")

    if unmatched_with_votes:
        for u in unmatched_with_votes:
            logger.warning("UNMATCHED: %s", u)

    logger.info("Matched %d, unmatched %d (%d with votes)", matched, unmatched, len(unmatched_with_votes))
    return results


def get_vps_token() -> str | None:
    """Login to VPS and get JWT token."""
    if not PASSWORD:
        logger.error("Set OSINT_PASSWORD env var")
        return None
    try:
        r = httpx.post(f"{VPS_BASE}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10.0)
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        logger.error("VPS login failed: %s", e)
        return None


def post_to_vps(candidates: list[dict], token: str):
    """POST vote data to VPS ingest endpoint."""
    if not candidates:
        logger.info("No candidates with votes to post")
        return

    payload = {"candidates": candidates, "source": "ekantipur-local"}

    try:
        r = httpx.post(
            f"{VPS_BASE}/election-results/ingest-votes",
            json=payload, timeout=15.0, verify=False,
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        result = r.json()
        logger.info("VPS ingest: %s", result)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.warning("Token expired, will re-login next cycle")
            return "reauth"
        logger.error("VPS POST failed: %s", e)
    except Exception as e:
        logger.error("VPS POST failed: %s", e)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Local ekantipur election scraper")
    parser.add_argument("--loop", type=int, default=0, help="Repeat every N seconds (0=one-shot)")
    args = parser.parse_args()

    token = get_vps_token()
    if not token:
        sys.exit(1)

    while True:
        try:
            candidates = scrape_ekantipur()
            result = post_to_vps(candidates, token)
            # Re-auth if token expired
            if result == "reauth":
                token = get_vps_token()
                if token:
                    post_to_vps(candidates, token)
        except Exception as e:
            logger.error("Scraper error: %s", e)

        if args.loop <= 0:
            break
        logger.info("Sleeping %ds...", args.loop)
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
