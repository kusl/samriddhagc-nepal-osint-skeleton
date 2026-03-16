#!/usr/bin/env python3
"""
Parliament Data Sync Script.

Run the complete parliament scraping and scoring pipeline.
Usage:
    python scripts/parliament_sync.py                  # Full sync
    python scripts/parliament_sync.py --members        # Members only
    python scripts/parliament_sync.py --bills          # Bills with details
    python scripts/parliament_sync.py --committees     # Committees + members
    python scripts/parliament_sync.py --videos         # Video/speech matching
    python scripts/parliament_sync.py --score          # Recalculate scores only
    python scripts/parliament_sync.py --stats          # Show current data stats
"""
import argparse
from datetime import date, datetime
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(name)s: %(message)s'
)
logger = logging.getLogger('parliament_sync')


async def sync_members(db):
    """Scrape MP profiles from both chambers."""
    from app.ingestion.parliament_scraper import ParliamentScraper
    from app.repositories.parliament import MPPerformanceRepository
    from app.services.parliament_linker import ParliamentLinker

    async with ParliamentScraper(rate_limit=0.5) as scraper:
        repo = MPPerformanceRepository(db)
        total = 0

        for chamber in ['hor', 'na']:
            try:
                members = await scraper.scrape_members(chamber)
                logger.info(f"Scraped {len(members)} {chamber.upper()} members")

                for member in members:
                    await repo.upsert({
                        'mp_id': member.mp_id,
                        'name_en': member.name_en,
                        'name_ne': member.name_ne,
                        'party': member.party,
                        'constituency': member.constituency,
                        'chamber': chamber,
                        'photo_url': member.photo_url,
                        'is_minister': member.is_minister,
                        'ministry_portfolio': member.ministry_portfolio,
                    })
                total += len(members)
            except Exception as e:
                logger.exception(f"Error scraping {chamber} members: {e}")

        await db.commit()

        # Link to election candidates
        try:
            linker = ParliamentLinker(db)
            link_results = await linker.link_all_members()
            logger.info(f"Linked {link_results['linked']} MPs to election candidates")
        except Exception as e:
            logger.exception(f"Error linking MPs: {e}")

    return total


async def _safe_date(date_val):
    """Convert date value to datetime.date or None. Handles BS date strings gracefully."""
    if date_val is None:
        return None
    if isinstance(date_val, date):
        return date_val
    if isinstance(date_val, str):
        # Try parsing as AD date first
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y'):
            try:
                return datetime.strptime(date_val, fmt).date()
            except ValueError:
                continue
        # BS dates (e.g. '2082-03-29') can't be stored as SQL DATE — skip
        return None
    return None


async def sync_bills(db):
    """Scrape bills with detail pages for presenter names."""
    from app.ingestion.parliament_scraper import ParliamentScraper
    from app.repositories.parliament import BillRepository, MPPerformanceRepository

    async with ParliamentScraper(rate_limit=0.8) as scraper:
        bill_repo = BillRepository(db)
        mp_repo = MPPerformanceRepository(db)
        total = 0

        for chamber in ['hor', 'na']:
            for bill_type in ['registered', 'passed', 'state']:
                try:
                    bills = await scraper.scrape_bills_with_details(
                        bill_type=bill_type,
                        chamber=chamber,
                        max_pages=10,
                        fetch_details=True,
                    )
                    logger.info(f"Scraped {len(bills)} {bill_type} bills from {chamber.upper()}")

                    for bill in bills:
                        try:
                            presenting_mp_id = None
                            if bill.presenting_mp_name:
                                mps = await mp_repo.search_by_name(bill.presenting_mp_name, limit=1)
                                if mps:
                                    presenting_mp_id = mps[0].id

                            await bill_repo.upsert({
                                'external_id': bill.external_id,
                                'title_en': bill.title_en,
                                'title_ne': bill.title_ne,
                                'bill_type': bill.bill_type,
                                'status': bill.status,
                                'presented_date': await _safe_date(bill.presented_date),
                                'presenting_mp_id': presenting_mp_id,
                                'ministry': bill.ministry,
                                'chamber': chamber,
                                'term': bill.term,
                                'pdf_url': bill.pdf_url,
                            })
                        except Exception as e:
                            logger.warning(f"Error upserting bill {bill.external_id}: {e}")
                            await db.rollback()
                    total += len(bills)
                    await db.commit()
                except Exception as e:
                    logger.exception(f"Error scraping {chamber} {bill_type} bills: {e}")
                    await db.rollback()

    return total


async def sync_committees(db):
    """Scrape committees and their member lists."""
    from app.ingestion.parliament_scraper import ParliamentScraper
    from app.repositories.parliament import MPPerformanceRepository
    from app.models.parliament import CommitteeMembership, ParliamentCommittee

    async with ParliamentScraper(rate_limit=0.8) as scraper:
        mp_repo = MPPerformanceRepository(db)
        total_committees = 0
        total_memberships = 0

        for chamber in ['hor', 'na']:
            try:
                committees = await scraper.scrape_committees(chamber)
                logger.info(f"Scraped {len(committees)} committees from {chamber.upper()}")

                for committee_data in committees:
                    # Upsert committee
                    from sqlalchemy import select
                    result = await db.execute(
                        select(ParliamentCommittee).where(
                            ParliamentCommittee.external_id == ext_id,
                            ParliamentCommittee.chamber == chamber,
                        )
                    )
                    db_committee = result.scalar_one_or_none()

                    # Truncate long external_ids (some committee slugs > 100 chars)
                    ext_id = committee_data.external_id[:250] if committee_data.external_id else None

                    if db_committee:
                        db_committee.name_en = committee_data.name_en
                        db_committee.committee_type = committee_data.committee_type
                        db_committee.is_active = True
                    else:
                        db_committee = ParliamentCommittee(
                            external_id=ext_id,
                            name_en=committee_data.name_en,
                            name_ne=committee_data.name_ne,
                            committee_type=committee_data.committee_type,
                            chamber=chamber,
                            is_active=True,
                        )
                        db.add(db_committee)
                        await db.flush()

                    total_committees += 1

                    # Upsert members
                    for member_data in committee_data.members:
                        mps = await mp_repo.search_by_name(member_data['name'], limit=1)
                        if not mps:
                            continue

                        mp = mps[0]
                        result = await db.execute(
                            select(CommitteeMembership).where(
                                CommitteeMembership.committee_id == db_committee.id,
                                CommitteeMembership.mp_id == mp.id,
                            )
                        )
                        existing = result.scalar_one_or_none()

                        if existing:
                            existing.role = member_data.get('role', 'member')
                            existing.is_current = True
                        else:
                            membership = CommitteeMembership(
                                committee_id=db_committee.id,
                                mp_id=mp.id,
                                role=member_data.get('role', 'member'),
                                is_current=True,
                            )
                            db.add(membership)
                            total_memberships += 1

                await db.commit()
            except Exception as e:
                logger.exception(f"Error scraping {chamber} committees: {e}")
                await db.rollback()

    logger.info(f"Synced {total_committees} committees, {total_memberships} new memberships")
    return total_committees


async def sync_videos(db):
    """Match video speakers to MPs and update speech counts."""
    from app.services.parliament_linker import ParliamentLinker

    linker = ParliamentLinker(db)
    total_matched = 0

    for chamber in ['hor', 'na']:
        try:
            stats = await linker.match_video_speakers(
                chamber=chamber,
                max_pages=30,
                max_sessions=200,
            )
            logger.info(
                f"Video matching ({chamber.upper()}): "
                f"{stats['total_videos']} videos, "
                f"{stats['matched_speakers']}/{stats['unique_speakers']} speakers matched, "
                f"{stats['mps_updated']} MPs updated"
            )
            if stats.get('unmatched_details'):
                logger.info(f"Top unmatched speakers: {[s['speaker'] for s in stats['unmatched_details'][:5]]}")
            total_matched += stats['matched_speakers']
        except Exception as e:
            logger.exception(f"Error matching {chamber} video speakers: {e}")

    await db.commit()
    return total_matched


async def recalculate_scores(db):
    """Recalculate all MP performance scores."""
    from app.services.parliament_scorer import PerformanceScorer

    scorer = PerformanceScorer(db)
    stats = await scorer.calculate_all_scores()
    logger.info(
        f"Score calculation complete: {stats['total_scored']} MPs scored, "
        f"avg score: {stats['avg_score']:.1f}, "
        f"top: {stats.get('top_performer', 'N/A')}"
    )
    return stats


async def show_stats(db):
    """Show current data quality statistics."""
    from sqlalchemy import text

    result = await db.execute(text("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN bills_introduced > 0 THEN 1 END) as has_bills,
            COUNT(CASE WHEN speeches_count > 0 THEN 1 END) as has_speeches,
            COUNT(CASE WHEN committee_memberships > 0 THEN 1 END) as has_committees,
            COUNT(CASE WHEN session_attendance_pct > 0 THEN 1 END) as has_attendance,
            COUNT(CASE WHEN questions_asked > 0 THEN 1 END) as has_questions,
            ROUND(AVG(performance_score)::numeric, 1) as avg_score,
            MAX(performance_score) as max_score,
            COUNT(CASE WHEN performance_score > 0 THEN 1 END) as has_score
        FROM mp_performance
        WHERE is_current_member = true
    """))
    row = result.fetchone()

    print("\n" + "=" * 60)
    print("  PARLIAMENT DATA QUALITY REPORT")
    print("=" * 60)
    print(f"  Total current MPs:          {row[0]}")
    print(f"  MPs with bills:             {row[1]} ({row[1]*100//max(row[0],1)}%)")
    print(f"  MPs with speeches:          {row[2]} ({row[2]*100//max(row[0],1)}%)")
    print(f"  MPs with committees:        {row[3]} ({row[3]*100//max(row[0],1)}%)")
    print(f"  MPs with attendance:        {row[4]} ({row[4]*100//max(row[0],1)}%)")
    print(f"  MPs with questions:         {row[5]} ({row[5]*100//max(row[0],1)}%)")
    print(f"  MPs with any score > 0:     {row[8]} ({row[8]*100//max(row[0],1)}%)")
    print(f"  Average performance score:  {row[6]}")
    print(f"  Max performance score:      {row[7]:.1f}")
    print("=" * 60)

    # Top 5
    result = await db.execute(text("""
        SELECT name_en, party, performance_score, performance_tier,
               bills_introduced, speeches_count, committee_memberships
        FROM mp_performance
        WHERE is_current_member = true
        ORDER BY performance_score DESC
        LIMIT 5
    """))
    rows = result.fetchall()
    print("\n  TOP 5 MPs:")
    for i, r in enumerate(rows, 1):
        print(f"  {i}. {r[0]} ({r[1]}) — Score: {r[2]:.1f} [{r[3]}]")
        print(f"     Bills: {r[4]}, Speeches: {r[5]}, Committees: {r[6]}")
    print()


async def main():
    parser = argparse.ArgumentParser(description='Parliament Data Sync')
    parser.add_argument('--members', action='store_true', help='Sync MP profiles')
    parser.add_argument('--bills', action='store_true', help='Sync bills with details')
    parser.add_argument('--committees', action='store_true', help='Sync committees')
    parser.add_argument('--videos', action='store_true', help='Match video speakers')
    parser.add_argument('--score', action='store_true', help='Recalculate scores')
    parser.add_argument('--stats', action='store_true', help='Show data stats')
    args = parser.parse_args()

    # If no specific flag, run everything
    run_all = not any([args.members, args.bills, args.committees, args.videos, args.score, args.stats])

    async with AsyncSessionLocal() as db:
        if args.stats:
            await show_stats(db)
            return

        if run_all or args.members:
            logger.info("=== SYNCING MEMBERS ===")
            await sync_members(db)

        if run_all or args.committees:
            logger.info("=== SYNCING COMMITTEES ===")
            await sync_committees(db)

        if run_all or args.bills:
            logger.info("=== SYNCING BILLS ===")
            await sync_bills(db)

        if run_all or args.videos:
            logger.info("=== SYNCING VIDEOS ===")
            await sync_videos(db)

        if run_all or args.score:
            logger.info("=== RECALCULATING SCORES ===")
            await recalculate_scores(db)

        # Always show stats at the end
        await show_stats(db)


if __name__ == '__main__':
    asyncio.run(main())
