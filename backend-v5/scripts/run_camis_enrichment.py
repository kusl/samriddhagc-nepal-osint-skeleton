#!/usr/bin/env python3
"""
Continuous CAMIS enrichment runner.

Enriches all un-enriched companies from a given registration number upward,
in batches of BATCH_SIZE with WORKERS parallel requests, until none remain.

Logs to both console and logs/camis_enrichment.log.

Usage:
    python scripts/run_camis_enrichment.py                      # defaults: reg >= 200000, 8 workers
    python scripts/run_camis_enrichment.py --min-reg 150000     # start lower
    python scripts/run_camis_enrichment.py --workers 12         # more concurrency
    python scripts/run_camis_enrichment.py --batch-size 500     # bigger batches
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from app.core.database import AsyncSessionLocal
from app.ingestion.camis_enricher import CAMISEnricher
from app.ingestion.camis_client import CAMISClient


def setup_logging(log_dir: Path) -> logging.Logger:
    """Set up dual logging: console + file."""
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"camis_enrichment_{timestamp}.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler (detailed)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    # Console handler (same detail)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger = logging.getLogger("camis_enrichment")
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(ch)

    # Also capture the ingestion module logs
    for mod in ("app.ingestion.camis_enricher", "app.ingestion.camis_client"):
        mod_logger = logging.getLogger(mod)
        mod_logger.setLevel(logging.INFO)
        mod_logger.addHandler(fh)
        mod_logger.addHandler(ch)

    # Suppress noisy httpx request logs in console (keep in file)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.WARNING)
    # But log to file at INFO
    httpx_fh = logging.FileHandler(log_file, encoding="utf-8")
    httpx_fh.setLevel(logging.DEBUG)
    httpx_fh.setFormatter(fmt)
    httpx_logger.addHandler(httpx_fh)

    logger.info(f"Logging to {log_file}")
    return logger


async def run(
    min_reg_number: int,
    batch_size: int,
    workers: int,
    logger: logging.Logger,
):
    """Run continuous enrichment until all companies are done."""
    # Shared CAMIS client across all batches (reuses HTTP connection pool + token)
    client = CAMISClient(max_concurrency=workers)

    grand_start = time.monotonic()
    total_enriched = 0
    total_pans = 0
    total_errors = 0
    batch_num = 0

    logger.info("=" * 70)
    logger.info("CAMIS ENRICHMENT STARTED")
    logger.info(f"  min_reg_number: {min_reg_number:,}")
    logger.info(f"  batch_size:     {batch_size:,}")
    logger.info(f"  workers:        {workers}")
    logger.info("=" * 70)

    while True:
        batch_num += 1

        async with AsyncSessionLocal() as db:
            enricher = CAMISEnricher(db, client=client, workers=workers)

            try:
                stats = await enricher.enrich_batch(
                    limit=batch_size,
                    min_reg_number=min_reg_number,
                )
            except Exception as e:
                logger.error(f"Batch #{batch_num} FAILED: {e}")
                total_errors += 1
                # Wait before retry
                logger.info("Waiting 30s before retry...")
                await asyncio.sleep(30)
                continue

        remaining = stats["total_unenriched"]
        enriched = stats["enriched"]
        pans = stats["pans_found"]
        errors = len(stats["errors"])

        total_enriched += enriched
        total_pans += pans
        total_errors += errors

        elapsed_total = time.monotonic() - grand_start
        rate = total_enriched / elapsed_total if elapsed_total > 0 else 0

        logger.info(
            f"Batch #{batch_num}: {enriched}/{stats['batch_size']} enriched, "
            f"{pans} PANs | "
            f"Running total: {total_enriched:,} enriched, {total_pans:,} PANs, "
            f"{total_errors} errors | "
            f"Rate: {rate:.1f}/sec | "
            f"Remaining: {remaining:,} | "
            f"Elapsed: {elapsed_total/60:.1f}min"
        )

        if stats["errors"]:
            for err in stats["errors"][:5]:
                logger.warning(f"  Error: {err}")

        # Done?
        if stats["batch_size"] == 0 or remaining == 0:
            break

        # Brief cooldown between batches to avoid overwhelming the CAMIS server
        await asyncio.sleep(3)

    # Close HTTP client
    await client.close()

    elapsed_total = time.monotonic() - grand_start
    hours = elapsed_total / 3600
    logger.info("=" * 70)
    logger.info("CAMIS ENRICHMENT COMPLETE")
    logger.info(f"  Total enriched:  {total_enriched:,}")
    logger.info(f"  Total PANs:      {total_pans:,}")
    logger.info(f"  Total errors:    {total_errors}")
    logger.info(f"  Batches:         {batch_num}")
    logger.info(f"  Total time:      {hours:.2f} hours ({elapsed_total:.0f}s)")
    logger.info(f"  Avg rate:        {total_enriched / elapsed_total:.1f} companies/sec")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Continuous CAMIS company enrichment")
    parser.add_argument("--min-reg", type=int, default=200000, help="Start from this registration number (default: 200000)")
    parser.add_argument("--batch-size", type=int, default=500, help="Companies per batch (default: 500)")
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers (default: 8)")
    args = parser.parse_args()

    log_dir = project_root / "logs"
    logger = setup_logging(log_dir)

    import warnings
    warnings.filterwarnings("ignore")

    try:
        asyncio.run(run(
            min_reg_number=args.min_reg,
            batch_size=args.batch_size,
            workers=args.workers,
            logger=logger,
        ))
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Progress is saved -- restart to continue.")


if __name__ == "__main__":
    main()
