"""
Benchmark accuracy/F1 of the OSINT RL/ML pipeline using ExperienceRecords.

This evaluates against stored ground-truth labels (human_action) collected via:
  - Analyst publish/override workflow (Ops)
  - Manual feedback API (/api/v1/ml/feedback)

Outputs both:
  - "as-recorded" system_action vs human_action (what the system believed at that time)
  - "current model" predictions vs human_action (what the active model predicts now)
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

import numpy as np
import sys
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.ml.evaluation import compute_classification_metrics  # noqa: E402
from app.ml.inference import get_predictor  # noqa: E402
from app.models.experience_record import ExperienceRecord, ExperienceType  # noqa: E402
from app.models.story import Story  # noqa: E402


CATEGORIES = ["political", "economic", "security", "disaster", "social"]
PRIORITIES = ["low", "medium", "high", "critical"]


def _print_block(title: str):
    print("")
    print(title)
    print("-" * len(title))


async def _load_stories(db, story_ids: list[UUID]) -> dict[UUID, Story]:
    if not story_ids:
        return {}
    result = await db.execute(select(Story).where(Story.id.in_(story_ids)))
    return {s.id: s for s in result.scalars().all()}


def _summarize_metrics(metrics: dict) -> str:
    return (
        f"acc={metrics['accuracy']:.3f} "
        f"macro_f1={metrics['macro_f1']:.3f} "
        f"support={metrics['support']}"
    )


async def run(hours: int, limit: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    predictor = get_predictor()
    if not predictor._initialized:
        predictor.initialize()

    async with AsyncSessionLocal() as db:
        q = (
            select(ExperienceRecord)
            .where(ExperienceRecord.created_at >= cutoff)
            .order_by(ExperienceRecord.created_at.desc())
        )
        if limit > 0:
            q = q.limit(limit)

        records = list((await db.execute(q)).scalars().all())

        _print_block("Experience buffer snapshot")
        by_type: dict[str, int] = {}
        for r in records:
            by_type[r.experience_type] = by_type.get(r.experience_type, 0) + 1
        print(f"Window: last {hours}h | records: {len(records)}")
        print(f"By type: {by_type}")

        # -------------------------
        # Classification benchmark
        # -------------------------
        cls_records = [r for r in records if r.experience_type == ExperienceType.CLASSIFICATION]
        if cls_records:
            story_ids = [r.story_id for r in cls_records if r.story_id]
            stories = await _load_stories(db, [sid for sid in story_ids if sid])

            y_true: list[str] = []
            y_sys: list[str] = []
            y_now: list[str] = []

            for r in cls_records:
                if not r.human_action:
                    continue
                story = stories.get(r.story_id) if r.story_id else None
                title = story.title if story else (r.context_features or {}).get("text", "") or ""
                summary = story.summary if story else None

                pred_now = predictor.classify_story(title=title, content=summary).category

                y_true.append(r.human_action.lower())
                y_sys.append((r.system_action or "unknown").lower())
                y_now.append((pred_now or "unknown").lower())

            _print_block("Category classification (classification feedback)")
            m_sys = compute_classification_metrics(y_true, y_sys, labels=CATEGORIES)
            m_now = compute_classification_metrics(y_true, y_now, labels=CATEGORIES)
            print(f"System-at-label-time  : {_summarize_metrics(m_sys)}")
            print(f"Current active model  : {_summarize_metrics(m_now)}")
        else:
            _print_block("Category classification (classification feedback)")
            print("No CLASSIFICATION experience records in this window.")

        # -------------------------
        # Priority benchmark
        # -------------------------
        pr_records = [r for r in records if r.experience_type == ExperienceType.PRIORITY]
        if pr_records:
            y_true_p: list[str] = []
            y_sys_p: list[str] = []
            y_now_p: list[str] = []

            for r in pr_records:
                if not r.human_action:
                    continue
                ctx = r.context_features or {}
                feats = ctx.get("features")
                if not isinstance(feats, list) or not feats:
                    continue

                context = np.asarray(feats, dtype=np.float32)
                pred_now = predictor.priority_bandit.predict(context, explore=False).priority

                y_true_p.append(r.human_action.lower())
                y_sys_p.append((r.system_action or "medium").lower())
                y_now_p.append((pred_now or "medium").lower())

            _print_block("Priority/severity (priority feedback)")
            m_sys_p = compute_classification_metrics(y_true_p, y_sys_p, labels=PRIORITIES)
            m_now_p = compute_classification_metrics(y_true_p, y_now_p, labels=PRIORITIES)
            print(f"System-at-label-time  : {_summarize_metrics(m_sys_p)}")
            print(f"Current active model  : {_summarize_metrics(m_now_p)}")
        else:
            _print_block("Priority/severity (priority feedback)")
            print("No PRIORITY experience records in this window.")

        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark OSINT RL/ML models using ExperienceRecords.")
    parser.add_argument("--hours", type=int, default=168, help="Time window in hours (default: 168)")
    parser.add_argument("--limit", type=int, default=0, help="Limit records evaluated (0 = no limit)")
    args = parser.parse_args()

    return asyncio.run(run(hours=args.hours, limit=args.limit))


if __name__ == "__main__":
    raise SystemExit(main())

