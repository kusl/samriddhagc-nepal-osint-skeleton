"""Nightly reconciliation report for unified investigation graph quality."""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass

from sqlalchemy import func, select, and_, or_

from app.core.database import AsyncSessionLocal
from app.models.graph import GraphNode, GraphEdge


@dataclass
class ReconciliationReport:
    disconnected_node_ratio: float
    synthetic_node_ratio: float
    candidate_person_bridge_coverage: float
    company_director_edge_coverage: float
    hierarchy_closure_coverage: float
    profile_quality_distribution: dict[str, int]
    thresholds_breached: list[str]


async def build_report(
    max_disconnected_ratio: float,
    max_synthetic_ratio: float,
    min_candidate_bridge_coverage: float,
    min_director_coverage: float,
    min_hierarchy_coverage: float,
) -> ReconciliationReport:
    async with AsyncSessionLocal() as db:
        canonical_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(GraphNode.is_canonical.is_(True))
            )
        ).scalar() or 0

        connected_ids = (
            await db.execute(
                select(GraphEdge.source_node_id)
                .where(GraphEdge.is_current.is_(True))
                .union(
                    select(GraphEdge.target_node_id).where(GraphEdge.is_current.is_(True))
                )
            )
        ).scalars().all()
        connected_set = set(connected_ids)

        disconnected_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(
                    GraphNode.is_canonical.is_(True),
                    ~GraphNode.id.in_(connected_set) if connected_set else True,
                )
            )
        ).scalar() or 0
        disconnected_ratio = disconnected_total / canonical_total if canonical_total else 0.0

        synthetic_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(
                    GraphNode.is_canonical.is_(True),
                    or_(
                        GraphNode.source_table == "synthetic",
                        GraphNode.properties["is_synthetic"].astext == "true",
                    ),
                )
            )
        ).scalar() or 0
        synthetic_ratio = synthetic_total / canonical_total if canonical_total else 0.0

        candidacy_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(
                    GraphNode.is_canonical.is_(True),
                    GraphNode.subtype == "candidacy",
                )
            )
        ).scalar() or 0
        bridged_candidacy_total = (
            await db.execute(
                select(func.count(func.distinct(GraphEdge.target_node_id))).where(
                    GraphEdge.is_current.is_(True),
                    GraphEdge.predicate == "identity_of_candidacy",
                )
            )
        ).scalar() or 0
        candidate_bridge_coverage = (
            bridged_candidacy_total / candidacy_total if candidacy_total else 1.0
        )

        company_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(
                    GraphNode.is_canonical.is_(True),
                    GraphNode.source_table == "company_registrations",
                )
            )
        ).scalar() or 0
        company_with_director = (
            await db.execute(
                select(func.count(func.distinct(GraphEdge.target_node_id))).where(
                    GraphEdge.is_current.is_(True),
                    GraphEdge.predicate == "director_of",
                )
            )
        ).scalar() or 0
        director_coverage = company_with_director / company_total if company_total else 1.0

        province_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(
                    GraphNode.is_canonical.is_(True),
                    GraphNode.source_table == "provinces",
                )
            )
        ).scalar() or 0
        province_linked = (
            await db.execute(
                select(func.count(func.distinct(GraphEdge.target_node_id))).where(
                    GraphEdge.is_current.is_(True),
                    GraphEdge.predicate == "parent_of",
                    GraphEdge.source_node_id.in_(
                        select(GraphNode.id).where(GraphNode.canonical_key == "country:nepal")
                    ),
                )
            )
        ).scalar() or 0
        district_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(
                    GraphNode.is_canonical.is_(True),
                    GraphNode.source_table == "districts",
                )
            )
        ).scalar() or 0
        district_linked = (
            await db.execute(
                select(func.count(func.distinct(GraphEdge.target_node_id))).where(
                    GraphEdge.is_current.is_(True),
                    GraphEdge.predicate == "parent_of",
                    GraphEdge.source_node_id.in_(
                        select(GraphNode.id).where(GraphNode.source_table == "provinces")
                    ),
                    GraphEdge.target_node_id.in_(
                        select(GraphNode.id).where(GraphNode.source_table == "districts")
                    ),
                )
            )
        ).scalar() or 0
        constituency_total = (
            await db.execute(
                select(func.count(GraphNode.id)).where(
                    GraphNode.is_canonical.is_(True),
                    GraphNode.source_table == "constituencies",
                )
            )
        ).scalar() or 0
        constituency_linked = (
            await db.execute(
                select(func.count(func.distinct(GraphEdge.target_node_id))).where(
                    GraphEdge.is_current.is_(True),
                    GraphEdge.predicate == "parent_of",
                    GraphEdge.source_node_id.in_(
                        select(GraphNode.id).where(GraphNode.source_table == "districts")
                    ),
                    GraphEdge.target_node_id.in_(
                        select(GraphNode.id).where(GraphNode.source_table == "constituencies")
                    ),
                )
            )
        ).scalar() or 0

        hierarchy_components = [
            province_linked / province_total if province_total else 1.0,
            district_linked / district_total if district_total else 1.0,
            constituency_linked / constituency_total if constituency_total else 1.0,
        ]
        hierarchy_closure_coverage = sum(hierarchy_components) / len(hierarchy_components)

        # Lightweight quality distribution based on required fields by node_type.
        quality_buckets = {"high": 0, "medium": 0, "low": 0}
        sample_nodes = (
            await db.execute(
                select(GraphNode).where(GraphNode.is_canonical.is_(True)).limit(5000)
            )
        ).scalars().all()
        for node in sample_nodes:
            missing = 0
            checks = 1
            if node.node_type in {"person", "organization"}:
                checks += 2
                missing += 1 if not node.title else 0
                missing += 1 if not node.source_table else 0
            if node.subtype in {"building", "building_signal"}:
                checks += 2
                missing += 1 if node.latitude is None else 0
                missing += 1 if node.longitude is None else 0
            score = 1 - (missing / checks)
            if score >= 0.8:
                quality_buckets["high"] += 1
            elif score >= 0.5:
                quality_buckets["medium"] += 1
            else:
                quality_buckets["low"] += 1

        breached: list[str] = []
        if disconnected_ratio > max_disconnected_ratio:
            breached.append(f"disconnected_node_ratio>{max_disconnected_ratio}")
        if synthetic_ratio > max_synthetic_ratio:
            breached.append(f"synthetic_node_ratio>{max_synthetic_ratio}")
        if candidate_bridge_coverage < min_candidate_bridge_coverage:
            breached.append(f"candidate_person_bridge_coverage<{min_candidate_bridge_coverage}")
        if director_coverage < min_director_coverage:
            breached.append(f"company_director_edge_coverage<{min_director_coverage}")
        if hierarchy_closure_coverage < min_hierarchy_coverage:
            breached.append(f"hierarchy_closure_coverage<{min_hierarchy_coverage}")

        return ReconciliationReport(
            disconnected_node_ratio=round(disconnected_ratio, 6),
            synthetic_node_ratio=round(synthetic_ratio, 6),
            candidate_person_bridge_coverage=round(candidate_bridge_coverage, 6),
            company_director_edge_coverage=round(director_coverage, 6),
            hierarchy_closure_coverage=round(hierarchy_closure_coverage, 6),
            profile_quality_distribution=quality_buckets,
            thresholds_breached=breached,
        )


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run unified graph reconciliation checks.")
    parser.add_argument("--max-disconnected-ratio", type=float, default=0.25)
    parser.add_argument("--max-synthetic-ratio", type=float, default=0.02)
    parser.add_argument("--min-candidate-bridge-coverage", type=float, default=0.9)
    parser.add_argument("--min-director-coverage", type=float, default=0.15)
    parser.add_argument("--min-hierarchy-coverage", type=float, default=0.95)
    args = parser.parse_args()

    report = await build_report(
        max_disconnected_ratio=args.max_disconnected_ratio,
        max_synthetic_ratio=args.max_synthetic_ratio,
        min_candidate_bridge_coverage=args.min_candidate_bridge_coverage,
        min_director_coverage=args.min_director_coverage,
        min_hierarchy_coverage=args.min_hierarchy_coverage,
    )
    print(json.dumps(asdict(report), ensure_ascii=False))
    return 1 if report.thresholds_breached else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
