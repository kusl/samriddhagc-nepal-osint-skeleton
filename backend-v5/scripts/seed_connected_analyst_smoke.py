"""Seed connected analyst smoke scenario.

Creates:
- one case + hypothesis
- one trade report/fact/anomaly
- one PWTT run + three-panel artifacts + finding
- graph/provenance links between PWTT finding and trade anomaly
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import types
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.types import UserDefinedType

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

# Allow this seed script to run in minimal local envs where pgvector is absent.
try:
    import pgvector.sqlalchemy  # type: ignore  # noqa: F401
except Exception:
    pgvector_module = types.ModuleType("pgvector")
    pgvector_sqlalchemy_module = types.ModuleType("pgvector.sqlalchemy")

    class Vector(UserDefinedType):
        cache_ok = True

        def __init__(self, *args, **kwargs):
            super().__init__()

        def get_col_spec(self, **kw):
            return "VECTOR"

    pgvector_sqlalchemy_module.Vector = Vector
    pgvector_module.sqlalchemy = pgvector_sqlalchemy_module
    sys.modules["pgvector"] = pgvector_module
    sys.modules["pgvector.sqlalchemy"] = pgvector_sqlalchemy_module

from app.core.database import AsyncSessionLocal
from app.models.case import Case, CasePriority, CaseStatus, CaseVisibility
from app.models.connected_analyst import (
    AnalystVerificationStatus,
    CaseHypothesis,
    DamageRun,
    DamageRunStatus,
    HypothesisEvidenceLink,
    HypothesisEvidenceRelation,
    KBEvidenceRef,
    ProvenanceOwnerType,
    TradeAnomaly,
    TradeDirection,
    TradeFact,
    TradeReport,
)
from app.models.user import User
from app.services.pwtt import PWTTPersistenceService


CASE_TITLE = "Connected Analyst Smoke Case"
HYPOTHESIS_STATEMENT = "Customs disruption in Birgunj is linked to trade volatility and route-level damage findings."


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "dev@narada.dev"))
        if user is None:
            user = await db.scalar(select(User).order_by(User.created_at.asc()))
        if user is None:
            raise RuntimeError("No users found. Seed users first (scripts/seed_users.py).")

        case = await db.scalar(select(Case).where(Case.title == CASE_TITLE))
        if case is None:
            case = Case(
                id=uuid4(),
                title=CASE_TITLE,
                description="Smoke demo case for connected analyst workspace",
                status=CaseStatus.ACTIVE,
                priority=CasePriority.HIGH,
                visibility=CaseVisibility.PUBLIC,
                category="economic",
                tags=["smoke", "trade", "pwtt"],
                created_by_id=user.id,
                assigned_to_id=user.id,
            )
            db.add(case)
            await db.flush()

        report = await db.scalar(
            select(TradeReport)
            .where(TradeReport.fiscal_year_bs == "2082-83")
            .where(TradeReport.month_ordinal == 4)
            .where(TradeReport.file_path == "seed://smoke")
        )
        if report is None:
            report = TradeReport(
                id=uuid4(),
                fiscal_year_bs="2082-83",
                upto_month="Kartik",
                month_ordinal=4,
                report_title="Smoke Seed Trade Report",
                file_path="seed://smoke",
                coverage_text="Seeded smoke scenario report",
                source_hash="seed-smoke",
            )
            db.add(report)
            await db.flush()

        fact = await db.scalar(
            select(TradeFact)
            .where(TradeFact.report_id == report.id)
            .where(TradeFact.table_name == "customswise_trade")
            .where(TradeFact.record_key == "Birgunj Customs|import")
        )
        if fact is None:
            fact = TradeFact(
                id=uuid4(),
                report_id=report.id,
                table_name="customswise_trade",
                direction=TradeDirection.IMPORT,
                customs_office="Birgunj Customs",
                value_npr_thousands=850000.0,
                cumulative_value_npr_thousands=850000.0,
                delta_value_npr_thousands=120000.0,
                record_key="Birgunj Customs|import",
                fact_metadata={"seed": True},
            )
            db.add(fact)
            await db.flush()

        anomaly = await db.scalar(
            select(TradeAnomaly)
            .where(TradeAnomaly.dimension == "customs_office")
            .where(TradeAnomaly.dimension_key == "birgunj_customs")
            .where(TradeAnomaly.fiscal_year_bs == "2082-83")
            .where(TradeAnomaly.month_ordinal == 4)
        )
        if anomaly is None:
            anomaly = TradeAnomaly(
                id=uuid4(),
                trade_fact_id=fact.id,
                dimension="customs_office",
                dimension_key="birgunj_customs",
                fiscal_year_bs="2082-83",
                month_ordinal=4,
                anomaly_score=3.9,
                observed_value=120000.0,
                expected_value=62000.0,
                baseline_mean=62000.0,
                baseline_std=14800.0,
                deviation_pct=93.55,
                severity="high",
                verification_status=AnalystVerificationStatus.CANDIDATE,
                rationale="Seeded anomaly: customs throughput spike",
            )
            db.add(anomaly)
            await db.flush()

        pwtt_service = PWTTPersistenceService(db)
        run = await db.scalar(
            select(DamageRun)
            .where(DamageRun.algorithm_name == "pwtt_smoke")
            .where(DamageRun.case_id == case.id)
        )
        if run is None:
            repo_root = Path(__file__).resolve().parents[2]
            artifact_base = repo_root / "pwtt-fixed-1km.png"
            artifact_after = repo_root / "pwtt-fixed-0.4km.png"

            run = await pwtt_service.create_run(
                initiated_by_id=user.id,
                assessment_id=None,
                case_id=case.id,
                algorithm_name="pwtt_smoke",
                algorithm_version="1.0",
                status=DamageRunStatus.COMPLETED,
                aoi_geojson={
                    "type": "Polygon",
                    "coordinates": [[[84.99, 27.68], [85.42, 27.68], [85.42, 27.88], [84.99, 27.88], [84.99, 27.68]]],
                },
                event_date=datetime.now(timezone.utc),
                run_params={"scenario": "smoke", "region": "Birgunj corridor"},
                summary={"note": "Seeded PWTT smoke run"},
                confidence_score=0.79,
                artifacts=[
                    {
                        "artifact_type": "three_panel_before",
                        "file_path": str(artifact_base),
                        "mime_type": "image/png",
                        "metadata": {"panel": "before"},
                    },
                    {
                        "artifact_type": "three_panel_after",
                        "file_path": str(artifact_after),
                        "mime_type": "image/png",
                        "metadata": {"panel": "after"},
                    },
                    {
                        "artifact_type": "three_panel_damage",
                        "file_path": str(artifact_base),
                        "mime_type": "image/png",
                        "metadata": {"panel": "damage"},
                    },
                ],
                findings=[
                    {
                        "finding_type": "corridor_damage",
                        "title": "Birgunj corridor disruption signature",
                        "severity": "high",
                        "confidence": 0.82,
                        "district": "Parsa",
                        "customs_office": "Birgunj Customs",
                        "route_name": "Birgunj-Kathmandu Corridor",
                        "metrics": {"damaged_segments": 3, "estimated_delay_hours": 11},
                    }
                ],
            )
            await db.flush()

        await pwtt_service.attach_run_to_case(
            run_id=run.id,
            case_id=case.id,
            added_by_id=user.id,
            include_findings=True,
        )

        hypothesis = await db.scalar(
            select(CaseHypothesis)
            .where(CaseHypothesis.case_id == case.id)
            .where(CaseHypothesis.statement == HYPOTHESIS_STATEMENT)
        )
        if hypothesis is None:
            hypothesis = CaseHypothesis(
                id=uuid4(),
                case_id=case.id,
                statement=HYPOTHESIS_STATEMENT,
                confidence=0.66,
                created_by_id=user.id,
                updated_by_id=user.id,
            )
            db.add(hypothesis)
            await db.flush()

        finding = (await pwtt_service.get_findings(run.id))[0]
        evidence_ref = await db.scalar(
            select(KBEvidenceRef)
            .where(KBEvidenceRef.owner_type == ProvenanceOwnerType.DAMAGE_FINDING)
            .where(KBEvidenceRef.owner_id == str(finding.id))
        )

        if evidence_ref is not None:
            existing = await db.scalar(
                select(HypothesisEvidenceLink)
                .where(HypothesisEvidenceLink.hypothesis_id == hypothesis.id)
                .where(HypothesisEvidenceLink.evidence_ref_id == evidence_ref.id)
            )
            if existing is None:
                db.add(
                    HypothesisEvidenceLink(
                        id=uuid4(),
                        hypothesis_id=hypothesis.id,
                        evidence_ref_id=evidence_ref.id,
                        relation_type=HypothesisEvidenceRelation.SUPPORTS,
                        weight=0.75,
                        notes="Seeded link from PWTT finding provenance",
                        created_by_id=user.id,
                    )
                )

        await db.commit()

        print("Connected analyst smoke scenario seeded")
        print(f"case_id={case.id}")
        print(f"hypothesis_id={hypothesis.id}")
        print(f"pwtt_run_id={run.id}")
        print(f"trade_anomaly_id={anomaly.id}")


if __name__ == "__main__":
    asyncio.run(seed())
