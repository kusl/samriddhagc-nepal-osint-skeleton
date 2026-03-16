"""
Soft-dedup benchmark for clustered events.

Compares:
  - Existing behavior: show every story inside an event cluster
  - New behavior: soft-dedup groups (near-identical stories collapse to 1 canonical)

This is NOT a clustering-quality benchmark; it focuses on duplicate suppression
within an already-formed cluster.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Iterable, Optional
from uuid import UUID

import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import AsyncSessionLocal
from app.models.story import Story
from app.models.story_cluster import StoryCluster
from app.services.ops.event_dedup import group_stories_by_near_duplicate


PRIORITY_CATEGORIES = {"political", "security", "disaster"}


@dataclass(frozen=True)
class ClusterMetrics:
    cluster_id: UUID
    headline: str
    category: str
    severity: str
    stories_actual: int
    groups: int
    dupes_collapsed: int
    group_ms: float


def _fmt_pct(n: int, d: int) -> str:
    if d <= 0:
        return "0.0%"
    return f"{(100.0 * n / d):.1f}%"


async def _count_nepal_stories(db: AsyncSession, cutoff: datetime, clustered: Optional[bool]) -> int:
    query = select(func.count(Story.id)).where(
        Story.created_at >= cutoff,
        Story.nepal_relevance.in_(["NEPAL_DOMESTIC", "NEPAL_NEIGHBOR"]),
    )

    if clustered is True:
        query = query.where(Story.cluster_id.isnot(None))
    elif clustered is False:
        query = query.where(Story.cluster_id.is_(None))

    return int(await db.scalar(query) or 0)


async def _load_clusters(db: AsyncSession, cutoff: datetime, limit: Optional[int]) -> list[StoryCluster]:
    query = (
        select(StoryCluster)
        .options(selectinload(StoryCluster.stories))
        .where(StoryCluster.first_published >= cutoff)
        .order_by(StoryCluster.last_updated.desc().nullslast())
    )
    if limit:
        query = query.limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


def _sum(values: Iterable[int]) -> int:
    total = 0
    for v in values:
        total += v
    return total


async def run(hours: int, threshold: float, limit: Optional[int], top: int) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    async with AsyncSessionLocal() as db:
        clusters = await _load_clusters(db, cutoff, limit)

        # Event detection coverage (simple proxy)
        total_stories = await _count_nepal_stories(db, cutoff, clustered=None)
        clustered_stories = await _count_nepal_stories(db, cutoff, clustered=True)
        unclustered_stories = await _count_nepal_stories(db, cutoff, clustered=False)

        metrics: list[ClusterMetrics] = []
        mismatched_counts = 0
        empty_clusters = 0

        for c in clusters:
            stories = list(c.stories or [])
            stories_actual = len(stories)
            if stories_actual == 0:
                empty_clusters += 1
                groups = 0
                group_ms = 0.0
            else:
                t0 = perf_counter()
                grouped = await group_stories_by_near_duplicate(db, stories, similarity_threshold=threshold)
                group_ms = (perf_counter() - t0) * 1000.0
                groups = len(grouped)

            if (c.story_count or 0) != stories_actual:
                mismatched_counts += 1

            category = (c.category or "unknown").lower()
            severity = (c.severity or "low").lower()
            dupes_collapsed = max(0, stories_actual - groups)

            metrics.append(
                ClusterMetrics(
                    cluster_id=c.id,
                    headline=c.headline,
                    category=category,
                    severity=severity,
                    stories_actual=stories_actual,
                    groups=groups,
                    dupes_collapsed=dupes_collapsed,
                    group_ms=group_ms,
                )
            )

        stories_in_clusters = _sum(m.stories_actual for m in metrics)
        groups_total = _sum(m.groups for m in metrics)
        dupes_total = _sum(m.dupes_collapsed for m in metrics)
        clusters_with_dupes = _sum(1 for m in metrics if m.dupes_collapsed > 0)
        priority_dupes = _sum(m.dupes_collapsed for m in metrics if m.category in PRIORITY_CATEGORIES)
        priority_stories = _sum(m.stories_actual for m in metrics if m.category in PRIORITY_CATEGORIES)
        group_ms_avg = (sum(m.group_ms for m in metrics) / max(1, len([m for m in metrics if m.stories_actual > 0])))

        print("")
        print("SOFT DEDUP BENCHMARK (within clusters)")
        print("====================================")
        print(f"Window: last {hours}h | similarity_threshold={threshold}")
        if limit:
            print(f"Cluster sample limit: {limit}")
        print("")
        print("Event detection (proxy, story-level)")
        print(f"- Total Nepal-relevant stories: {total_stories}")
        print(f"- Clustered stories: {clustered_stories} ({_fmt_pct(clustered_stories, total_stories)})")
        print(f"- Unclustered stories: {unclustered_stories} ({_fmt_pct(unclustered_stories, total_stories)})")
        print("")
        print("Duplicate suppression (cluster-level)")
        print(f"- Clusters evaluated: {len(metrics)}")
        print(f"- Empty clusters (no linked stories): {empty_clusters}")
        print(f"- Count mismatches (story_count != linked stories): {mismatched_counts}")
        print("")
        print("Existing behavior (no soft dedup)")
        print(f"- Display items (expanded): {stories_in_clusters}")
        print("")
        print("New behavior (soft dedup groups)")
        print(f"- Display items (expanded): {groups_total}")
        print(f"- Duplicates collapsed: {dupes_total} ({_fmt_pct(dupes_total, stories_in_clusters)})")
        print(f"- Clusters with any duplicates: {clusters_with_dupes}/{len(metrics)}")
        print(f"- Avg grouping time per non-empty cluster: {group_ms_avg:.1f} ms")
        print("")
        print("Priority domains (political/security/disaster)")
        print(f"- Stories: {priority_stories}")
        print(f"- Duplicates collapsed: {priority_dupes} ({_fmt_pct(priority_dupes, priority_stories)})")
        print("")

        if top > 0:
            print(f"Top {top} clusters by duplicates collapsed")
            for m in sorted(metrics, key=lambda x: (x.dupes_collapsed, x.stories_actual), reverse=True)[:top]:
                if m.dupes_collapsed <= 0:
                    break
                print(
                    f"- {m.cluster_id} | {m.category}/{m.severity} | "
                    f"{m.stories_actual}→{m.groups} (collapsed {m.dupes_collapsed}) | "
                    f"{m.headline[:120]}"
                )

        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark soft dedup inside event clusters.")
    parser.add_argument("--hours", type=int, default=72, help="Time window in hours (default: 72)")
    parser.add_argument("--threshold", type=float, default=0.95, help="Embedding similarity threshold (default: 0.95)")
    parser.add_argument("--limit", type=int, default=0, help="Limit clusters evaluated (0 = no limit)")
    parser.add_argument("--top", type=int, default=10, help="Show top N clusters by dupes collapsed (default: 10)")
    args = parser.parse_args()

    limit = None if args.limit == 0 else args.limit
    return asyncio.run(run(hours=args.hours, threshold=args.threshold, limit=limit, top=args.top))


if __name__ == "__main__":
    raise SystemExit(main())
