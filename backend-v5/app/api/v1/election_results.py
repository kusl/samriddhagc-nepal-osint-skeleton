"""API endpoints for live election results from ECN."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Query, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.data.pr_elected_members_2082 import (
    PR_ELECTED_MEMBERS_2082,
    PR_ELECTED_SOURCE_URL,
)
from app.models.election_result import ElectionCandidate, ElectionPartySummary, ElectionScrapeLog
from app.repositories.parliament import MPPerformanceRepository
from app.schemas.election import ParliamentRecordSummary
from app.services.election_service import ElectionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/election-results", tags=["election-results"])

# Cache for the live snapshot (rebuilt every 30s)
_snapshot_cache: dict | None = None
_snapshot_cache_ts: float = 0
SNAPSHOT_TTL = 30  # seconds


def _build_public_parliament_summary(mp) -> ParliamentRecordSummary:
    """Convert MPPerformance row into the public summary shape used by election endpoints."""
    return ParliamentRecordSummary(
        id=str(mp.id),
        name_en=mp.name_en,
        name_ne=mp.name_ne,
        party=mp.party,
        chamber=mp.chamber,
        performance_score=mp.performance_score,
        performance_percentile=mp.performance_percentile,
        performance_tier=mp.performance_tier,
        legislative_score=mp.legislative_score,
        legislative_percentile=mp.legislative_percentile,
        participation_score=mp.participation_score,
        participation_percentile=mp.participation_percentile,
        accountability_score=mp.accountability_score,
        accountability_percentile=mp.accountability_percentile,
        committee_score=mp.committee_score,
        committee_percentile=mp.committee_percentile,
        bills_introduced=mp.bills_introduced,
        bills_passed=mp.bills_passed,
        session_attendance_pct=mp.session_attendance_pct,
        questions_asked=mp.questions_asked,
        committee_memberships=mp.committee_memberships,
        committee_leadership_roles=mp.committee_leadership_roles,
        speeches_count=getattr(mp, "speeches_count", 0) or 0,
        peer_group=mp.peer_group,
        peer_rank=mp.peer_rank,
        peer_total=mp.peer_total,
        is_former_pm=getattr(mp, "is_former_pm", False) or False,
        pm_terms=getattr(mp, "pm_terms", 0) or 0,
        notable_roles=getattr(mp, "notable_roles", None),
    )


def _build_synthetic_inaugural_summary(candidate) -> ParliamentRecordSummary:
    """Fallback summary for current-term winners missing a parliament row.

    This keeps public profiles usable at the start of a term: everyone is
    treated as having attended the inaugural swearing-in session, while all
    substantive parliamentary activity fields remain at zero until scraped.
    """
    return ParliamentRecordSummary(
        id=f"synthetic-{candidate.id}",
        name_en=candidate.name_en_roman or candidate.name_en,
        name_ne=candidate.name_ne,
        party=candidate.party,
        chamber="hor",
        performance_score=0.0,
        performance_percentile=None,
        performance_tier=None,
        legislative_score=0.0,
        legislative_percentile=None,
        participation_score=100.0,
        participation_percentile=None,
        accountability_score=0.0,
        accountability_percentile=None,
        committee_score=0.0,
        committee_percentile=None,
        bills_introduced=0,
        bills_passed=0,
        session_attendance_pct=100.0,
        questions_asked=0,
        committee_memberships=0,
        committee_leadership_roles=0,
        speeches_count=0,
        peer_group=None,
        peer_rank=None,
        peer_total=None,
        is_former_pm=False,
        pm_terms=0,
        notable_roles=None,
    )


@router.get("/summary")
async def get_election_summary(db: AsyncSession = Depends(get_db)):
    """Top-level summary: total seats, counted, party standings."""
    # Party summary for HOR (national)
    result = await db.execute(
        select(ElectionPartySummary)
        .where(ElectionPartySummary.election_type == "hor")
        .where(ElectionPartySummary.state_id.is_(None))
        .order_by(desc(ElectionPartySummary.seats_won + ElectionPartySummary.seats_leading))
    )
    parties = result.scalars().all()

    # Count constituencies with results
    counted = await db.execute(
        select(func.count(func.distinct(
            func.concat(ElectionCandidate.district_cd, "-", ElectionCandidate.constituency_no)
        ))).where(
            ElectionCandidate.election_type == "hor",
            ElectionCandidate.total_vote_received > 0,
        )
    )
    constituencies_counted = counted.scalar() or 0

    total_constituencies = await db.execute(
        select(func.count(func.distinct(
            func.concat(ElectionCandidate.district_cd, "-", ElectionCandidate.constituency_no)
        ))).where(ElectionCandidate.election_type == "hor")
    )
    total = min(total_constituencies.scalar() or 165, 165)  # HOR has exactly 165 FPTP seats

    # Last scrape time
    last_scrape = await db.execute(
        select(ElectionScrapeLog)
        .where(ElectionScrapeLog.error.is_(None))
        .order_by(desc(ElectionScrapeLog.finished_at))
        .limit(1)
    )
    scrape = last_scrape.scalar_one_or_none()

    return {
        "total_seats": 165,
        "total_constituencies": total,
        "constituencies_counted": constituencies_counted,
        "last_updated": scrape.finished_at.isoformat() if scrape and scrape.finished_at else None,
        "parties": [
            {
                "party_name": p.party_name,
                "seats_won": p.seats_won,
                "seats_leading": p.seats_leading,
                "total": p.seats_won + p.seats_leading,
                "total_votes": p.total_votes,
            }
            for p in parties
        ],
    }


@router.get("/parties")
async def get_party_results(
    election_type: str = Query("hor", pattern="^(hor|pa)$"),
    state_id: Optional[int] = Query(None, ge=1, le=7),
    db: AsyncSession = Depends(get_db),
):
    """Party-wise seat counts."""
    query = select(ElectionPartySummary).where(
        ElectionPartySummary.election_type == election_type
    )

    if state_id:
        query = query.where(ElectionPartySummary.state_id == state_id)
    elif election_type == "hor":
        query = query.where(ElectionPartySummary.state_id.is_(None))

    query = query.order_by(
        desc(ElectionPartySummary.seats_won + ElectionPartySummary.seats_leading)
    )

    result = await db.execute(query)
    parties = result.scalars().all()

    return [
        {
            "party_name": p.party_name,
            "party_id": p.party_id,
            "seats_won": p.seats_won,
            "seats_leading": p.seats_leading,
            "total": p.seats_won + p.seats_leading,
            "total_votes": p.total_votes,
        }
        for p in parties
    ]


@router.get("/constituency/{district_cd}/{constituency_no}")
async def get_constituency_results(
    district_cd: int,
    constituency_no: int,
    election_type: str = Query("hor", pattern="^(hor|pa)$"),
    db: AsyncSession = Depends(get_db),
):
    """Candidate-level results for a specific constituency."""
    result = await db.execute(
        select(ElectionCandidate)
        .where(
            ElectionCandidate.district_cd == district_cd,
            ElectionCandidate.constituency_no == constituency_no,
            ElectionCandidate.election_type == election_type,
        )
        .order_by(desc(ElectionCandidate.total_vote_received))
    )
    candidates = result.scalars().all()

    if not candidates:
        return {"candidates": [], "meta": None}

    first = candidates[0]
    return {
        "meta": {
            "district_cd": district_cd,
            "district_name": first.district_name,
            "constituency_no": constituency_no,
            "state_id": first.state_id,
            "state_name": first.state_name,
            "total_voters": first.total_voters,
            "casted_vote": first.casted_vote,
            "turnout_pct": round(first.casted_vote / first.total_voters * 100, 1)
            if first.total_voters > 0 else 0,
        },
        "candidates": [
            {
                "candidate_name": c.candidate_name,
                "party_name": c.party_name,
                "symbol_name": c.symbol_name,
                "gender": c.gender,
                "age": c.age,
                "total_vote_received": c.total_vote_received,
                "rank": c.rank,
                "is_winner": c.is_winner,
                "vote_share_pct": round(c.total_vote_received / first.casted_vote * 100, 1)
                if first.casted_vote > 0 else 0,
            }
            for c in candidates
        ],
    }


@router.get("/by-state/{state_id}")
async def get_state_results(
    state_id: int,
    db: AsyncSession = Depends(get_db),
):
    """All constituency results for a province, showing leading candidates."""
    # Get all candidates ranked #1 in each constituency
    subq = (
        select(
            ElectionCandidate.district_cd,
            ElectionCandidate.constituency_no,
            func.max(ElectionCandidate.total_vote_received).label("max_votes"),
        )
        .where(
            ElectionCandidate.state_id == state_id,
            ElectionCandidate.election_type == "hor",
        )
        .group_by(ElectionCandidate.district_cd, ElectionCandidate.constituency_no)
        .subquery()
    )

    result = await db.execute(
        select(ElectionCandidate)
        .join(
            subq,
            (ElectionCandidate.district_cd == subq.c.district_cd)
            & (ElectionCandidate.constituency_no == subq.c.constituency_no)
            & (ElectionCandidate.total_vote_received == subq.c.max_votes),
        )
        .where(ElectionCandidate.state_id == state_id)
        .order_by(ElectionCandidate.district_cd, ElectionCandidate.constituency_no)
    )
    leaders = result.scalars().all()

    return [
        {
            "district_cd": c.district_cd,
            "district_name": c.district_name,
            "constituency_no": c.constituency_no,
            "leading_candidate": c.candidate_name,
            "leading_party": c.party_name,
            "votes": c.total_vote_received,
            "is_winner": c.is_winner,
            "total_voters": c.total_voters,
            "casted_vote": c.casted_vote,
        }
        for c in leaders
    ]


@router.get("/scrape-status")
async def get_scrape_status(db: AsyncSession = Depends(get_db)):
    """Check last scrape run status."""
    result = await db.execute(
        select(ElectionScrapeLog)
        .order_by(desc(ElectionScrapeLog.started_at))
        .limit(5)
    )
    logs = result.scalars().all()

    return [
        {
            "started_at": l.started_at.isoformat() if l.started_at else None,
            "finished_at": l.finished_at.isoformat() if l.finished_at else None,
            "constituencies_scraped": l.constituencies_scraped,
            "candidates_updated": l.candidates_updated,
            "error": l.error,
        }
        for l in logs
    ]


# ── Static JSON base (loaded once) ──────────────────────────────────
_static_base: dict | None = None

def _load_static_base() -> dict:
    """Load the static election-results-2082.json as the base template."""
    global _static_base
    if _static_base is not None:
        return _static_base

    # Try multiple paths (Docker vs local dev)
    candidates = [
        Path("/app/static/election-results-2082.json"),
        Path(__file__).resolve().parents[3] / "static" / "election-results-2082.json",
    ]
    for p in candidates:
        if p.exists():
            with open(p) as f:
                _static_base = json.load(f)
            logger.info("Loaded static election base from %s (%d results)", p, len(_static_base.get("results", [])))
            return _static_base

    raise FileNotFoundError(f"election-results-2082.json not found in {[str(c) for c in candidates]}")


@router.get("/live-snapshot")
async def get_live_snapshot(db: AsyncSession = Depends(get_db)):
    """Full election data with live vote counts overlaid on static candidate data.

    Returns the same format as election-results-2082.json so the frontend
    ElectionMapWidget can consume it directly.
    """
    global _snapshot_cache, _snapshot_cache_ts

    now = time.monotonic()
    if _snapshot_cache and (now - _snapshot_cache_ts) < SNAPSHOT_TTL:
        return _snapshot_cache

    base = _load_static_base()

    # Fetch all live vote data keyed by ecn_candidate_id
    result = await db.execute(select(ElectionCandidate).where(ElectionCandidate.election_type == "hor"))
    live_rows = result.scalars().all()

    live_by_id: dict[int, ElectionCandidate] = {}
    for row in live_rows:
        live_by_id[row.ecn_candidate_id] = row

    # Fetch party summary
    party_result = await db.execute(
        select(ElectionPartySummary)
        .where(ElectionPartySummary.election_type == "hor", ElectionPartySummary.state_id.is_(None))
        .order_by(desc(ElectionPartySummary.seats_won + ElectionPartySummary.seats_leading))
    )
    party_rows = party_result.scalars().all()

    # Build updated results
    updated_results = []
    total_declared = 0
    total_counting = 0
    total_votes_cast = 0
    leading_party_seats: dict[str, int] = {}
    won_party_seats: dict[str, int] = {}

    for const in base.get("results", []):
        candidates_out = []
        const_total_votes = 0
        const_casted = 0
        has_votes = False
        winner_party = None
        winner_name = None
        winner_votes = None
        const_last_updated = None

        for cand in const.get("candidates", []):
            cand_id = int(cand["id"]) if cand.get("id") else None
            live = live_by_id.get(cand_id) if cand_id else None

            # Track latest update time across all candidates in this constituency
            if live and live.last_updated:
                if const_last_updated is None or live.last_updated > const_last_updated:
                    const_last_updated = live.last_updated

            votes = live.total_vote_received if live else 0
            is_winner = (live.remarks in ("Winner", "Elected")) if live and live.remarks else False
            if not is_winner and live and live.is_winner:
                is_winner = True

            cand_out = {**cand, "votes": votes, "is_winner": is_winner}
            if live and live.casted_vote:
                cand_out["vote_pct"] = round(votes / live.casted_vote * 100, 1) if live.casted_vote > 0 else 0
                const_casted = max(const_casted, live.casted_vote)
            else:
                cand_out["vote_pct"] = 0

            if votes > 0:
                has_votes = True
            const_total_votes += votes

            if is_winner:
                winner_party = cand.get("party")
                winner_name = cand.get("name_en")
                winner_votes = votes
                if winner_party:
                    won_party_seats[winner_party] = won_party_seats.get(winner_party, 0) + 1

            candidates_out.append(cand_out)

        # Sort by votes descending
        candidates_out.sort(key=lambda c: c.get("votes", 0), reverse=True)

        # Determine status
        if winner_party:
            status = "declared"
            total_declared += 1
        elif has_votes:
            status = "counting"
            total_counting += 1
        else:
            status = "pending"

        # Track leading party
        if has_votes and candidates_out:
            lead_party = candidates_out[0].get("party", "")
            if lead_party:
                leading_party_seats[lead_party] = leading_party_seats.get(lead_party, 0) + 1

        total_votes_cast += const_total_votes

        turnout_pct = None
        if const_casted > 0 and const.get("candidates"):
            first_live = live_by_id.get(int(const["candidates"][0]["id"])) if const["candidates"][0].get("id") else None
            if first_live and first_live.total_voters > 0:
                turnout_pct = round(first_live.casted_vote / first_live.total_voters * 100, 1)

        updated_results.append({
            "constituency_id": const["constituency_id"],
            "name_en": const["name_en"],
            "name_ne": const.get("name_ne", ""),
            "district": const["district"],
            "province": const["province"],
            "province_id": const.get("province_id", 0),
            "status": status,
            "winner_party": winner_party,
            "winner_name": winner_name,
            "winner_votes": winner_votes,
            "total_votes": const_total_votes,
            "turnout_pct": turnout_pct,
            "last_updated": const_last_updated.isoformat() if const_last_updated else None,
            "candidates": candidates_out,
        })

    # Build leading party info
    top_party = max(leading_party_seats, key=leading_party_seats.get, default=None) if leading_party_seats else None

    # Build party seats: prefer computed leading_party_seats (always fresh)
    # over DB summary which may lag behind vote ingestion
    if leading_party_seats:
        party_seats_list = [
            {"party": party, "seats": count, "won": won_party_seats.get(party, 0), "leading": count - won_party_seats.get(party, 0)}
            for party, count in sorted(leading_party_seats.items(), key=lambda x: -x[1])
        ]
    else:
        party_seats_list = []
        for p in party_rows:
            party_seats_list.append({
                "party": p.party_name,
                "seats": p.seats_won + p.seats_leading,
                "won": p.seats_won,
                "leading": p.seats_leading,
            })

    total_pending = len(updated_results) - total_declared - total_counting

    snapshot = {
        "election_year": 2082,
        "total_constituencies": len(updated_results),
        "results": updated_results,
        "national_summary": {
            "total_constituencies": len(updated_results),
            "declared": total_declared,
            "counting": total_counting,
            "pending": total_pending,
            "turnout_pct": None,
            "total_votes_cast": total_votes_cast,
            "total_registered_voters": None,
            "leading_party": top_party,
            "leading_party_seats": leading_party_seats.get(top_party, 0) if top_party else 0,
            "party_seats": party_seats_list,
        },
    }

    _snapshot_cache = snapshot
    _snapshot_cache_ts = now
    logger.info("Built live snapshot: %d declared, %d counting, %d pending", total_declared, total_counting, total_pending)
    return snapshot


# ── Election Ticker Breaking News (AI agent → frontend ticker) ──────────────

# In-memory store for AI-extracted breaking election alerts (max 50, TTL 30 min)
_ticker_breaking: list[dict] = []
_TICKER_MAX = 50
_TICKER_TTL = 1800  # 30 minutes


class TickerAlert(BaseModel):
    """A single breaking election alert from the AI agent."""
    id: str
    type: str  # 'elected' | 'leading' | 'breaking' | 'update'
    headline: str
    source: str = "ai-agent"  # 'ai-agent', 'journalist', etc.
    confidence: float = 0.8


class TickerIngestRequest(BaseModel):
    """Batch of breaking alerts from the local AI agent."""
    alerts: list[TickerAlert]


@router.post("/ticker/ingest")
async def ingest_ticker_alerts(
    payload: TickerIngestRequest,
    user=Depends(get_current_user),
):
    """Ingest AI-extracted breaking election alerts for the ticker.

    Called by the local Sonnet agent every 5 minutes.
    """
    global _ticker_breaking

    now = time.time()
    # Remove expired alerts
    _ticker_breaking = [a for a in _ticker_breaking if (now - a.get("_ts", 0)) < _TICKER_TTL]

    seen_ids = {a["id"] for a in _ticker_breaking}
    added = 0
    for alert in payload.alerts:
        if alert.id in seen_ids:
            continue
        _ticker_breaking.append({
            "id": alert.id,
            "type": alert.type,
            "headline": alert.headline,
            "source": alert.source,
            "confidence": alert.confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "_ts": now,
        })
        seen_ids.add(alert.id)
        added += 1

    # Cap size
    if len(_ticker_breaking) > _TICKER_MAX:
        _ticker_breaking = _ticker_breaking[-_TICKER_MAX:]

    logger.info(f"Ticker ingest: {added} new alerts ({len(_ticker_breaking)} total)")
    return {"added": added, "total": len(_ticker_breaking)}


@router.get("/ticker/breaking")
async def get_ticker_breaking():
    """Get AI-extracted breaking election alerts for the ticker."""
    now = time.time()
    active = [
        {k: v for k, v in a.items() if k != "_ts"}
        for a in _ticker_breaking
        if (now - a.get("_ts", 0)) < _TICKER_TTL
    ]
    return active


# ── Ekantipur ingest endpoint (called by local scraper) ──────────────

class EkantipurCandidate(BaseModel):
    ecn_candidate_id: int
    vote_count: int
    is_win: bool = False
    is_lead: bool = False

class EkantipurIngestPayload(BaseModel):
    candidates: list[EkantipurCandidate]
    source: str = "ekantipur"


@router.post("/ingest-votes")
async def ingest_votes(
    payload: EkantipurIngestPayload,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Ingest vote counts from local ekantipur scraper.

    Accepts a list of {ecn_candidate_id, vote_count, is_win, is_lead}.
    Only updates if incoming vote_count > existing (no data loss).
    """
    global _snapshot_cache, _snapshot_cache_ts

    now = datetime.now(timezone.utc)
    updated = 0
    skipped = 0

    for c in payload.candidates:
        if c.vote_count <= 0:
            continue

        result = await db.execute(
            select(ElectionCandidate).where(
                ElectionCandidate.ecn_candidate_id == c.ecn_candidate_id
            )
        )
        row = result.scalar_one_or_none()

        if not row:
            skipped += 1
            continue

        changed = False
        if c.vote_count > (row.total_vote_received or 0):
            row.total_vote_received = c.vote_count
            row.last_updated = now
            changed = True
        if c.is_win and not row.is_winner:
            row.is_winner = True
            row.last_updated = now
            changed = True
        if changed:
            updated += 1

    if updated > 0:
        await db.commit()
        # Invalidate snapshot cache
        _snapshot_cache = None
        _snapshot_cache_ts = 0
        # Flush Redis response cache for election endpoints
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if redis:
                keys = await redis.keys("rcache:*")
                if keys:
                    await redis.delete(*keys)
                    logger.info("Flushed %d Redis cache keys after vote ingest", len(keys))
        except Exception as e:
            logger.warning("Redis cache flush failed: %s", e)

    logger.info("Ingest from %s: %d updated, %d skipped", payload.source, updated, skipped)
    return {"updated": updated, "skipped": skipped, "source": payload.source}


class NameBasedCandidate(BaseModel):
    candidate_name: str
    party_name: str
    district_name: str
    constituency_no: int
    vote_count: int
    is_win: bool = False
    is_lead: bool = False

class NameBasedIngestPayload(BaseModel):
    candidates: list[NameBasedCandidate]
    source: str = "ekantipur"


@router.post("/ingest-by-name")
async def ingest_by_name(
    payload: NameBasedIngestPayload,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """Ingest vote counts by matching candidate name + party + district + constituency.

    For sources like ekantipur that don't have ECN candidate IDs.
    Only updates if incoming vote_count > existing (no data loss).
    """
    global _snapshot_cache, _snapshot_cache_ts

    now = datetime.now(timezone.utc)
    updated = 0
    skipped = 0
    not_found = 0

    for c in payload.candidates:
        if c.vote_count <= 0:
            continue

        # Match by name + party + constituency
        result = await db.execute(
            select(ElectionCandidate).where(
                func.lower(ElectionCandidate.candidate_name) == c.candidate_name.lower().strip(),
                func.lower(ElectionCandidate.party_name) == c.party_name.lower().strip(),
                ElectionCandidate.constituency_no == c.constituency_no,
                ElectionCandidate.election_type == "hor",
            ).limit(1)
        )
        row = result.scalar_one_or_none()

        if not row:
            # Try fuzzy: just name + constituency (party names differ between sources)
            result = await db.execute(
                select(ElectionCandidate).where(
                    func.lower(ElectionCandidate.candidate_name) == c.candidate_name.lower().strip(),
                    ElectionCandidate.constituency_no == c.constituency_no,
                    ElectionCandidate.election_type == "hor",
                ).limit(1)
            )
            row = result.scalar_one_or_none()

        if not row:
            not_found += 1
            continue

        if c.vote_count > (row.total_vote_received or 0):
            row.total_vote_received = c.vote_count
            row.is_winner = c.is_win
            row.last_updated = now
            updated += 1
        else:
            skipped += 1

    if updated > 0:
        await db.commit()
        _snapshot_cache = None
        _snapshot_cache_ts = 0
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            if redis:
                keys = await redis.keys("rcache:*")
                if keys:
                    await redis.delete(*keys)
        except Exception:
            pass

    logger.info("Name-ingest from %s: %d updated, %d skipped, %d not found", payload.source, updated, skipped, not_found)
    return {"updated": updated, "skipped": skipped, "not_found": not_found, "source": payload.source}


# ── PR Votes + Seat Projection ──────────────────────────────────────

_pr_cache: dict | None = None
_pr_cache_ts: float = 0
PR_CACHE_TTL = 60  # seconds

PR_TOTAL_SEATS = 110
PR_THRESHOLD_PCT = 3.0
# Modified Sainte-Laguë divisors: 1.4, 3, 5, 7, 9, ...
SAINTE_LAGUE_FIRST = 1.4
PR_LIST_CACHE_TTL = 60 * 60 * 12  # 12 hours
PR_CLOSED_LIST_URL = "https://election.gov.np/admin/public/storage/HOR%202082/PR/PR_FINAL.pdf"

_pr_member_cache: dict | None = None
_pr_member_cache_ts: float = 0


class PRElectedMember(BaseModel):
    id: str
    name_ne: str
    name_roman: Optional[str] = None
    party: str
    party_code: Optional[str] = None
    party_en: Optional[str] = None
    district: Optional[str] = None
    list_order: int
    election_type: str = "pr"
    constituency: str = "PR - Party List"
    source_urls: list[str] = []
    derived_from_closed_list: bool = False


class HouseRepresentative(BaseModel):
    id: str
    constituency_id: str
    name: str
    name_ne: Optional[str] = None
    name_roman: Optional[str] = None
    party: str
    constituency: str
    district: str
    province: str
    votes: int = 0
    vote_pct: float = 0
    is_winner: bool = True
    photo_url: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    biography: Optional[str] = None
    biography_source: Optional[str] = None
    election_type: str


def _normalize_pr_party_name(raw: str | None) -> str | None:
    """Normalize PR party headers from the ECN rectified list PDF."""
    if not raw:
        return None

    cleaned = " ".join(raw.split()).strip().rstrip("[").strip()
    if not cleaned:
        return None

    if "मजदुर" in cleaned and ("किसान" in cleaned or "ǒकसान" in cleaned):
        return "नेपाल मजदुर किसान पार्टी"
    if "काँĒेस" in cleaned or "कांग्रेस" in cleaned or "काँग्रेस" in cleaned:
        return "नेपाली काँग्रेस"
    if "(एमाले)" in cleaned:
        return "नेपाल कम्युनिष्ट पार्टी (एकीकृत मार्क्सवादी लेनिनवादी)"
    if "माओवाद" in cleaned or "माओवादȣ" in cleaned:
        return "नेपाली कम्युनिष्ट पार्टी"
    if "èवतÛğ" in cleaned or "स्वतन्त्र" in cleaned:
        return "राष्ट्रिय स्वतन्त्र पार्टी"
    if "Įम संèकृǓत" in cleaned or "श्रम संस्कृति" in cleaned:
        return "श्रम संस्कृति पार्टी"
    if "ĤजातÛğ" in cleaned or "प्रजातन्त्र" in cleaned:
        return "राष्ट्रिय प्रजातन्त्र पार्टी"
    if ("समाजवादȣ" in cleaned or "समाजवादी" in cleaned) and "जनता" in cleaned:
        return "जनता समाजवादी पार्टी, नेपाल"
    if "जनमोचा" in cleaned or "जनमोर्चा" in cleaned:
        return "राष्ट्रिय जनमोर्चा"

    return cleaned


def _extract_pr_closed_list_rows(pdf_bytes: bytes) -> dict[str, list[dict]]:
    """Parse party-wise PR closed-list rows from ECN's final rectified PDF.

    The PDF uses legacy Nepali fonts, so candidate names are still somewhat
    garbled in direct extraction. We keep the official extracted strings for
    now and label the endpoint as ECN-derived party-list data.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PR closed-list parsing") from exc

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    members_by_party: dict[str, list[dict]] = {}
    current_party: str | None = None

    for page in doc:
        text_lines = [line.strip() for line in page.get_text("text").splitlines() if line.strip()]
        if text_lines and text_lines[0].startswith("राजनी"):
            current_party = _normalize_pr_party_name(text_lines[1] if len(text_lines) > 1 else None)

        if not current_party:
            continue

        words = page.get_text("words")
        anchors: list[float] = []
        seen_anchor_keys: set[int] = set()
        for x0, y0, x1, y1, text, *_ in words:
            if x0 < 70 and text.isdigit():
                key = int(round(y0 * 10))
                if key not in seen_anchor_keys:
                    seen_anchor_keys.add(key)
                    anchors.append(y0)

        for anchor_y in sorted(anchors):
            row_words = [w for w in words if abs(w[1] - anchor_y) < 1.2]
            order_tokens = [
                text for x0, _, _, _, text, *_ in row_words
                if 75 <= x0 < 105 and text.isdigit()
            ]
            name_tokens = [
                text for x0, _, _, _, text, *_ in sorted(row_words)
                if 95 <= x0 < 240 and not text.isdigit()
            ]
            district_tokens = [
                text for x0, _, _, _, text, *_ in sorted(row_words)
                if 790 <= x0 < 860
            ]

            if not order_tokens or not name_tokens:
                continue

            list_order = int(order_tokens[0])
            name_ne = " ".join(name_tokens).strip()
            district = " ".join(district_tokens).strip() or None
            if not name_ne:
                continue

            members_by_party.setdefault(current_party, []).append(
                {
                    "name_ne": name_ne,
                    "district": district,
                    "list_order": list_order,
                }
            )

    for party, rows in members_by_party.items():
        deduped: dict[int, dict] = {}
        for row in rows:
            deduped.setdefault(row["list_order"], row)
        members_by_party[party] = sorted(deduped.values(), key=lambda x: x["list_order"])

    doc.close()
    return members_by_party


async def _get_pr_closed_list_rows() -> dict[str, list[dict]]:
    global _pr_member_cache, _pr_member_cache_ts

    now = time.monotonic()
    if _pr_member_cache and (now - _pr_member_cache_ts) < PR_LIST_CACHE_TTL:
        return _pr_member_cache["rows"]

    async with httpx.AsyncClient(verify=False, timeout=60) as client:
        response = await client.get(PR_CLOSED_LIST_URL)
        response.raise_for_status()

    rows = _extract_pr_closed_list_rows(response.content)
    _pr_member_cache = {"rows": rows}
    _pr_member_cache_ts = now
    return rows


def _compute_pr_seats(parties: list[dict]) -> list[dict]:
    """Apply modified Sainte-Laguë method to allocate 110 PR seats.

    parties: [{"party": str, "votes": int, ...}, ...]
    Returns parties with added "pr_seats" field.
    """
    total_votes = sum(p["votes"] for p in parties)
    if total_votes == 0:
        return parties

    # Step 1: Filter by 3% threshold
    threshold = total_votes * PR_THRESHOLD_PCT / 100
    qualifying = [p for p in parties if p["votes"] >= threshold]
    non_qualifying = [p for p in parties if p["votes"] < threshold]

    for p in non_qualifying:
        p["pr_seats"] = 0
        p["qualifies"] = False

    if not qualifying:
        return parties

    for p in qualifying:
        p["qualifies"] = True
        p["pr_seats"] = 0

    # Step 2: Modified Sainte-Laguë allocation
    # Generate quotients for each qualifying party
    quotients = []
    for p in qualifying:
        # First divisor is 1.4, then 3, 5, 7, 9, ...
        # We need at most PR_TOTAL_SEATS quotients per party
        max_possible = min(PR_TOTAL_SEATS, 110)
        for seat_num in range(max_possible):
            if seat_num == 0:
                divisor = SAINTE_LAGUE_FIRST
            else:
                divisor = 2 * seat_num + 1  # 3, 5, 7, 9, ...
            quotients.append((p["votes"] / divisor, p["party"]))

    # Sort by quotient descending, take top 110
    quotients.sort(key=lambda x: -x[0])
    seat_allocation: dict[str, int] = {}
    for i in range(min(PR_TOTAL_SEATS, len(quotients))):
        party_name = quotients[i][1]
        seat_allocation[party_name] = seat_allocation.get(party_name, 0) + 1

    for p in qualifying:
        p["pr_seats"] = seat_allocation.get(p["party"], 0)

    return qualifying + non_qualifying


@router.get("/pr-votes")
async def get_pr_votes():
    """Fetch PR vote data from ECN and compute projected seat allocation."""
    import httpx

    global _pr_cache, _pr_cache_ts

    now = time.monotonic()
    if _pr_cache and (now - _pr_cache_ts) < PR_CACHE_TTL:
        return _pr_cache

    try:
        async with httpx.AsyncClient(verify=False, timeout=20) as client:
            # Init session
            r = await client.get("https://result.election.gov.np/")
            csrf = r.cookies.get("CsrfToken")
            if not csrf:
                logger.warning("PR: No CSRF token from ECN")
                if _pr_cache:
                    return _pr_cache
                return {"parties": [], "total_votes": 0, "error": "No CSRF token"}

            headers = {
                "X-CSRF-Token": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": "https://result.election.gov.np/",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            }

            r = await client.get(
                "https://result.election.gov.np/Handlers/SecureJson.ashx?file=JSONFiles/Election2082/Common/PRHoRPartyTop5.txt",
                headers=headers,
            )
            if r.status_code != 200:
                logger.warning("PR: ECN returned %d", r.status_code)
                if _pr_cache:
                    return _pr_cache
                return {"parties": [], "total_votes": 0, "error": f"ECN {r.status_code}"}

            text = r.text.strip().lstrip("\ufeff")
            data = json.loads(text)

    except Exception as e:
        logger.warning("PR fetch error: %s", e)
        if _pr_cache:
            return _pr_cache
        return {"parties": [], "total_votes": 0, "error": str(e)}

    # Build party list
    parties = []
    for entry in data:
        votes = int(entry.get("TotalVoteReceived", 0) or 0)
        parties.append({
            "party": entry.get("PoliticalPartyName", ""),
            "votes": votes,
            "symbol_id": entry.get("SymbolID"),
        })

    # Sort by votes descending
    parties.sort(key=lambda x: -x["votes"])
    total_votes = sum(p["votes"] for p in parties)

    # Add vote percentage
    for p in parties:
        p["vote_pct"] = round(p["votes"] / total_votes * 100, 2) if total_votes > 0 else 0

    # Compute seat projection
    parties = _compute_pr_seats(parties)

    result = {
        "parties": parties,
        "total_votes": total_votes,
        "total_pr_seats": PR_TOTAL_SEATS,
        "threshold_pct": PR_THRESHOLD_PCT,
        "method": "Modified Sainte-Laguë",
        "note": "Projected seats based on current vote count. Final allocation may differ.",
    }

    _pr_cache = result
    _pr_cache_ts = now
    return result


@router.get("/pr-members")
async def get_pr_members():
    """Return the official 2082 elected PR House roster.

    The ECN elected roster is published as a scanned PDF. We extracted it with
    local Tesseract OCR, cleaned the final names locally, and keep the verified
    110-member list in the app so production does not need to OCR the PDF on
    every request.
    """
    members = [
        PRElectedMember(
            id=f"pr-{row['party']}-{row['closed_list_order']}",
            name_ne=row["name_ne"],
            name_roman=row.get("name_roman"),
            party=row["party"],
            party_code=row.get("party_code"),
            party_en=row.get("party_en"),
            district="Party List",
            list_order=row["closed_list_order"],
            source_urls=[PR_ELECTED_SOURCE_URL],
            derived_from_closed_list=False,
        ).model_dump()
        for row in PR_ELECTED_MEMBERS_2082
    ]

    party_counts: dict[str, int] = {}
    for row in PR_ELECTED_MEMBERS_2082:
        party_counts[row["party"]] = party_counts.get(row["party"], 0) + 1

    parties_out = [
        {"party": party, "pr_seats": count}
        for party, count in sorted(party_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "members": members,
        "parties": parties_out,
        "total_members": len(members),
        "total_pr_seats": PR_TOTAL_SEATS,
        "method": "Official ECN elected PR PDF, OCR-extracted locally with Tesseract and manually cleaned",
        "derived": False,
        "source_urls": [PR_ELECTED_SOURCE_URL],
        "missing_parties": [],
    }


@router.get("/house-representatives")
async def get_house_representatives(db: AsyncSession = Depends(get_db)):
    """Return the full House roster: 165 FPTP winners + 110 elected PR members."""
    snapshot = await get_live_snapshot(db)
    pr_members_response = await get_pr_members()

    fptp_members: list[dict] = []
    for constituency in snapshot.get("results", []):
        for candidate in constituency.get("candidates", []):
            if not candidate.get("is_winner"):
                continue
            fptp_members.append(
                HouseRepresentative(
                    id=candidate.get("external_id") or candidate.get("id") or f"{constituency['constituency_id']}-{candidate['name_en']}",
                    constituency_id=constituency["constituency_id"],
                    name=candidate.get("name_en_roman") or candidate["name_en"],
                    name_ne=candidate.get("name_ne") or candidate.get("name_en"),
                    name_roman=candidate.get("name_en_roman"),
                    party=candidate["party"],
                    constituency=constituency["name_en"],
                    district=constituency["district"],
                    province=constituency["province"],
                    votes=int(candidate.get("votes") or 0),
                    vote_pct=float(candidate.get("vote_pct") or 0),
                    photo_url=candidate.get("photo_url"),
                    age=candidate.get("age"),
                    gender=candidate.get("gender"),
                    biography=candidate.get("biography"),
                    biography_source=candidate.get("biography_source"),
                    election_type="fptp",
                ).model_dump()
            )

    pr_members = [
        HouseRepresentative(
            id=member["id"],
            constituency_id=f"pr-{member.get('party_code') or member['party']}",
            name=member.get("name_roman") or member["name_ne"],
            name_ne=member["name_ne"],
            name_roman=member.get("name_roman"),
            party=member.get("party_code") or member["party"],
            constituency="PR - Party List",
            district=member.get("district") or "Party List",
            province="PR",
            election_type="pr",
        ).model_dump()
        for member in pr_members_response.get("members", [])
    ]

    members = sorted(
        [*fptp_members, *pr_members],
        key=lambda item: (
            item["election_type"] != "fptp",
            item["name_ne"] or item["name"],
        ),
    )

    return {
        "members": members,
        "counts": {
            "total": len(members),
            "fptp": len(fptp_members),
            "pr": len(pr_members),
        },
        "source_urls": [
            "https://nepalosint.com/api/v1/election-results/live-snapshot",
            PR_ELECTED_SOURCE_URL,
        ],
    }


@router.get("/house-representatives/{candidate_id}/parliamentary-summary", response_model=ParliamentRecordSummary)
async def get_public_parliamentary_summary_for_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the linked parliamentary summary for a public House member record.

    This is the public-safe bridge for widgets that need attendance and score data
    without depending on the authenticated `/parliament` router.
    """
    service = ElectionService(db)
    candidate = await service.candidate_repo.get_by_external_id(candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    mp_repo = MPPerformanceRepository(db)
    mp = await mp_repo.get_by_candidate_id(candidate.id)

    if not mp and candidate.name_ne:
        mps = await mp_repo.search_by_name(candidate.name_ne, limit=1)
        if mps:
            mp = mps[0]

    if not mp and candidate.name_en:
        mps = await mp_repo.search_by_name(candidate.name_en, limit=1)
        if mps:
            mp = mps[0]

    if not mp:
        return _build_synthetic_inaugural_summary(candidate)

    return _build_public_parliament_summary(mp)
