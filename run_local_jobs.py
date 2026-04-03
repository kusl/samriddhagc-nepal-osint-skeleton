#!/usr/bin/env python3
"""Run production jobs locally via SSH tunnel.

Some jobs can't run on the VPS because:
  - Claude CLI (`claude -p`) is only available locally (Claude Max)
  - Nitter instances block cloud provider IPs (AWS Lightsail)

Prerequisites:
  SSH tunnels must be active:
    ssh -i ~/Downloads/LightsailDefaultKey-us-east-2.pem -f -N \
        -L 5433:172.18.0.3:5432 ubuntu@3.148.250.92
    ssh -i ~/Downloads/LightsailDefaultKey-us-east-2.pem -f -N \
        -L 6380:172.18.0.2:6379 ubuntu@3.148.250.92

Usage:
  python run_local_jobs.py nitter          # Scrape all accounts + hashtags
  python run_local_jobs.py clustering      # Run story clustering (Haiku merge)
  python run_local_jobs.py analyst         # Run analyst agent (Sonnet)
  python run_local_jobs.py province        # Run province anomaly agent
  python run_local_jobs.py tweet-dedup     # Run tweet dedup batch
  python run_local_jobs.py all             # Run all local-only jobs
"""

import asyncio
import logging
import os
import sys
import time

# Set production DB/Redis URLs via SSH tunnel BEFORE any app imports
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://nepal_osint:osint_pr0d_0d18418bd57311e54c42638d"
    "@localhost:5433/nepal_osint"
)
os.environ["REDIS_URL"] = "redis://localhost:6380/0"
os.environ["APP_ENV"] = "development"  # Skip production JWT validation
os.environ["RUN_SCHEDULER"] = "false"  # Don't start the scheduler
os.environ["CLAUDE_USE_CLI"] = "true"  # Use claude CLI (Max subscription) for Sonnet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_nitter():
    """Scrape all Nitter accounts and hashtags."""
    from app.core.database import AsyncSessionLocal
    from app.services.nitter_service import NitterService

    logger.info("=== Starting Nitter scrape (accounts + hashtags) ===")
    t0 = time.monotonic()

    async with AsyncSessionLocal() as db:
        service = NitterService(db)

        # Accounts
        logger.info("Scraping account timelines...")
        result = await service.scrape_all_accounts()
        logger.info(
            f"Accounts: {result.get('accounts_scraped', 0)} scraped, "
            f"{result.get('tweets_fetched', 0)} fetched, "
            f"{result.get('new_tweets', 0)} new"
        )
        if result.get("errors"):
            for err in result["errors"]:
                logger.warning(f"  Error: {err}")

        # Hashtags
        logger.info("Scraping hashtag searches...")
        result_ht = await service.scrape_all_hashtags()
        logger.info(
            f"Hashtags: {result_ht.get('hashtags_scraped', 0)} scraped, "
            f"{result_ht.get('tweets_fetched', 0)} fetched, "
            f"{result_ht.get('new_tweets', 0)} new"
        )
        if result_ht.get("errors"):
            for err in result_ht["errors"]:
                logger.warning(f"  Error: {err}")

        # Text searches
        logger.info("Scraping text searches...")
        result_ts = await service.scrape_all_searches()
        logger.info(
            f"Searches: {result_ts.get('searches_scraped', 0)} scraped, "
            f"{result_ts.get('tweets_fetched', 0)} fetched, "
            f"{result_ts.get('new_tweets', 0)} new"
        )
        if result_ts.get("errors"):
            for err in result_ts["errors"]:
                logger.warning(f"  Error: {err}")

    elapsed = time.monotonic() - t0
    logger.info(f"=== Nitter scrape complete ({elapsed:.1f}s) ===")


async def run_clustering():
    """Run story clustering with Haiku merge."""
    from app.tasks.scheduler import run_clustering as _run_clustering

    logger.info("=== Starting clustering ===")
    t0 = time.monotonic()
    await _run_clustering()
    logger.info(f"=== Clustering complete ({time.monotonic() - t0:.1f}s) ===")


async def run_analyst():
    """Run analyst agent (Sonnet)."""
    from app.tasks.scheduler import run_analyst_agent

    logger.info("=== Starting analyst agent ===")
    t0 = time.monotonic()
    await run_analyst_agent()
    logger.info(f"=== Analyst agent complete ({time.monotonic() - t0:.1f}s) ===")


async def run_province():
    """Run province anomaly agent."""
    from app.tasks.scheduler import run_province_anomaly_agent

    logger.info("=== Starting province anomaly agent ===")
    t0 = time.monotonic()
    await run_province_anomaly_agent()
    logger.info(f"=== Province anomaly complete ({time.monotonic() - t0:.1f}s) ===")


async def run_tweet_dedup():
    """Run tweet dedup batch."""
    from app.tasks.scheduler import run_tweet_dedup_batch

    logger.info("=== Starting tweet dedup batch ===")
    t0 = time.monotonic()
    await run_tweet_dedup_batch()
    logger.info(f"=== Tweet dedup complete ({time.monotonic() - t0:.1f}s) ===")


async def run_all():
    """Run all local-only jobs sequentially."""
    await run_nitter()
    await run_tweet_dedup()
    await run_clustering()
    await run_province()
    await run_analyst()


JOBS = {
    "nitter": run_nitter,
    "clustering": run_clustering,
    "analyst": run_analyst,
    "province": run_province,
    "tweet-dedup": run_tweet_dedup,
    "all": run_all,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in JOBS:
        print(f"Usage: python {sys.argv[0]} <{'|'.join(JOBS.keys())}>")
        sys.exit(1)

    job_name = sys.argv[1]
    logger.info(f"Running local job: {job_name}")
    asyncio.run(JOBS[job_name]())
    logger.info("DONE")


if __name__ == "__main__":
    main()
