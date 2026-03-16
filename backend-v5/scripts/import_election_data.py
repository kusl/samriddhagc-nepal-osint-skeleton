#!/usr/bin/env python3
"""Import election data from static JSON files into PostgreSQL.

This script imports election results from the frontend's static JSON files:
- election-results-2074.json (BS) = 2017 (AD)
- election-results-2079.json (BS) = 2022 (AD)
- election-results-2082.json (BS) = 2025 (AD)

Usage:
    cd backend-v5
    python scripts/import_election_data.py

    # Import specific years only
    python scripts/import_election_data.py --years 2079,2082

    # Clear existing data before import
    python scripts/import_election_data.py --clear

    # Full unified replay pipeline (import + link + overrides + reconcile)
    python scripts/import_election_data.py --all --replace-existing --link-entities --reapply-overrides --reconcile
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import click
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
settings = get_settings()
from app.models.election import (
    Election,
    Constituency,
    Candidate,
    ElectionType,
    ElectionStatus,
    ConstituencyStatus,
)
from app.services.entity_linker import link_all_entities
from app.services.candidate_profile_resolver import CandidateProfileResolver
from app.models.election_sync_run import ElectionSyncRun

# Path to JSON files (relative to project root)
JSON_DATA_DIR = Path(__file__).parent.parent.parent / "frontend" / "public" / "data"

# BS to AD year mapping
BS_TO_AD = {
    2074: 2017,
    2079: 2022,
    2082: 2025,
}


async def get_db_session() -> AsyncSession:
    """Create async database session."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()


async def clear_election_data(db: AsyncSession, year_bs: Optional[int] = None):
    """Clear existing election data."""
    if year_bs:
        # Find election by year
        result = await db.execute(select(Election).where(Election.year_bs == year_bs))
        election = result.scalar_one_or_none()
        if election:
            # Delete cascades to constituencies and candidates
            await db.delete(election)
            await db.commit()
            print(f"  Cleared election data for {year_bs} BS")
    else:
        # Clear all election data
        await db.execute(delete(Candidate))
        await db.execute(delete(Constituency))
        await db.execute(delete(Election))
        await db.commit()
        print("  Cleared all election data")


async def import_election_year(db: AsyncSession, year_bs: int, replace_existing: bool = True):
    """Import election data for a specific year."""
    json_file = JSON_DATA_DIR / f"election-results-{year_bs}.json"

    if not json_file.exists():
        print(f"  JSON file not found: {json_file}")
        return False

    print(f"\nImporting election year {year_bs} BS ({BS_TO_AD.get(year_bs, '?')} AD)...")

    # Load JSON data
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Check if election already exists
    result = await db.execute(select(Election).where(Election.year_bs == year_bs))
    existing_election = result.scalar_one_or_none()

    if existing_election:
        if replace_existing:
            await clear_election_data(db, year_bs)
        else:
            print(f"  Election {year_bs} already exists. Use --replace-existing to refresh.")
            return False

    # Determine election status based on results
    results = data.get("results", [])
    declared_count = sum(1 for r in results if r.get("status") == "declared")
    total = len(results)

    if declared_count == total:
        status = ElectionStatus.COMPLETED.value
    elif declared_count > 0:
        status = ElectionStatus.ONGOING.value
    else:
        status = ElectionStatus.UPCOMING.value

    # Calculate totals
    total_votes = sum(r.get("total_votes", 0) or 0 for r in results)

    # Create Election record
    election = Election(
        id=uuid4(),
        year_bs=year_bs,
        year_ad=BS_TO_AD.get(year_bs, year_bs - 57),
        election_type=ElectionType.PARLIAMENTARY.value,
        status=status,
        total_constituencies=data.get("total_constituencies", total),
        total_votes_cast=total_votes if total_votes > 0 else None,
    )
    db.add(election)
    await db.flush()  # Get election ID

    print(f"  Created election: {election.year_bs} BS, status={status}")

    # Import constituencies and candidates
    constituency_count = 0
    candidate_count = 0

    for result_data in results:
        # Map status string to enum
        status_str = result_data.get("status", "pending")
        if status_str == "declared":
            const_status = ConstituencyStatus.DECLARED.value
        elif status_str == "counting":
            const_status = ConstituencyStatus.COUNTING.value
        else:
            const_status = ConstituencyStatus.PENDING.value

        # Create Constituency record
        constituency = Constituency(
            id=uuid4(),
            election_id=election.id,
            constituency_code=result_data["constituency_id"],
            name_en=result_data["name_en"],
            name_ne=result_data.get("name_ne"),
            district=result_data["district"],
            province=result_data["province"],
            province_id=result_data["province_id"],
            status=const_status,
            total_votes_cast=result_data.get("total_votes"),
            turnout_pct=result_data.get("turnout_pct"),
            winner_party=result_data.get("winner_party"),
            winner_votes=result_data.get("winner_votes"),
        )
        db.add(constituency)
        await db.flush()  # Get constituency ID
        constituency_count += 1

        # Import candidates
        winner_id = None
        candidates_data = result_data.get("candidates", [])

        for i, cand_data in enumerate(candidates_data):
            candidate = Candidate(
                id=uuid4(),
                election_id=election.id,
                constituency_id=constituency.id,
                external_id=cand_data["id"],
                name_en=cand_data["name_en"],
                name_ne=cand_data.get("name_ne"),
                party=cand_data["party"],
                votes=cand_data.get("votes", 0),
                vote_pct=cand_data.get("vote_pct", 0.0),
                rank=i + 1,  # Assumes candidates are sorted by votes
                is_winner=cand_data.get("is_winner", False),
                photo_url=cand_data.get("photo_url"),
                age=cand_data.get("age"),
                gender=cand_data.get("gender"),
                education=cand_data.get("education"),
                education_institution=cand_data.get("education_institution"),
                # Biography and enrichment fields
                name_en_roman=cand_data.get("name_en_roman"),
                aliases=cand_data.get("aliases"),
                biography=cand_data.get("biography"),
                biography_source=cand_data.get("biography_source"),
                is_notable=cand_data.get("is_notable", False),
                previous_positions=cand_data.get("previous_positions"),
            )
            db.add(candidate)
            candidate_count += 1

            if cand_data.get("is_winner"):
                winner_id = candidate.id

        # Flush candidates before setting winner reference
        await db.flush()

        # Update constituency with winner reference
        if winner_id:
            constituency.winner_candidate_id = winner_id
            # Calculate margin
            if len(candidates_data) >= 2:
                sorted_by_votes = sorted(candidates_data, key=lambda x: x.get("votes", 0), reverse=True)
                if sorted_by_votes[0].get("votes") and sorted_by_votes[1].get("votes"):
                    constituency.winner_margin = sorted_by_votes[0]["votes"] - sorted_by_votes[1]["votes"]

    await db.commit()

    print(f"  Imported {constituency_count} constituencies, {candidate_count} candidates")
    return True


async def reconcile_year(db: AsyncSession, year_bs: int) -> dict:
    """Compare DB counts vs source JSON for key election signals."""
    json_file = JSON_DATA_DIR / f"election-results-{year_bs}.json"
    if not json_file.exists():
        return {"year": year_bs, "error": "source_json_missing"}

    with open(json_file, "r", encoding="utf-8") as f:
        source = json.load(f)

    source_results = source.get("results", [])
    source_constituencies = len(source_results)
    source_candidates = sum(len(r.get("candidates", [])) for r in source_results)
    source_winners = sum(1 for r in source_results if r.get("winner_party"))
    source_total_votes = sum((r.get("total_votes") or 0) for r in source_results)
    source_missing_bio_source = sum(
        1
        for r in source_results
        for c in r.get("candidates", [])
        if not c.get("biography_source")
    )

    election_result = await db.execute(select(Election).where(Election.year_bs == year_bs))
    election = election_result.scalar_one_or_none()
    if not election:
        return {"year": year_bs, "error": "db_election_missing"}

    db_constituencies = (await db.execute(
        select(func.count(Constituency.id)).where(Constituency.election_id == election.id)
    )).scalar() or 0
    db_candidates = (await db.execute(
        select(func.count(Candidate.id)).where(Candidate.election_id == election.id)
    )).scalar() or 0
    db_winners = (await db.execute(
        select(func.count(Candidate.id)).where(
            Candidate.election_id == election.id,
            Candidate.is_winner.is_(True),
        )
    )).scalar() or 0
    db_total_votes = (await db.execute(
        select(func.sum(Constituency.total_votes_cast)).where(
            Constituency.election_id == election.id
        )
    )).scalar() or 0
    db_missing_bio_source = (await db.execute(
        select(func.count(Candidate.id)).where(
            Candidate.election_id == election.id,
            Candidate.biography_source.is_(None),
        )
    )).scalar() or 0

    candidate_mismatch_pct = (
        abs(db_candidates - source_candidates) / source_candidates * 100.0
        if source_candidates
        else 0.0
    )
    return {
        "year": year_bs,
        "source": {
            "constituencies": source_constituencies,
            "candidates": source_candidates,
            "winners": source_winners,
            "total_votes": source_total_votes,
            "missing_biography_source": source_missing_bio_source,
        },
        "db": {
            "constituencies": db_constituencies,
            "candidates": db_candidates,
            "winners": db_winners,
            "total_votes": db_total_votes,
            "missing_biography_source": db_missing_bio_source,
        },
        "candidate_mismatch_pct": round(candidate_mismatch_pct, 3),
        "has_schema_error": any(
            [
                source_constituencies == 0,
                source_candidates == 0,
                db_constituencies == 0,
                db_candidates == 0,
            ]
        ),
    }


@click.command()
@click.option("--years", default=None, help="Comma-separated BS years to import (e.g., 2079,2082)")
@click.option("--clear", is_flag=True, help="Clear existing data before import")
@click.option("--replace-existing/--skip-existing", default=True, help="Replace year data when it already exists")
@click.option("--link-entities/--no-link-entities", default=True, help="Run entity linker after import")
@click.option("--reapply-overrides/--no-reapply-overrides", default=True, help="Rebuild approved override projection")
@click.option("--reconcile/--no-reconcile", default=True, help="Compare DB snapshot vs source JSON after import")
@click.option("--all", "import_all", is_flag=True, help="Import all available years")
def main(
    years: Optional[str],
    clear: bool,
    replace_existing: bool,
    link_entities: bool,
    reapply_overrides: bool,
    reconcile: bool,
    import_all: bool,
):
    """Import election data from JSON files into PostgreSQL."""

    async def run():
        db = await get_db_session()
        sync_run: Optional[ElectionSyncRun] = None

        try:
            if clear and not years:
                print("Clearing all existing election data...")
                await clear_election_data(db)

            # Determine which years to import
            if years:
                year_list = [int(y.strip()) for y in years.split(",")]
            elif import_all:
                year_list = [2074, 2079, 2082]
            else:
                # Default: import all available
                year_list = [2074, 2079, 2082]

            print(f"Importing election data for years: {year_list}")
            sync_run = ElectionSyncRun(
                run_type="manual_replay",
                status="running",
                years=year_list,
                started_at=datetime.now(timezone.utc),
            )
            db.add(sync_run)
            await db.commit()
            await db.refresh(sync_run)

            success_count = 0
            for year_bs in year_list:
                try:
                    if await import_election_year(db, year_bs, replace_existing=replace_existing):
                        success_count += 1
                except Exception as e:
                    print(f"  Error importing {year_bs}: {e}")

            print(f"\nImport complete: {success_count}/{len(year_list)} elections imported successfully")
            import_summary = {
                "success_count": success_count,
                "total_requested": len(year_list),
                "replace_existing": replace_existing,
            }
            link_stats = None
            override_stats = None
            reports = None

            if link_entities:
                print("\nRunning entity linker...")
                link_stats = await link_all_entities(db)
                print(f"  Entity linker stats: {link_stats}")

            if reapply_overrides:
                print("\nRebuilding candidate override projection...")
                override_stats = await CandidateProfileResolver(db).rebuild_projection_from_corrections()
                await db.commit()
                print(f"  Override projection stats: {override_stats}")

            if reconcile:
                print("\nRunning reconciliation (DB snapshot vs source JSON)...")
                reports = []
                for year_bs in year_list:
                    report = await reconcile_year(db, year_bs)
                    reports.append(report)
                    print(f"  {year_bs}: {report}")

                schema_errors = sum(1 for r in reports if r.get("has_schema_error"))
                high_candidate_mismatch = [
                    r for r in reports
                    if (r.get("candidate_mismatch_pct") or 0) > 1.0
                ]
                if schema_errors > 0:
                    print(f"  ALERT: {schema_errors} reconciliation schema errors detected")
                if high_candidate_mismatch:
                    years_bad = [str(r["year"]) for r in high_candidate_mismatch]
                    print(f"  ALERT: candidate mismatch >1% for years: {', '.join(years_bad)}")

            if sync_run:
                sync_run.status = "success"
                sync_run.import_summary = import_summary
                sync_run.link_stats = link_stats
                sync_run.override_stats = override_stats
                sync_run.reconciliation = reports
                sync_run.finished_at = datetime.now(timezone.utc)
                await db.commit()

        except Exception as e:
            if sync_run:
                sync_run.status = "failed"
                sync_run.error_message = str(e)
                sync_run.finished_at = datetime.now(timezone.utc)
                await db.commit()
            raise

        finally:
            await db.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
