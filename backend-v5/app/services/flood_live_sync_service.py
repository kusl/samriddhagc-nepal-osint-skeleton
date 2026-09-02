"""Mirror the official flood feeds into the desk's own tables.

The seeded figures in `scripts/seed_trishuli_2026.py` were only ever as current
as the last hand edit. This service replaces that with a ten-minute poll of the
sources the government actually publishes, while keeping every guard that made
the hand-seeded numbers trustworthy.

Three rules are load-bearing and are enforced here rather than left to callers.

**The toll only moves on a complete, coherent revision.** The district split
must add up to the published total, and the death count must not fall below the
highest we already hold for that authority. Both checks exist because this toll
counts recovered bodies: it cannot legitimately go down, and a split that does
not sum means the board was read mid-edit. Either failure logs and skips, and
the figures already stored stand.

**Filings are never merged with the toll.** The OPMCM rescue portal counts
reports the public filed — 12,677 missing-person filings against NDRRMA's 3,916
missing, because relatives file separately and found people are rarely closed.
Those figures get their own panel, their own label, and a note saying so.

**Every step is independent.** One ministry's outage must not stop the other
five feeds writing. Each step runs inside its own try/except and reports its own
outcome, so a partial sync is visible as a partial sync rather than a failure.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import flood_official_feeds as feeds
from app.ingestion.flood_sitrep_parser import (extract_pdf_text, looks_english,
                                               parse_english_sitrep,
                                               sitrep_lang,
                                               sitrep_number_from_title,
                                               sitrep_time_from_title)
from app.models.flood_event import (FloodLiveSnapshot, FloodMediaItem,
                                    FloodOfficialToll, FloodSituationPanel,
                                    FloodSitrep)
from app.models.story import Story
from app.services.flood_service import ACTIVE_EVENT_KEY

logger = logging.getLogger(__name__)

NPT = feeds.NPT
PRIMARY_AUTHORITY = "NDRRMA"

# The event began on 26 August 2026; nothing published before it belongs here.
EVENT_START = date(2026, 8, 26)

SITREP_PAGE_URL = "https://ndrrma.gov.np/np/rasuwa/situation"
NDRRMA_PRESS_PAGE = "https://ndrrma.gov.np/np"

# Downloading every sitrep on every run would pull ~25 MB from a disaster
# authority's web server every ten minutes. Three per run backfills the whole
# series within an hour and then costs nothing.
MAX_NEW_PDFS = 3
# Article pages fetched for an og:image, per run.
MAX_OG_FETCHES = 12

# Terms that make a story about this event, in both scripts. Deliberately
# narrow: this list decides which outlet's photograph appears on a disaster
# desk, and a false positive puts an unrelated picture beside a death toll.
FLOOD_TERMS = (
    "flood", "बाढी", "rasuwa", "रसुवा", "bhote", "भोटे", "trishuli", "त्रिशूली",
    "nuwakot", "नुवाकोट", "langtang", "syabru", "timure", "rasuwagadhi",
    "glacier",
)


def _fmt(value: Optional[int]) -> Optional[str]:
    """A figure as the desk prints it: thousands separated, or None."""
    return f"{value:,}" if isinstance(value, int) else None


def _rows_updated(rows: Optional[list], updates: Iterable[tuple[str, str, Any]]) -> list:
    """Apply label-prefix updates to a panel's rows, keeping the rest.

    Rows are matched case-insensitively by label prefix rather than by exact
    string, because the seeded labels carry em-dashes and NDRRMA's own wording
    drifts. Anything unmatched is kept: this service knows about four rows in
    the rescue panel and must not silently drop the hand-verified ones it does
    not know about.
    """
    result = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    for prefix, label, value in updates:
        if value is None:
            continue
        needle = prefix.lower()
        for row in result:
            if str(row.get("label", "")).lower().startswith(needle):
                row["value"] = value
                break
        else:
            result.append({"label": label, "value": value})
    return result


class FloodLiveSyncService:
    def __init__(self, db: AsyncSession, event_key: str = ACTIVE_EVENT_KEY):
        self.db = db
        self.event_key = event_key
        self.now = datetime.now(timezone.utc)
        # Feed name -> (ok, payload, error), written out in step 6.
        self._snapshots: dict[str, tuple[bool, Optional[dict], Optional[str]]] = {}

    # -- helpers ----------------------------------------------------------

    async def _panel(self, panel_key: str) -> Optional[FloodSituationPanel]:
        return (await self.db.execute(
            select(FloodSituationPanel)
            .where(FloodSituationPanel.event_key == self.event_key,
                   FloodSituationPanel.panel_key == panel_key)
        )).scalar_one_or_none()

    async def _max_deaths(self) -> Optional[int]:
        rows = (await self.db.execute(
            select(FloodOfficialToll.deaths)
            .where(FloodOfficialToll.event_key == self.event_key,
                   FloodOfficialToll.authority == PRIMARY_AUTHORITY,
                   FloodOfficialToll.deaths.is_not(None))
        )).scalars().all()
        return max(rows) if rows else None

    def _record(self, feed: str, ok: bool, payload: Optional[dict],
                error: Optional[str] = None) -> None:
        self._snapshots[feed] = (ok, payload, error)

    # -- run --------------------------------------------------------------

    async def run(self) -> dict[str, Any]:
        """One full sync. Returns a per-step result; never raises."""
        result: dict[str, Any] = {"event_key": self.event_key,
                                  "started_at": self.now.isoformat()}

        for name, step in (
            ("toll", self._step_toll),
            ("rescue_panels", self._step_rescue_panels),
            ("portal_panel", self._step_portal_panel),
            ("sitreps", self._step_sitreps),
            ("media", self._step_media),
        ):
            try:
                result[name] = await step()
            except Exception as exc:  # noqa: BLE001 — one step must not stop the rest
                logger.exception("Flood live sync step %s failed", name)
                result[name] = {"ok": False, "error": str(exc)}
                await self.db.rollback()

        try:
            result["snapshots"] = await self._step_snapshots()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Flood live sync snapshot write failed")
            result["snapshots"] = {"ok": False, "error": str(exc)}
            await self.db.rollback()

        logger.info("Flood live sync: %s", {k: v for k, v in result.items()
                                            if k not in ("event_key", "started_at")})
        return result

    # -- 1. toll ----------------------------------------------------------

    async def _step_toll(self) -> dict[str, Any]:
        """The NDRRMA situation board, guarded, into the toll series and panels."""
        kpi = await feeds.fetch_bulletin_kpi()
        if not kpi:
            self._record("bulletin_kpi", False, None, "fetch failed")
            return {"ok": False, "error": "bulletin unavailable"}

        payload = dict(kpi)
        payload["as_of_npt"] = kpi["as_of_npt"].isoformat()
        self._record("bulletin_kpi", True, payload)

        deaths = kpi.get("deaths")
        district_tolls = kpi.get("district_tolls") or {}
        as_of = kpi["as_of_npt"].date()

        if deaths is None:
            return {"ok": False, "error": "no death figure on the board"}

        if not kpi.get("parts_sum_ok"):
            logger.warning("Toll skipped: district parts (%d) do not sum to %s",
                           sum(district_tolls.values()), deaths)
            return {"ok": False, "written": False,
                    "error": "district parts do not sum to the total",
                    "parts_sum": sum(district_tolls.values()), "deaths": deaths}

        highest = await self._max_deaths()
        if highest is not None and deaths < highest:
            # This toll counts recovered bodies. A fall means a bad read, not
            # a correction, and the stored figure stands.
            logger.warning("Toll skipped: board says %d, already hold %d",
                           deaths, highest)
            return {"ok": False, "written": False,
                    "error": "death count fell below the stored maximum",
                    "deaths": deaths, "stored_max": highest}

        stamp = kpi.get("stamp") or ""
        source_title = (f"NDRRMA situation board {stamp}, via Rasuwa flood "
                        f"bulletin (compilation)").replace("  ", " ")

        toll = (await self.db.execute(
            select(FloodOfficialToll)
            .where(FloodOfficialToll.event_key == self.event_key,
                   FloodOfficialToll.as_of == as_of,
                   FloodOfficialToll.authority == PRIMARY_AUTHORITY)
        )).scalar_one_or_none()
        created = toll is None
        if toll is None:
            toll = FloodOfficialToll(event_key=self.event_key, as_of=as_of,
                                     authority=PRIMARY_AUTHORITY)
            self.db.add(toll)

        toll.deaths = deaths
        for field in ("missing", "injured", "rescued"):
            value = kpi.get(field)
            if value is not None:
                setattr(toll, field, value)
        toll.district_tolls = {name: {"bodies_recovered": count}
                               for name, count in district_tolls.items()}
        toll.source_url = kpi.get("source_url")
        toll.source_title = source_title
        toll.note = ("Transcription of NDRRMA's published situation board. "
                     "Written only when the district split sums to the "
                     "published total and the count has not fallen.")

        # The headline panels carry the same four figures the board does, and
        # are only moved by a revision that already passed both guards.
        panel_values = {
            "deaths": (_fmt(deaths), "confirmed dead"),
            "missing": (_fmt(kpi.get("missing")), "missing"),
            "rescued": (_fmt(kpi.get("rescued")), "rescued"),
            "medical": (_fmt(kpi.get("injured")), "hospitalised"),
        }
        panels_touched = []
        for panel_key, (value, _label) in panel_values.items():
            if value is None:
                continue
            panel = await self._panel(panel_key)
            if panel is None:
                continue
            panel.headline_value = value
            panel.as_of = as_of
            panel.source = source_title
            panels_touched.append(panel_key)

        # The death panel's district rows are the same split that was just
        # checked, so they move with the headline rather than drifting from it.
        deaths_panel = await self._panel("deaths")
        if deaths_panel is not None and district_tolls:
            deaths_panel.rows = _rows_updated(
                deaths_panel.rows,
                [(name, name, _fmt(count)) for name, count in district_tolls.items()],
            )

        await self.db.commit()
        return {"ok": True, "written": True, "created": created,
                "as_of": as_of.isoformat(), "deaths": deaths,
                "missing": kpi.get("missing"), "rescued": kpi.get("rescued"),
                "injured": kpi.get("injured"), "stamp": stamp,
                "districts": len(district_tolls), "panels": panels_touched}

    # -- 2. NDRRMA rescue register ---------------------------------------

    async def _step_rescue_panels(self) -> dict[str, Any]:
        """NDRRMA's own rescue counters into the rescue and operations panels."""
        stats = await feeds.fetch_ndrrma_rescue_stats()
        counts = await feeds.fetch_ndrrma_status_counts()
        self._record("ndrrma_rescue", stats is not None, stats,
                     None if stats is not None else "fetch failed")
        if counts is not None:
            self._record("ndrrma_status", True, counts)
        else:
            self._record("ndrrma_status", False, None, "fetch failed")

        advisories = await feeds.fetch_ndrrma_advisories()
        if advisories is not None:
            self._record("ndrrma_advisory", True, {"results": advisories})
        else:
            self._record("ndrrma_advisory", False, None, "fetch failed")

        if stats is None and counts is None:
            return {"ok": False, "error": "both NDRRMA rescue feeds unavailable"}

        today = datetime.now(NPT).date()
        source = "NDRRMA rescue register (live)"
        touched = []

        rescued_panel = await self._panel("rescued")
        if rescued_panel is not None:
            updates: list[tuple[str, str, Any]] = []
            if counts:
                updates += [
                    ("Named in the public registry", "Named in the public registry",
                     _fmt(counts.get("total_count"))),
                    ("— of these, Nepali", "— of these, Nepali",
                     _fmt(counts.get("nepali_count"))),
                    ("— of these, foreign", "— of these, foreign",
                     _fmt(counts.get("foreign_count"))),
                ]
            if stats:
                updates.append(("Logged in the NDRRMA rescue system",
                                "Logged in the NDRRMA rescue system",
                                _fmt(stats.get("rescued_count"))))
            if updates:
                rescued_panel.rows = _rows_updated(rescued_panel.rows, updates)
                rescued_panel.source = source
                rescued_panel.as_of = today
                touched.append("rescued")

        ops_panel = await self._panel("operations")
        if ops_panel is not None and stats:
            if stats.get("force_deployed") is not None:
                ops_panel.headline_value = _fmt(stats["force_deployed"])
            rows = [dict(r) for r in (ops_panel.rows or []) if isinstance(r, dict)]
            out_of_reach = stats.get("out_of_reach")
            if out_of_reach is not None:
                for row in rows:
                    if "out of reach" in str(row.get("label", "")).lower():
                        row["value"] = _fmt(out_of_reach)
                        break
                else:
                    rows.append({"label": "Out of reach (NDRRMA)",
                                 "value": _fmt(out_of_reach)})
            ops_panel.rows = rows
            ops_panel.source = source
            ops_panel.as_of = today
            touched.append("operations")

        await self.db.commit()
        return {"ok": True, "panels": touched,
                "registry_total": (counts or {}).get("total_count"),
                "rescued_count": (stats or {}).get("rescued_count"),
                "force_deployed": (stats or {}).get("force_deployed"),
                "out_of_reach": (stats or {}).get("out_of_reach")}

    # -- 3. OPMCM portal --------------------------------------------------

    async def _step_portal_panel(self) -> dict[str, Any]:
        """Public filings from the OPMCM portal, in a panel that says so."""
        stats = await feeds.fetch_opmcm_stats()
        if stats is None:
            self._record("opmcm_stats", False, None, "fetch failed")
            return {"ok": False, "error": "OPMCM stats unavailable"}
        self._record("opmcm_stats", True, stats)

        persons = stats.get("persons") or {}
        requests = stats.get("requests") or {}
        offers = stats.get("offers") or {}

        rows = [
            {"label": "Found filings", "value": _fmt(persons.get("found"))},
            {"label": "Open filings", "value": _fmt(persons.get("open"))},
            {"label": "Filed in last 24h", "value": _fmt(persons.get("last24h"))},
            {"label": "Children reported missing",
             "value": _fmt(persons.get("childrenMissing"))},
            {"label": "Elderly reported missing",
             "value": _fmt(persons.get("elderlyMissing"))},
            {"label": "Help requests (open/total)",
             "value": f"{_fmt(requests.get('open')) or '—'} / "
                      f"{_fmt(requests.get('total')) or '—'}"},
            {"label": "Offers of help", "value": _fmt(offers.get("total"))},
        ]
        rows = [row for row in rows if row["value"] not in (None, "— / —")]

        panel = await self._panel("portal")
        created = panel is None
        if panel is None:
            panel = FloodSituationPanel(event_key=self.event_key, panel_key="portal",
                                        display_order=55)
            self.db.add(panel)

        panel.title = "Public filings · OPMCM rescue portal"
        panel.subtitle = "Reports filed by the public — filings, not people"
        panel.headline_value = _fmt(persons.get("lost"))
        panel.headline_label = "missing-person filings"
        panel.rows = rows
        panel.note = ("One person can be filed by several relatives and a found "
                      "person is rarely closed. Never add to, or reconcile "
                      "against, the NDRRMA toll.")
        panel.source = "OPMCM rescue portal (live)"
        panel.as_of = datetime.now(NPT).date()
        panel.display_order = 55

        await self.db.commit()
        return {"ok": True, "created": created, "rows": len(rows),
                "lost_filings": persons.get("lost"),
                "found_filings": persons.get("found")}

    # -- 4. sitreps -------------------------------------------------------

    async def _step_sitreps(self) -> dict[str, Any]:
        """Upsert the publication list; extract a few new PDFs per run."""
        results = await feeds.fetch_ndrrma_sitreps()
        if results is None:
            return {"ok": False, "error": "sitrep list unavailable"}

        existing = {row.source_id: row for row in (await self.db.execute(
            select(FloodSitrep).where(FloodSitrep.event_key == self.event_key)
        )).scalars().all()}

        created = 0
        pending: list[FloodSitrep] = []
        for item in results:
            source_id = item.get("id")
            if source_id is None:
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue

            report_date = None
            try:
                report_date = date.fromisoformat(item["date"]) if item.get("date") else None
            except (TypeError, ValueError):
                report_date = None

            row = existing.get(source_id)
            if row is None:
                row = FloodSitrep(event_key=self.event_key, source_id=source_id)
                self.db.add(row)
                existing[source_id] = row
                created += 1

            row.title = title
            row.title_ne = item.get("title_ne")
            row.number = sitrep_number_from_title(title)
            row.lang = sitrep_lang(title)
            row.report_time = sitrep_time_from_title(title)
            row.report_date = report_date
            row.pdf_url = item.get("pdffile")
            row.page_url = SITREP_PAGE_URL
            row.fetched_at = self.now

            if row.extracted is None and row.pdf_url:
                pending.append(row)

        await self.db.commit()

        # English editions first: they are the only ones whose figures parse,
        # and the newest of them is what the desk actually reads.
        pending.sort(key=lambda r: (r.lang != "en",
                                    -(r.report_date or EVENT_START).toordinal(),
                                    -r.source_id))

        extracted_count = 0
        for row in pending[:MAX_NEW_PDFS]:
            data = await feeds.fetch_pdf(row.pdf_url)
            if not data:
                continue
            text = extract_pdf_text(data)
            if not text:
                continue
            # Several reports carry an English title over a Nepali document, so
            # the title's language is not enough: the extracted text has to
            # actually be Latin before its figures are read or an excerpt kept.
            if row.lang == "en" and looks_english(text):
                parsed = parse_english_sitrep(text)
                row.text_excerpt = text[:3000]
            else:
                # Nepali PDFs extract with doubled vowel signs, so the prose is
                # unreliable. The document is kept; nothing is claimed from it.
                parsed = {}
            if parsed:
                row.extracted = parsed
                extracted_count += 1
            else:
                # Marks it as attempted so the next run moves on rather than
                # re-downloading the same file forever.
                row.extracted = {}

        await self.db.commit()
        return {"ok": True, "listed": len(results), "created": created,
                "pdfs_attempted": len(pending[:MAX_NEW_PDFS]),
                "extracted": extracted_count}

    # -- 5. media ---------------------------------------------------------

    async def _upsert_media(self, source: str, source_id: str, **fields) -> bool:
        row = (await self.db.execute(
            select(FloodMediaItem).where(
                FloodMediaItem.event_key == self.event_key,
                FloodMediaItem.source == source,
                FloodMediaItem.source_id == source_id)
        )).scalar_one_or_none()
        created = row is None
        if row is None:
            row = FloodMediaItem(event_key=self.event_key, source=source,
                                 source_id=source_id)
            self.db.add(row)
        for key, value in fields.items():
            setattr(row, key, value)
        row.fetched_at = self.now
        return created

    async def _step_media(self) -> dict[str, Any]:
        """Government photographs to display, news photographs to link."""
        counts = {"opmcm_carousel": 0, "ndrrma_press": 0, "press_lead": 0}

        carousel = await feeds.fetch_opmcm_carousel()
        if carousel is None:
            logger.warning("OPMCM carousel unavailable this run")
        else:
            for item in carousel:
                if not item.get("isActive") or not item.get("imageUrl"):
                    continue
                alt_en = (item.get("altEn") or "").strip()
                # The agency is named in the caption; crediting "OPMCM" alone
                # would drop the force that took and released the photograph.
                agency = None
                if re.search(r"nepali army|nepal army", alt_en, re.I):
                    agency = "Nepali Army"
                elif re.search(r"nepal police|armed police", alt_en, re.I):
                    agency = "Nepal Police"
                credit = "OPMCM rescue portal" + (f" · {agency}" if agency else "")

                published = None
                created_at = item.get("createdAt")
                if created_at:
                    try:
                        published = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00"))
                    except (TypeError, ValueError):
                        published = None

                counts["opmcm_carousel"] += await self._upsert_media(
                    "opmcm_carousel", str(item.get("_id")),
                    kind="govt_photo",
                    title=alt_en or "Rasuwa flood rescue operation",
                    title_ne=item.get("altNe"),
                    caption=alt_en or None,
                    credit=credit,
                    outlet=None,
                    page_url="https://rescue.opmcm.gov.np/",
                    image_url=item["imageUrl"],
                    content_type=item.get("contentType"),
                    licence_tier="display",
                    published_at=published,
                    display_order=int(item.get("order") or 100),
                    is_active=True,
                )

        press = await feeds.fetch_ndrrma_press_notes(EVENT_START)
        if press is None:
            logger.warning("NDRRMA press notes unavailable this run")
        else:
            for order, item in enumerate(press):
                image = item.get("image")
                if not image:
                    continue
                published = None
                if item.get("date"):
                    try:
                        published = datetime.combine(
                            date.fromisoformat(item["date"]),
                            datetime.min.time(), tzinfo=NPT)
                    except (TypeError, ValueError):
                        published = None
                counts["ndrrma_press"] += await self._upsert_media(
                    "ndrrma_press", str(item.get("id")),
                    kind="govt_photo",
                    title=(item.get("title") or "NDRRMA press note").strip(),
                    title_ne=item.get("title_ne"),
                    caption=item.get("summary"),
                    credit="NDRRMA press note",
                    outlet=None,
                    page_url=NDRRMA_PRESS_PAGE,
                    image_url=image,
                    content_type=None,
                    licence_tier="display",
                    published_at=published,
                    display_order=200 + order,
                    is_active=True,
                )

        counts["press_lead"] = await self._press_leads()
        await self.db.commit()
        total = (await self.db.execute(
            select(FloodMediaItem.id).where(FloodMediaItem.event_key == self.event_key)
        )).scalars().all()
        return {"ok": True, "new": counts, "total_items": len(total)}

    async def _press_leads(self) -> int:
        """Photographs from news coverage, stored as link previews only.

        These are outlets' copyrighted images. Nothing here grants a right to
        reproduce them, so the row is written with `link_preview` and the page
        URL is mandatory — the desk renders a thumbnail that links back, which
        is a citation rather than a reproduction.
        """
        cutoff = self.now - timedelta(hours=72)
        stories = (await self.db.execute(
            select(Story)
            .where(Story.published_at.is_not(None), Story.published_at >= cutoff)
            .order_by(Story.published_at.desc())
            .limit(400)
        )).scalars().all()

        matched = []
        for story in stories:
            haystack = " ".join(filter(None, [
                story.title or "", story.summary or "",
                " ".join(story.districts or []) if story.districts else "",
            ])).lower()
            if any(term in haystack for term in FLOOD_TERMS):
                matched.append(story)

        created = 0
        og_fetches = 0
        for order, story in enumerate(matched):
            image = _image_from_raw(story.raw_data)
            if not image and og_fetches < MAX_OG_FETCHES:
                existing = (await self.db.execute(
                    select(FloodMediaItem.image_url).where(
                        FloodMediaItem.event_key == self.event_key,
                        FloodMediaItem.source == "press_lead",
                        FloodMediaItem.source_id == str(story.id))
                )).scalar_one_or_none()
                if existing:
                    continue
                og_fetches += 1
                image = await _og_image(story.url)
            if not image:
                continue

            created += await self._upsert_media(
                "press_lead", str(story.id),
                kind="press_lead",
                title=story.title or "",
                title_ne=None,
                caption=story.summary,
                credit=story.source_name or story.source_id,
                outlet=story.source_name or story.source_id,
                page_url=story.url,
                image_url=image,
                content_type=None,
                licence_tier="link_preview",
                published_at=story.published_at,
                display_order=500 + order,
                is_active=True,
            )
        return created

    # -- 6. snapshots -----------------------------------------------------

    async def _step_snapshots(self) -> dict[str, Any]:
        """The last good payload per feed, and whether the last poll worked."""
        written = []
        for feed, (ok, payload, error) in self._snapshots.items():
            row = (await self.db.execute(
                select(FloodLiveSnapshot).where(
                    FloodLiveSnapshot.event_key == self.event_key,
                    FloodLiveSnapshot.feed == feed)
            )).scalar_one_or_none()
            if row is None:
                row = FloodLiveSnapshot(event_key=self.event_key, feed=feed)
                self.db.add(row)
            row.ok = ok
            row.error = error
            if ok and payload is not None:
                # A failed poll leaves the previous payload in place: the desk
                # then shows stale figures flagged as stale, rather than
                # implying the response itself stopped.
                row.payload = payload
                row.fetched_at = self.now
            written.append(f"{feed}:{'ok' if ok else 'fail'}")

        await self.db.commit()
        return {"ok": True, "feeds": sorted(written)}


# ---------------------------------------------------------------------------


_IMAGE_KEYS = ("media_content", "media_thumbnail", "enclosure", "enclosures",
               "image", "image_url", "thumbnail", "og_image", "top_image")


def _image_from_raw(raw: Optional[dict]) -> Optional[str]:
    """An image URL already present in a story's stored feed entry."""
    if not isinstance(raw, dict):
        return None
    for key in _IMAGE_KEYS:
        value = raw.get(key)
        url = _first_url(value)
        if url:
            return url
    return None


def _first_url(value: Any, depth: int = 0) -> Optional[str]:
    if depth > 3:
        return None
    if isinstance(value, str):
        return value if value.startswith("http") else None
    if isinstance(value, dict):
        for key in ("url", "href", "src", "@url", "link"):
            found = _first_url(value.get(key), depth + 1)
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for entry in value:
            found = _first_url(entry, depth + 1)
            if found:
                return found
    return None


_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE)
_OG_RE_REVERSED = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.IGNORECASE)


async def _og_image(url: Optional[str]) -> Optional[str]:
    """The og:image an article page advertises, or None. Never raises."""
    if not url or not url.startswith("http"):
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True,
                                     headers={"User-Agent": feeds.USER_AGENT}) as client:
            response = await client.get(url)
            response.raise_for_status()
            head = response.text[:120_000]
    except Exception as exc:  # noqa: BLE001
        logger.debug("og:image fetch failed for %s: %s", url, exc)
        return None

    match = _OG_RE.search(head) or _OG_RE_REVERSED.search(head)
    if not match:
        return None
    found = match.group(1).strip()
    return found if found.startswith("http") else None
