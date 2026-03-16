#!/usr/bin/env python3
"""
Continuous IRD PAN enrichment runner.

Enriches companies that have PAN numbers (from CAMIS) with IRD data:
  - Taxpayer name, tax office, registration date
  - Phone/mobile hashes (privacy-preserving HMAC-SHA256)
  - Tax clearance status

Phone hashes enable detecting hidden connections between companies
(same phone = same owner/controller) without storing raw PII.

Uses Playwright to handle reCAPTCHA v3 on ird.gov.np.

Usage:
    python scripts/run_ird_enrichment.py                          # defaults
    python scripts/run_ird_enrichment.py --batch-size 20          # smaller batches
    python scripts/run_ird_enrichment.py --min-reg 200000         # start from reg#
    python scripts/run_ird_enrichment.py --headed                 # visible browser (debug)
"""
import argparse
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from app.core.database import AsyncSessionLocal
from app.ingestion.ird_enricher import IRDEnricher
from app.ingestion.ird_client import IRDClient


def setup_logging(log_dir: Path) -> logging.Logger:
    """Set up dual logging: console + file."""
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"ird_enrichment_{timestamp}.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger = logging.getLogger("ird_enrichment")
    logger.setLevel(logging.INFO)
    logger.addHandler(fh)
    logger.addHandler(ch)

    # Also capture enricher and client logs
    for mod in ("app.ingestion.ird_enricher", "app.ingestion.ird_client"):
        mod_logger = logging.getLogger(mod)
        mod_logger.setLevel(logging.INFO)
        mod_logger.addHandler(fh)
        mod_logger.addHandler(ch)

    logger.info(f"Logging to {log_file}")
    return logger


async def run(
    min_reg_number: int,
    batch_size: int,
    headed: bool,
    logger: logging.Logger,
):
    """Run continuous IRD enrichment until all companies with PANs are done."""
    # IRD is slower than CAMIS (browser-based), so we use low concurrency
    # reCAPTCHA v3 also dislikes rapid-fire requests
    client = IRDClient(max_concurrency=1, headless=not headed)
    await client._start()

    grand_start = time.monotonic()
    total_enriched = 0
    total_phones = 0
    total_errors = 0
    batch_num = 0

    logger.info("=" * 70)
    logger.info("IRD ENRICHMENT STARTED")
    logger.info(f"  min_reg_number: {min_reg_number:,}")
    logger.info(f"  batch_size:     {batch_size}")
    logger.info(f"  headed:         {headed}")
    logger.info("=" * 70)

    while True:
        batch_num += 1

        async with AsyncSessionLocal() as db:
            enricher = IRDEnricher(db, client=client, concurrency=1)

            try:
                stats = await enricher.enrich_batch(
                    limit=batch_size,
                    min_reg_number=min_reg_number,
                )
            except Exception as e:
                logger.error(f"Batch #{batch_num} FAILED: {e}")
                total_errors += 1
                logger.info("Waiting 30s before retry...")
                await asyncio.sleep(30)
                continue

        remaining = stats["total_unenriched"]
        enriched = stats["enriched"]
        phones = stats["phone_hashes_found"]
        errors = len(stats["errors"])

        total_enriched += enriched
        total_phones += phones
        total_errors += errors

        elapsed_total = time.monotonic() - grand_start
        rate = total_enriched / elapsed_total if elapsed_total > 0 else 0

        logger.info(
            f"Batch #{batch_num}: {enriched}/{stats['batch_size']} enriched, "
            f"{phones} phones | "
            f"Running total: {total_enriched:,} enriched, {total_phones:,} phones, "
            f"{total_errors} errors | "
            f"Rate: {rate:.2f}/sec | "
            f"Remaining: {remaining:,} | "
            f"Elapsed: {elapsed_total/60:.1f}min"
        )

        if stats["errors"]:
            for err in stats["errors"][:3]:
                logger.warning(f"  Error: {err}")

        # Done?
        if stats["batch_size"] == 0 or remaining == 0:
            break

        # Cooldown between batches (be gentle with IRD)
        await asyncio.sleep(5)

    await client.close()

    elapsed_total = time.monotonic() - grand_start
    hours = elapsed_total / 3600
    logger.info("=" * 70)
    logger.info("IRD ENRICHMENT COMPLETE")
    logger.info(f"  Total enriched:       {total_enriched:,}")
    logger.info(f"  Total phone hashes:   {total_phones:,}")
    logger.info(f"  Total errors:         {total_errors}")
    logger.info(f"  Batches:              {batch_num}")
    logger.info(f"  Total time:           {hours:.2f} hours ({elapsed_total:.0f}s)")
    if total_enriched > 0:
        logger.info(f"  Avg rate:             {total_enriched / elapsed_total:.2f} companies/sec")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Continuous IRD PAN enrichment")
    parser.add_argument("--min-reg", type=int, default=200000, help="Start from this registration number (default: 200000)")
    parser.add_argument("--batch-size", type=int, default=25, help="Companies per batch (default: 25)")
    parser.add_argument("--headed", action="store_true", help="Run browser in visible mode (for debugging)")
    args = parser.parse_args()

    log_dir = project_root / "logs"
    logger = setup_logging(log_dir)

    import warnings
    warnings.filterwarnings("ignore")

    try:
        asyncio.run(run(
            min_reg_number=args.min_reg,
            batch_size=args.batch_size,
            headed=args.headed,
            logger=logger,
        ))
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Progress is saved -- restart to continue.")


if __name__ == "__main__":
    main()
