"""Reads the imaging and narrative record for a named flood event.

Sits beside OfficialTollService, which answers "how many". This answers "what
happened, and who photographed it from orbit". Both are deliberately thin: the
rows are curated at seed time with their authority attached, and nothing here
derives, ranks or summarises them.
"""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flood_event import FloodChronologyEntry, FloodImageryProduct

# Nepal runs at UTC+05:45 with no daylight saving. Timestamps come back from
# Postgres normalised to UTC, and a desk in Kathmandu needs the local clock the
# bulletins were issued on, so both are returned rather than one being guessed
# at in the browser.
NPT = timezone(timedelta(hours=5, minutes=45))

# The Charter activation is a single, closed administrative record — one id, one
# requester, one project manager — not a table's worth of rows. It is stated
# here in full so the imagery endpoint can name the authority behind the Charter
# products it returns.
CHARTER_ACTIVATION = {
    "activation_id": "1052",
    "name": "Flood in Nepal — Activation 1052",
    "activated_at": "2026-08-26T14:58:00+02:00",
    "requested_by": "Asian Disaster Reduction Center (ADRC)",
    "on_behalf_of": "Department of Hydrology and Meteorology (DHM), Ministry of "
                    "Energy, Water Resources and Irrigation, Nepal",
    "project_manager": "Samir Belabbes (UNITAR)",
    "products_published": 18,
    "contributing_bodies": [
        "NRSC", "ISRO", "British Geological Survey", "SERTIT", "ICIMOD",
        "Copernicus EMS",
    ],
    "url": "https://disasterscharter.org/activations/flood-in-nepal-activation-1052-",
}

# The cite tier. Everything here is copyrighted coverage or a rights-reserved map
# product: the desk may state what it found and link to it, and may not show a
# pixel of it. That split is the whole point of the constant — the display tier
# (Vantor CC BY-NC, Commons, NASA/USGS, ESA) is served by /flood/media and
# /flood/scenes, and nothing in this list may ever be rendered as an image or
# have a thumbnail scraped for it.
#
# Verified by hand on 2026-09-01. `date` and `url` are null where the briefing
# stated none: an undated row renders without a date rather than with a guessed
# one, and a row without a link renders as text rather than behind a fabricated
# anchor. This is an editorial record, not scraped, and it does not change
# without a person changing it.
CITE_TIER_NOTE = ("Reported findings from copyrighted coverage. Cited and linked "
                  "only — no images, no rehosting, no thumbnail scraping.")

CITED_REPORTING: list[dict[str, Any]] = [
    {
        "display_order": 5,
        "outlet": "Copernicus Emergency Management Service",
        "headline": "EMSR927 Rapid Mapping activation, four Areas of Interest, "
                    "Rasuwa and Nuwakot",
        "date": "2026-08-26",
        "finding": "Damage grading over Syapru Besi from WorldView-3 imagery "
                   "acquired 27 Aug 2026 05:05 UTC counts more than 240 "
                   "buildings destroyed and 32 damaged.",
        "url": "https://mapping.emergency.copernicus.eu/activations/EMSR927/",
        "theme": "imagery",
        "rights": "EMS map products are published all rights reserved — cited "
                  "and linked, never rehosted.",
    },
    {
        "display_order": 6,
        "outlet": "UNOSAT / UNITAR",
        "headline": "Satellite-detected mudflow and rockflow extent, Rasuwa, "
                    "26–27 Aug 2026, and impact assessment maps for Rasuwa and "
                    "Nuwakot",
        "date": None,
        "finding": "Mapped the mudflow and rockflow extent of 26–27 August and "
                   "published district-level impact assessments for Rasuwa and "
                   "Nuwakot.",
        "url": "http://www.unitar.org/unosat/maps/NPL",
        "theme": "imagery",
    },
    {
        "display_order": 10,
        "outlet": "Al Jazeera",
        "headline": "Satellite images show destruction from Nepal-Tibet floods",
        "date": "2026-08-27",
        "finding": "Rasuwagadhi and Gyirong Port were scoured to bedrock; April "
                   "2024 imagery showed large buildings and a basketball court "
                   "on the same site.",
        "url": "https://www.aljazeera.com/news/2026/8/27/satellite-images-show-"
               "destruction-from-nepal-tibet-floods",
        "theme": "imagery",
    },
    {
        "display_order": 20,
        "outlet": "ABC News",
        "headline": "Images from before and after deadly Nepal-Tibet floods show "
                    "settlements wiped off map",
        "date": "2026-08-28",
        "finding": "Before and after imagery shows settlements wiped off the map.",
        "url": "https://www.abc.net.au/news/2026-08-28/nepal-tibet-floods-"
               "satellite-imagery-shows-destruction/107088372",
        "theme": "imagery",
    },
    {
        "display_order": 30,
        "outlet": "Bloomberg",
        "headline": "Satellite Images Show How Nepal Floods Damaged Homes, Power "
                    "Plants, Bridges",
        "date": None,
        "finding": "Satellite images show damage to homes, power plants and bridges.",
        "url": "https://www.bloomberg.com/graphics/2026-nepal-flash-flood/",
        "theme": "imagery",
    },
    {
        "display_order": 40,
        "outlet": "phys.org",
        "headline": "Satellite images show bedrock and glacier collapsed on "
                    "Nepal-China border",
        "date": None,
        "finding": "The bedrock beneath the glacier failed, reclassifying the "
                   "event from an ice avalanche.",
        "url": "https://phys.org/news/2026-08-satellite-images-bedrock-glacier-"
               "collapsed.html",
        "theme": "imagery",
    },
    {
        "display_order": 50,
        "outlet": "ESA",
        "headline": "Nepal flash flood imaged by satellites",
        "date": None,
        "finding": "A Sentinel-2 pair, 12 August against 27 August, images the flood.",
        "url": "https://www.esa.int/Applications/Observing_the_Earth/Copernicus/"
               "Sentinel-2/Nepal_flash_flood_imaged_by_satellites",
        "theme": "imagery",
    },
    {
        "display_order": 60,
        "outlet": "ArcGIS StoryMaps",
        "headline": "August 2026 Nepal Trishuli Flood",
        "date": None,
        "finding": "A narrative map of the flood along the Trishuli corridor.",
        "url": "https://storymaps.arcgis.com/stories/"
               "f2b2425eac544929a7d18f4c90b41d66",
        "theme": "imagery",
    },
    {
        "display_order": 70,
        "outlet": "AP",
        "headline": "Mass burials in Nepal as death toll from flash floods "
                    "exceeds 1,000",
        "date": None,
        "finding": "Mass burials under way as the flash-flood death toll exceeds 1,000.",
        "url": None,
        "theme": "toll",
    },
    {
        "display_order": 80,
        "outlet": "The New York Times",
        "headline": "Death Toll in Nepal Floods Tops 1,000: What to Know",
        "date": "2026-09-01",
        "finding": "The death toll in the Nepal floods tops 1,000.",
        "url": None,
        "theme": "toll",
    },
    {
        "display_order": 90,
        "outlet": "UN News",
        "headline": "Nepal floods: Mounting death toll and concern for women and girls",
        "date": "2026-08-31",
        "finding": "OCHA put the toll past 900 with more than 4,200 missing, and named "
                   "access as the single biggest obstacle to the response: 65,000 "
                   "needed emergency water and sanitation, 22,000 children needed "
                   "protection services, and 107 children were potentially separated "
                   "from their caregivers.",
        "url": "https://news.un.org/en/story/2026/08/1168233",
        "theme": "humanitarian",
    },
    {
        "display_order": 100,
        "outlet": "Ratopati",
        "headline": "35 Bridges Damaged by Flood, Nepal Seeks International Aid "
                    "for Bailey Bridges",
        "date": None,
        "finding": "35 bridges damaged; Nepal is seeking international aid for "
                   "Bailey bridges.",
        "url": None,
        "theme": "infrastructure",
    },
    {
        "display_order": 110,
        "outlet": "Ratopati",
        "headline": "Flood Damage to Water and Sanitation Infrastructure Exceeds "
                    "NPR 930 Million",
        "date": None,
        "finding": "Water and sanitation infrastructure damage exceeds NPR 930 million.",
        "url": None,
        "theme": "infrastructure",
    },
    {
        "display_order": 120,
        "outlet": "Ratopati",
        "headline": "Flood Devastates Nepal, Impacting 17,000 Children "
                    "Psychologically",
        "date": None,
        "finding": "17,000 children are reported psychologically impacted.",
        "url": None,
        "theme": "humanitarian",
    },
]


class FloodIntelService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_imagery(self, event_key: str) -> list[dict[str, Any]]:
        """Catalogued imagery products for the event, in curated order."""
        rows = (await self.db.execute(
            select(FloodImageryProduct)
            .where(FloodImageryProduct.event_key == event_key)
            .order_by(FloodImageryProduct.display_order.asc())
        )).scalars().all()

        return [
            {
                "provider": p.provider,
                "title": p.title,
                "product_type": p.product_type,
                "sensor": p.sensor,
                "area": p.area,
                # Null where the publisher did not state an acquisition date —
                # left empty rather than filled with a plausible one.
                "acquired_before": p.acquired_before.isoformat() if p.acquired_before else None,
                "acquired_after": p.acquired_after.isoformat() if p.acquired_after else None,
                "published_on": p.published_on.isoformat() if p.published_on else None,
                "description": p.description,
                "url": p.url,
                "credit": p.credit,
            }
            for p in rows
        ]

    async def get_chronology(self, event_key: str) -> list[dict[str, Any]]:
        """Narrative beats oldest first.

        display_order breaks ties within a day: several beats on 26 August share
        the only timestamp anyone published for them, and the order they are
        listed in is the order they happened.
        """
        rows = (await self.db.execute(
            select(FloodChronologyEntry)
            .where(FloodChronologyEntry.event_key == event_key)
            .order_by(FloodChronologyEntry.occurred_at.asc(),
                      FloodChronologyEntry.display_order.asc())
        )).scalars().all()

        return [
            {
                "occurred_at": e.occurred_at.isoformat(),
                "occurred_at_npt": e.occurred_at.astimezone(NPT).isoformat(),
                # False = only the date is on the record; the client must not
                # render a clock it was never given.
                "time_published": e.time_published,
                "kind": e.kind,
                "headline": e.headline,
                "detail": e.detail,
                "source": e.source,
                "source_url": e.source_url,
            }
            for e in rows
        ]
