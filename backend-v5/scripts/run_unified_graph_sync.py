"""Manual replay command for unified election + graph sync."""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from app.core.database import AsyncSessionLocal
from app.services.graph.graph_ingestion_service import GraphIngestionService
from app.services.graph.entity_resolution_service import EntityResolutionService
from app.services.graph.graph_metrics_service import GraphMetricsService


async def run_graph_pipeline(skip_metrics: bool = False) -> dict:
    root = Path(__file__).resolve().parents[1]
    async with AsyncSessionLocal() as db:
        ingestion = GraphIngestionService(db)
        ingest_stats = await ingestion.run_full_ingestion()

        resolver = EntityResolutionService(db)
        resolution_stats = await resolver.run_full_resolution()

        metrics_stats = {}
        if not skip_metrics:
            metrics = GraphMetricsService(db)
            metrics_stats = await metrics.compute_all_metrics()

    reconciliation_script = root / "scripts" / "unified_graph_reconciliation.py"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(reconciliation_script),
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out_text = stdout.decode("utf-8", errors="ignore").strip()
    if proc.returncode not in (0, 1):
        raise RuntimeError(stderr.decode("utf-8", errors="ignore").strip() or "reconciliation failed")
    report = json.loads(out_text) if out_text else {}
    return {
        "ingestion": ingest_stats,
        "resolution": resolution_stats,
        "metrics": metrics_stats,
        "reconciliation": report,
    }


def run_election_import() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "import_election_data.py"
    cmd = [
        sys.executable,
        str(script),
        "--all",
        "--replace-existing",
        "--link-entities",
        "--reapply-overrides",
        "--reconcile",
    ]
    subprocess.run(cmd, cwd=str(root), check=True)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Manual replay of unified election + graph sync.")
    parser.add_argument("--skip-election-import", action="store_true")
    parser.add_argument("--skip-metrics", action="store_true")
    args = parser.parse_args()

    if not args.skip_election_import:
        run_election_import()

    summary = await run_graph_pipeline(skip_metrics=args.skip_metrics)
    print(json.dumps(summary, ensure_ascii=False))

    breached = summary["reconciliation"].get("thresholds_breached", [])
    return 1 if breached else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
