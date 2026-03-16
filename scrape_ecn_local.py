#!/usr/bin/env python3
"""Local ECN scraper — runs on Mac, POSTs vote data to VPS.

Usage:
    OSINT_PASSWORD=your-osint-password python3 scrape_ecn_local.py --loop 180
    OSINT_PASSWORD=your-osint-password python3 scrape_ecn_local.py --once
"""
import argparse
import json
import logging
import os
import sys
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

VPS_URL = "http://3.148.250.92"
ECN_BASE = "https://result.election.gov.np"
ECN_HANDLER = "/Handlers/SecureJson.ashx"
ELECTION_YEAR = "2082"

OSINT_EMAIL = os.environ.get("OSINT_EMAIL", "dev@narada.dev")
OSINT_PASSWORD = os.environ.get("OSINT_PASSWORD", "")

vps_token: str | None = None


def login() -> str:
    global vps_token
    r = requests.post(
        f"{VPS_URL}/api/v1/auth/login",
        json={"email": OSINT_EMAIL, "password": OSINT_PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    vps_token = r.json()["access_token"]
    log.info("VPS login OK")
    return vps_token


def post_votes(candidates: list[dict]) -> dict:
    global vps_token
    if not vps_token:
        login()

    for attempt in range(2):
        r = requests.post(
            f"{VPS_URL}/api/v1/election-results/ingest-votes",
            json={"candidates": candidates, "source": "ecn-local"},
            headers={"Authorization": f"Bearer {vps_token}"},
            timeout=60,
        )
        if r.status_code == 401 and attempt == 0:
            log.info("Token expired, re-login...")
            login()
            continue
        r.raise_for_status()
        return r.json()
    return {"error": "failed"}


def scrape_all() -> int:
    """Scrape all ECN constituencies and POST votes to VPS."""
    # Use requests.Session to handle cookies automatically
    session = requests.Session()
    session.verify = False
    session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})

    # 1. Init session — get CSRF token
    log.info("Connecting to ECN...")
    r = session.get(f"{ECN_BASE}/", timeout=30)
    r.raise_for_status()
    csrf = session.cookies.get("CsrfToken")
    if not csrf:
        log.error("No CsrfToken from ECN")
        return 0
    log.info("ECN session OK, CSRF: %s...", csrf[:8])

    session.headers.update({
        "X-CSRF-Token": csrf,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{ECN_BASE}/",
    })

    def fetch_json(file_path: str) -> list | dict | None:
        url = f"{ECN_BASE}{ECN_HANDLER}?file={file_path}"
        for attempt in range(3):
            try:
                r = session.get(url, timeout=30)
                if r.status_code == 429:
                    wait = 10 * (2 ** attempt)
                    log.warning("ECN 429 on %s, waiting %ds (%d/3)", file_path, wait, attempt + 1)
                    time.sleep(wait)
                    continue
                if r.status_code == 403:
                    log.warning("ECN 403 on %s — re-initing session", file_path)
                    # Re-init session
                    r2 = session.get(f"{ECN_BASE}/", timeout=30)
                    new_csrf = session.cookies.get("CsrfToken")
                    if new_csrf:
                        session.headers["X-CSRF-Token"] = new_csrf
                    continue
                if r.status_code == 404:
                    return None
                if r.status_code >= 500:
                    log.warning("ECN %d on %s", r.status_code, file_path)
                    return None
                r.raise_for_status()
                text = r.text.strip().lstrip("\ufeff")
                if not text or text == "[]":
                    return []
                return json.loads(text)
            except requests.exceptions.Timeout:
                log.warning("ECN timeout on %s (attempt %d/3)", file_path, attempt + 1)
                time.sleep(5)
            except Exception as e:
                log.warning("ECN error on %s: %s", file_path, e)
                if attempt < 2:
                    time.sleep(5)
        return None

    # 2. Get constituencies lookup
    log.info("Fetching constituencies lookup...")
    consts_data = fetch_json(f"JSONFiles/Election{ELECTION_YEAR}/HOR/Lookup/constituencies.json")
    if not consts_data:
        log.error("No constituencies lookup from ECN")
        return 0
    log.info("Got %d constituency entries", len(consts_data))

    # 3. Scrape each constituency
    all_candidates = []
    total_with_votes = 0
    seen_districts = set()
    const_count = 0

    for entry in consts_data:
        dist_id = entry["distId"]
        if dist_id in seen_districts:
            continue
        seen_districts.add(dist_id)
        num_consts = entry["consts"]

        for const_no in range(1, num_consts + 1):
            const_count += 1
            file_path = f"JSONFiles/Election{ELECTION_YEAR}/HOR/FPTP/HOR-{dist_id}-{const_no}.json"
            candidates = fetch_json(file_path)

            if not candidates:
                time.sleep(0.5)
                continue

            const_votes = 0
            for c in candidates:
                votes = c.get("TotalVoteReceived", 0)
                cand_id = c.get("CandidateID") or c.get("CandidateId")
                if votes > 0 and cand_id:
                    all_candidates.append({
                        "ecn_candidate_id": cand_id,
                        "vote_count": votes,
                        "is_win": c.get("Remarks", "") in ("Winner", "Elected"),
                        "is_lead": False,
                    })
                    total_with_votes += 1
                    const_votes += votes

            if const_votes > 0:
                log.info("[%d/%d] HOR-%d-%d: %d votes (%d candidates)",
                         const_count, 165, dist_id, const_no, const_votes, len(candidates))
            elif const_count % 20 == 0:
                log.info("[%d/%d] Scanning... (no votes yet)", const_count, 165)

            # 0.5s delay between requests (local Mac IP, not rate-limited)
            time.sleep(0.5)

    log.info("Done scraping: %d constituencies, %d candidates with votes", const_count, total_with_votes)

    if not all_candidates:
        log.info("No vote data found")
        return 0

    # 4. POST to VPS in batches
    total_updated = 0
    batch_size = 50
    for i in range(0, len(all_candidates), batch_size):
        batch = all_candidates[i:i + batch_size]
        result = post_votes(batch)
        updated = result.get("updated", 0)
        total_updated += updated
        log.info("Posted batch %d-%d: %d updated", i, i + len(batch), updated)

    log.info("TOTAL: %d updated / %d with votes", total_updated, total_with_votes)
    return total_updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", type=int, help="Loop interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once")
    args = parser.parse_args()

    if not OSINT_PASSWORD:
        print("Set OSINT_PASSWORD env var")
        sys.exit(1)

    login()

    if args.once or not args.loop:
        scrape_all()
    else:
        while True:
            try:
                scrape_all()
            except Exception as e:
                log.error("Scrape failed: %s", e)
            log.info("Sleeping %ds...", args.loop)
            time.sleep(args.loop)


if __name__ == "__main__":
    main()
