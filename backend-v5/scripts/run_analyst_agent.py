"""Run the Narada Analyst Agent.

Usage:
    python scripts/run_analyst_agent.py              # analyze since last run
    python scripts/run_analyst_agent.py --hours 6    # analyze last 6 hours
    python scripts/run_analyst_agent.py --dry-run    # collect data, print context, don't call Claude
    python scripts/run_analyst_agent.py --province Bagmati  # single province
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def setup_logging(log_dir: Path) -> None:
    """Configure dual logging (console + file)."""
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"analyst_agent_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ],
    )
    logging.getLogger(__name__).info("Logging to %s", log_file)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Narada Analyst Agent")
    parser.add_argument(
        "--hours", type=int, default=3,
        help="Analysis window in hours (default: 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Collect data and print contexts without calling Claude",
    )
    parser.add_argument(
        "--province", type=str, default=None,
        help="Analyze only this province (e.g. 'Bagmati')",
    )
    args = parser.parse_args()

    # Setup logging
    project_root = Path(__file__).resolve().parent.parent
    setup_logging(project_root / "logs")

    logger = logging.getLogger("analyst_agent")
    logger.info("Starting Narada Analyst Agent")
    logger.info("  Hours: %d, Dry run: %s, Province: %s",
                args.hours, args.dry_run, args.province or "all")

    # Import after path setup
    from app.core.database import AsyncSessionLocal
    from app.services.analyst_agent.agent import NaradaAnalystAgent

    async with AsyncSessionLocal() as db:
        agent = NaradaAnalystAgent(
            db=db,
            hours=args.hours,
            province_filter=args.province,
            dry_run=args.dry_run,
        )
        try:
            brief = await agent.run()
            logger.info("Agent completed: run #%d, status=%s", brief.run_number, brief.status)
            if brief.national_summary:
                logger.info("National summary: %s", brief.national_summary[:200])
            return 0
        except Exception as e:
            logger.error("Agent failed: %s", e, exc_info=True)
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
