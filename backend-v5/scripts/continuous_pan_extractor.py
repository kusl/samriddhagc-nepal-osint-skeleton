#!/usr/bin/env python3
"""
Continuous PAN extractor - runs in background discovering and validating PANs.

Strategy:
1. Mine PANs from raw data (if available)
2. Validate discovered PANs with IRD
3. Enrich validated companies
4. Sleep and repeat

This runs continuously in the background, processing companies in batches.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime
import logging

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, or_, update
from app.core.database import AsyncSessionLocal
from app.models.company import CompanyRegistration, IRDEnrichment
from app.ingestion.ird_client import IRDClient
from app.ingestion.privacy_hasher import hash_phone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def validate_and_enrich_batch(batch_size: int = 10):
    """Validate and enrich a batch of companies with unvalidated PANs."""

    # Find companies with PANs that need validation/enrichment
    async with AsyncSessionLocal() as db:
        stmt = (
            select(CompanyRegistration)
            .where(
                and_(
                    CompanyRegistration.pan.isnot(None),
                    CompanyRegistration.pan != "",
                    or_(
                        CompanyRegistration.ird_enriched.is_(False),
                        CompanyRegistration.ird_enriched.is_(None),
                    ),
                )
            )
            .order_by(CompanyRegistration.updated_at.desc())
            .limit(batch_size)
        )

        result = await db.execute(stmt)
        companies = list(result.scalars().all())

    if not companies:
        logger.info("No companies need validation")
        return 0

    logger.info(f"Processing batch of {len(companies)} companies")

    validated = 0
    enriched = 0
    invalid = 0

    async with IRDClient(max_concurrency=1, headless=True) as ird_client:
        for company in companies:
            try:
                logger.info(f"Company #{company.registration_number} - PAN: {company.pan}")

                # Validate with IRD
                ird_data = await ird_client.search_pan(company.pan)

                if not ird_data or not ird_data.get("panDetails"):
                    logger.warning(f"Invalid PAN {company.pan} for company #{company.registration_number}")
                    invalid += 1

                    # Clear invalid PAN
                    async with AsyncSessionLocal() as db_update:
                        stmt = (
                            update(CompanyRegistration)
                            .where(CompanyRegistration.registration_number == company.registration_number)
                            .values(pan=None, updated_at=datetime.utcnow())
                        )
                        await db_update.execute(stmt)
                        await db_update.commit()
                    continue

                validated += 1
                detail = ird_data["panDetails"][0]

                logger.info(f"  ✅ Valid - {detail.get('trade_Name_Eng')}")

                # Enrich
                from sqlalchemy.dialects.postgresql import insert as pg_insert

                async with AsyncSessionLocal() as db_update:
                    enrichment_data = {
                        "pan": company.pan,
                        "taxpayer_name_en": detail.get("trade_Name_Eng"),
                        "taxpayer_name_np": detail.get("trade_Name_Nep"),
                        "account_status": detail.get("account_Status"),
                        "tax_office": detail.get("office_Name"),
                        "ward_no": detail.get("ward_No"),
                        "vdc_municipality": detail.get("vdc_Town"),
                        "phone_hash": hash_phone(detail.get("telephone")),
                        "mobile_hash": hash_phone(detail.get("mobile")),
                        "fetched_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }

                    stmt = pg_insert(IRDEnrichment).values(**enrichment_data)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["pan"],
                        set_={k: v for k, v in enrichment_data.items() if k != "pan"},
                    )
                    await db_update.execute(stmt)

                    stmt = (
                        update(CompanyRegistration)
                        .where(CompanyRegistration.registration_number == company.registration_number)
                        .values(
                            ird_enriched=True,
                            ird_enriched_at=datetime.utcnow(),
                        )
                    )
                    await db_update.execute(stmt)
                    await db_update.commit()

                enriched += 1
                logger.info(f"  ✅ Enriched")

            except Exception as e:
                logger.error(f"Error processing company #{company.registration_number}: {e}")

            # Be polite to IRD
            await asyncio.sleep(2)

    logger.info(f"Batch complete: {validated} validated, {enriched} enriched, {invalid} invalid")
    return validated


async def main():
    """Main loop - continuously process companies."""

    logger.info("="*80)
    logger.info("CONTINUOUS PAN EXTRACTOR STARTED")
    logger.info("="*80)
    logger.info("This process will run continuously in the background")
    logger.info("Processing companies with PANs that need validation/enrichment")
    logger.info("Press Ctrl+C to stop")
    logger.info("="*80)

    cycle = 0
    total_processed = 0

    try:
        while True:
            cycle += 1
            logger.info(f"\n--- Cycle {cycle} ---")

            # Process a batch
            count = await validate_and_enrich_batch(batch_size=10)
            total_processed += count

            if count == 0:
                # No more companies to process - wait longer
                logger.info("No companies to process - waiting 5 minutes")
                await asyncio.sleep(300)  # 5 minutes
            else:
                # More companies to process - short break
                logger.info(f"Total processed so far: {total_processed}")
                logger.info("Waiting 30 seconds before next batch...")
                await asyncio.sleep(30)

    except KeyboardInterrupt:
        logger.info("\n" + "="*80)
        logger.info("STOPPING CONTINUOUS PAN EXTRACTOR")
        logger.info(f"Total companies processed: {total_processed}")
        logger.info("="*80)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
