"""Procurement service for government contract ingestion and querying."""
import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.bolpatra_scraper import BolpatraScraper
from app.repositories.procurement import ProcurementRepository
from app.services.procurement_company_linkage_service import ProcurementCompanyLinkageService
from app.services.procurement_entity_classifier import (
    ENTITY_BUCKET_LABELS,
    classify_procurement_entity,
)

logger = logging.getLogger(__name__)


class ProcurementService:
    """Service for government procurement contract operations."""

    SUMMARY_CACHE_TTL = 15 * 60

    def __init__(self, db: AsyncSession, redis_client=None):
        self.db = db
        self.redis = redis_client
        self.repo = ProcurementRepository(db)

    @staticmethod
    def _format_compact_npr(value: float | None) -> str:
        if not value:
            return "Nrs 0"
        abs_value = abs(value)
        if abs_value >= 1_000_000_000_000:
            return f"Nrs {(value / 1_000_000_000_000):.2f}T".replace(".00", "")
        if abs_value >= 1_000_000_000:
            return f"Nrs {(value / 1_000_000_000):.2f}B".replace(".00", "")
        if abs_value >= 1_000_000:
            return f"Nrs {(value / 1_000_000):.2f}M".replace(".00", "")
        if abs_value >= 1_000:
            return f"Nrs {(value / 1_000):.1f}K".replace(".0", "")
        return f"Nrs {round(value):,}"

    @staticmethod
    def _summary_cache_key(entity_bucket: Optional[str], procurement_type: Optional[str], search: Optional[str]) -> str:
        return "procurement:widget-summary:" + json.dumps(
            {
                "entity_bucket": entity_bucket or "all",
                "procurement_type": procurement_type or "all",
                "search": (search or "").strip().lower(),
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    async def ingest_contracts(self, page_size: int = 5000) -> dict:
        return await self.ingest_contracts_with_options(page_size=page_size)

    async def ingest_contracts_with_options(
        self,
        page_size: int = 5000,
        *,
        scraper_delay: float = 0.5,
        refresh_ocr_linkage: bool = True,
        linkage_target_coverage: float = 0.90,
    ) -> dict:
        """
        Run Bolpatra scraper and upsert all contracts to database.

        Returns ingestion stats dict.
        """
        logger.info("Starting Bolpatra contract ingestion")

        # Run sync scraper in executor
        def _scrape():
            scraper = BolpatraScraper(delay=scraper_delay)
            return scraper.scrape_contracts(page_size=page_size)

        loop = asyncio.get_event_loop()
        contracts = await loop.run_in_executor(None, _scrape)

        stats = {
            "source": "bolpatra.gov.np",
            "fetched": len(contracts),
            "new": 0,
            "updated": 0,
            "errors": [],
        }

        for contract in contracts:
            try:
                external_id = BolpatraScraper.generate_external_id(
                    contract.ifb_number, contract.procuring_entity
                )
                award_date = BolpatraScraper._parse_date(contract.contract_award_date or "")
                fiscal_year = BolpatraScraper._extract_fiscal_year(contract.ifb_number)

                _, created = await self.repo.upsert(
                    external_id=external_id,
                    ifb_number=contract.ifb_number,
                    project_name=contract.project_name,
                    procuring_entity=contract.procuring_entity,
                    procurement_type=contract.procurement_type,
                    contractor_name=contract.contractor_name,
                    contract_award_date=award_date,
                    contract_amount_npr=contract.contract_amount_npr,
                    fiscal_year_bs=fiscal_year,
                    raw_data=contract.raw_data,
                )

                if created:
                    stats["new"] += 1
                else:
                    stats["updated"] += 1

            except Exception as e:
                error_msg = f"Error ingesting contract {contract.ifb_number}: {e}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)

        logger.info(
            f"Bolpatra ingestion complete: {stats['fetched']} fetched, "
            f"{stats['new']} new, {stats['updated']} updated, "
            f"{len(stats['errors'])} errors"
        )

        if refresh_ocr_linkage:
            try:
                stats["ocr_linkage"] = await ProcurementCompanyLinkageService(self.db).refresh_links(
                    target_coverage=linkage_target_coverage
                )
            except Exception as exc:
                logger.warning("Failed to refresh procurement OCR linkage after ingestion: %s", exc)
                stats["ocr_linkage"] = {"error": str(exc)}

        return stats

    async def list_contracts(
        self,
        procuring_entity: Optional[str] = None,
        entity_bucket: Optional[str] = None,
        procurement_type: Optional[str] = None,
        contractor_name: Optional[str] = None,
        district: Optional[str] = None,
        fiscal_year_bs: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """List contracts with filtering and pagination."""
        filter_kwargs = dict(
            procuring_entity=procuring_entity,
            entity_bucket=entity_bucket,
            procurement_type=procurement_type,
            contractor_name=contractor_name,
            district=district,
            fiscal_year_bs=fiscal_year_bs,
            min_amount=min_amount,
            max_amount=max_amount,
            search=search,
        )

        contracts = await self.repo.list_contracts(
            **filter_kwargs,
            page=page,
            per_page=per_page,
        )
        total = await self.repo.count(**filter_kwargs)

        return {
            "contracts": [c.to_dict() for c in contracts],
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_more": (page * per_page) < total,
        }

    async def get_widget_summary(
        self,
        *,
        entity_bucket: Optional[str] = None,
        procurement_type: Optional[str] = None,
        search: Optional[str] = None,
        per_page: int = 20,
    ) -> dict:
        """Return a single cached procurement payload for dashboard widgets."""
        cache_key = self._summary_cache_key(entity_bucket, procurement_type, search)
        if self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception:
                logger.warning("Failed to read procurement widget summary cache", exc_info=True)

        stats = await self.get_stats()
        entity_buckets = await self.get_entity_buckets()
        top_entities = await self.get_top_procuring_entities(
            limit=5,
            entity_bucket=entity_bucket if entity_bucket and entity_bucket != "all" else None,
        )
        contracts_page = await self.list_contracts(
            entity_bucket=entity_bucket,
            procurement_type=procurement_type,
            search=search,
            page=1,
            per_page=per_page,
        )

        bucket_value = None
        if entity_bucket and entity_bucket != "all":
            matched = next((item for item in entity_buckets if item["bucket"] == entity_bucket), None)
            bucket_value = matched["total_value"] if matched else None
        else:
            bucket_value = stats["total_value_npr"]

        lead_entity = top_entities[0] if top_entities else None
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total": contracts_page["total"],
            "cards": [
                {
                    "label": "Contracts",
                    "value": str(contracts_page["total"]),
                    "meta": "Filtered view" if (entity_bucket and entity_bucket != "all") or procurement_type or search else "All tracked awards",
                },
                {
                    "label": "Awarded Value",
                    "value": self._format_compact_npr(bucket_value),
                    "meta": "Current bucket" if entity_bucket and entity_bucket != "all" else "All tracked awards",
                },
                {
                    "label": "Top Entity",
                    "value": lead_entity["procuring_entity"] if lead_entity else "None",
                    "meta": f"{lead_entity['contract_count']} awards" if lead_entity else "No ranked entity",
                },
            ],
            "stats": stats,
            "entity_buckets": entity_buckets,
            "top_entities": top_entities,
            "contracts": contracts_page["contracts"],
        }

        if self.redis:
            try:
                await self.redis.set(cache_key, json.dumps(payload), ex=self.SUMMARY_CACHE_TTL)
            except Exception:
                logger.warning("Failed to write procurement widget summary cache", exc_info=True)

        return payload

    async def get_contract(self, contract_id: str) -> Optional[dict]:
        """Get single contract by ID."""
        try:
            uid = UUID(contract_id)
        except (ValueError, TypeError):
            return None

        contract = await self.repo.get_by_id(uid)
        if not contract:
            return None
        return contract.to_dict()

    async def get_stats(self) -> dict:
        """Get aggregate procurement statistics."""
        stats = await self.repo.get_stats()
        rollups = await self.repo.get_entity_rollups()

        by_entity_bucket: dict[str, dict] = {}
        for row in rollups:
            entity_meta = classify_procurement_entity(row["procuring_entity"])
            bucket = entity_meta["entity_bucket"]
            if bucket not in by_entity_bucket:
                by_entity_bucket[bucket] = {
                    "bucket": bucket,
                    "label": entity_meta["entity_bucket_label"],
                    "count": 0,
                    "total_value": 0.0,
                    "entity_count": 0,
                }
            by_entity_bucket[bucket]["count"] += row["contract_count"]
            by_entity_bucket[bucket]["total_value"] += row["total_value"] or 0.0
            by_entity_bucket[bucket]["entity_count"] += 1

        stats["by_entity_bucket"] = sorted(
            by_entity_bucket.values(),
            key=lambda item: item["total_value"],
            reverse=True,
        )
        return stats

    async def get_top_contractors(self, limit: int = 10) -> list:
        """Get top contractors by total contract value."""
        return await self.repo.get_top_contractors(limit=limit)

    async def get_top_procuring_entities(
        self,
        limit: int = 10,
        entity_bucket: Optional[str] = None,
    ) -> list:
        """Get top procuring entities by total contract value."""
        rows = await self.repo.get_top_procuring_entities(limit=limit, entity_bucket=entity_bucket)
        return [
            {
                **row,
                **classify_procurement_entity(row["procuring_entity"]),
            }
            for row in rows
        ]

    async def get_entity_buckets(self) -> list[dict]:
        """Return procurement entity buckets and summary counts for filter UIs."""
        rollups = await self.repo.get_entity_rollups()
        grouped: dict[str, dict] = {
            bucket: {
                "bucket": bucket,
                "label": label,
                "count": 0,
                "entity_count": 0,
                "total_value": 0.0,
            }
            for bucket, label in ENTITY_BUCKET_LABELS.items()
        }

        for row in rollups:
            entity_meta = classify_procurement_entity(row["procuring_entity"])
            bucket = entity_meta["entity_bucket"]
            grouped[bucket]["count"] += row["contract_count"]
            grouped[bucket]["entity_count"] += 1
            grouped[bucket]["total_value"] += row["total_value"] or 0.0

        return sorted(
            [item for item in grouped.values() if item["entity_count"] > 0],
            key=lambda item: item["total_value"],
            reverse=True,
        )
