#!/usr/bin/env python3
"""One-shot runner for the VPS OpenAI briefing service."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.services.openai_briefing_service import OpenAIBriefingService  # noqa: E402


async def main() -> int:
    async with AsyncSessionLocal() as db:
        service = OpenAIBriefingService(db=db)
        result = await service.run()
        print(
            json.dumps(
                {
                    "run_number": result["brief"].run_number,
                    "province_anomaly_run_id": str(result["province_anomaly_run"].id),
                    "stories_analyzed": result["stories_analyzed"],
                    "political_tweets_analyzed": result["tweets_analyzed"],
                    "period_start": result["period_start"],
                    "period_end": result["period_end"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
