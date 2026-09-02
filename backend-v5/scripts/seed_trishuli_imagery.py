#!/usr/bin/env python3
"""Seed satellite imagery products and the narrative chronology for the
26 August 2026 Trishuli glacier-collapse flood.

Companion to seed_trishuli_2026.py, which seeds the official toll. That file
records how the count moved; this one records what happened and what was
imaged, so the desk can show a toll revision next to the event that caused it.

Every row carries a source URL. Where a date is not published — the day in
April 2024 the Rasuwagadhi baseline was acquired, or the date of Planet's next
clear pass — the column is left null and the published wording is kept in the
description rather than a plausible date being invented.

Re-runnable: imagery upserts on (event_key, title), chronology on
(event_key, headline).

Sources
-------
  - International Charter Space and Major Disasters, Activation 1052
    https://disasterscharter.org/activations/flood-in-nepal-activation-1052-
  - ESA, "Nepal flash flood imaged by satellites"
    https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2/Nepal_flash_flood_imaged_by_satellites
  - Phys.org, "Satellite images show bedrock where a glacier collapsed"
    https://phys.org/news/2026-08-satellite-images-bedrock-glacier-collapsed.html
  - Al Jazeera, ABC News and Bloomberg before/after imagery analyses
  - ArcGIS StoryMap, "August 2026 Nepal Trishuli Flood"
"""
import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.flood_event import FloodChronologyEntry, FloodImageryProduct  # noqa: E402

EVENT = "trishuli-2026-08"

NPT = timezone(timedelta(hours=5, minutes=45))
CEST = timezone(timedelta(hours=2))

CHARTER = "International Charter"
CHARTER_URL = "https://disasterscharter.org/activations/flood-in-nepal-activation-1052-"
CHARTER_CREDIT = ("International Charter Space and Major Disasters, Activation 1052 · "
                  "contributions from NRSC, ISRO, British Geological Survey, SERTIT, "
                  "ICIMOD and Copernicus EMS")

ESA_URL = ("https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2/"
           "Nepal_flash_flood_imaged_by_satellites")
EMSR927_URL = "https://mapping.emergency.copernicus.eu/activations/EMSR927/"
EMS_IMAGE_URL = ("https://eu-space.europa.eu/components/earth-observation-copernicus/"
                 "image-of-the-day/copernicus-emergency-management-service-maps-"
                 "flood-damages-northern-nepal")
UNOSAT_URL = "http://www.unitar.org/unosat/maps/NPL"
VANTOR_URL = ("https://vantor-opendata.s3.amazonaws.com/events/"
              "Nepal-Flooding-Aug-2026/collection.json")
PHYS_URL = "https://phys.org/news/2026-08-satellite-images-bedrock-glacier-collapsed.html"
ALJAZEERA_URL = ("https://www.aljazeera.com/news/2026/8/27/"
                 "satellite-images-show-destruction-from-nepal-tibet-floods")
ABC_URL = ("https://www.abc.net.au/news/2026-08-28/"
           "nepal-tibet-floods-satellite-imagery-shows-destruction/107088372")
BLOOMBERG_URL = "https://www.bloomberg.com/graphics/2026-nepal-flash-flood/"
STORYMAP_URL = "https://storymaps.arcgis.com/stories/f2b2425eac544929a7d18f4c90b41d66"

# Reused for chronology rows whose authority published no standalone page of
# its own that we can cite directly.
UN_URL = "https://news.un.org/en/story/2026/08/1168233"
RELIEFWEB_URL = ("https://reliefweb.int/report/nepal/"
                 "nepal-flood-response-situation-report-1-27-august-2026")
NEPALDISASTER_URL = "https://www.nepaldisaster.com/stats"
WIKI_URL = "https://en.wikipedia.org/wiki/2026_Nepal_floods"

# --------------------------------------------------------------- imagery
IMAGERY = [
    dict(display_order=10, provider=CHARTER, product_type="pre_post",
         title="Pre and Post Satellite Images - Nuwakot District Damages",
         area="Nuwakot district", published_on=date(2026, 8, 28),
         url=CHARTER_URL, credit=CHARTER_CREDIT,
         description="Charter product pairing pre- and post-event acquisitions over "
                     "Nuwakot, the district holding the third-largest recovered death "
                     "toll and the Gerkhutar flash-flood area."),
    dict(display_order=20, provider=CHARTER, product_type="impact_map",
         title="Nepal, Timure-Syaburbensi Impact Map",
         area="Timure - Syabrubesi corridor, Rasuwa", published_on=date(2026, 8, 28),
         url=CHARTER_URL, credit=CHARTER_CREDIT,
         description="Mapped impact along the first inhabited stretch below the border. "
                     "Timure and Syabrubesi sit directly on the surge path from "
                     "Rasuwagadhi and were cut off by road for days."),
    dict(display_order=30, provider=CHARTER, product_type="pre_post",
         title="Pre and Post Satellite Images - Gerkhutar Nuwakot Flash Flood Areas",
         area="Gerkhutar, Nuwakot", published_on=date(2026, 8, 29),
         url=CHARTER_URL, credit=CHARTER_CREDIT,
         description="Second Nuwakot pairing, published three days into the activation "
                     "as further acquisitions cleared cloud."),

    dict(display_order=40, provider="ESA Copernicus", product_type="pre_post",
         title="Nepal flash flood imaged by Sentinel-2",
         sensor="Sentinel-2", area="Trishuli and Bhote Koshi valleys",
         acquired_before=date(2026, 8, 12), acquired_after=date(2026, 8, 27),
         url=ESA_URL, credit="ESA · contains modified Copernicus Sentinel data (2026)",
         description="Natural-colour pair fifteen days apart, showing the dramatic "
                     "increase in river water along the Trishuli."),
    dict(display_order=50, provider="NASA / USGS", product_type="pre_post",
         title="Landsat-9 shortwave-infrared pair, Langtang Lirung to Rasuwagadhi",
         sensor="Landsat-9", area="Langtang Lirung to Rasuwagadhi",
         acquired_before=date(2026, 8, 24), acquired_after=date(2026, 8, 26),
         url=STORYMAP_URL,
         credit="NASA / USGS Landsat-9 · compiled in the ArcGIS StoryMap "
                "'August 2026 Nepal Trishuli Flood'",
         description="The after acquisition is roughly two hours post-collapse. "
                     "Shortwave-infrared separates water and ice from cloud, which is "
                     "what makes this pair usable at all in permanently cloudy terrain "
                     "where natural colour is blind. Linked to the StoryMap that "
                     "compiles it, not to a scene archive.",
         published_on=date(2026, 8, 26)),
    dict(display_order=60, provider="Planet Labs", product_type="analysis",
         title="Planet pre-collapse pass over the Langtang Lirung glacier",
         sensor="PlanetScope", area="Langtang Lirung, Langtang National Park",
         acquired_before=date(2026, 8, 25),
         url=PHYS_URL, credit="Planet Labs PBC · reported by Phys.org",
         description="Planet imaged the glacier one day before it collapsed. The next "
                     "clear pass showed the bedrock beneath the glacier had gone, not "
                     "just the ice — the observation that reclassified this from an "
                     "ice avalanche to a bedrock failure. The date of that following "
                     "pass is not published, so it is not recorded here."),

    dict(display_order=70, provider="Al Jazeera", product_type="pre_post",
         title="Rasuwagadhi and Gyirong Port scoured to bedrock",
         area="Rasuwagadhi / Gyirong Port border crossing",
         acquired_after=date(2026, 8, 27),
         url=ALJAZEERA_URL, credit="Al Jazeera satellite imagery analysis",
         description="April 2024 imagery shows the border post with several large "
                     "buildings and a basketball court. Post-event imagery shows almost "
                     "every structure gone and the site scoured to bedrock. The exact "
                     "April 2024 acquisition date is not published."),
    dict(display_order=80, provider="ABC News", product_type="pre_post",
         title="Nepal-Tibet floods: satellite imagery shows destruction",
         area="Rasuwagadhi and the Bhote Koshi valley",
         published_on=date(2026, 8, 28),
         url=ABC_URL, credit="ABC News satellite imagery analysis",
         description="Independent before/after comparison over the same border reach, "
                     "published two days after the collapse."),
    dict(display_order=90, provider="Bloomberg", product_type="analysis",
         title="Nepal flash flood: visual investigation",
         area="Bhote Koshi to Trishuli, source to Chitwan",
         url=BLOOMBERG_URL, credit="Bloomberg graphics",
         description="Traces the surge along its full run from the border to the "
                     "downstream districts where most bodies were recovered."),
    dict(display_order=110, provider="Copernicus EMS", product_type="impact_map",
         title="EMSR927 — Rapid Mapping activation, four Areas of Interest",
         area="Rasuwa District, four AOIs",
         acquired_after=date(2026, 8, 27),
         sensor="WorldView-3",
         published_on=date(2026, 8, 28),
         url=EMSR927_URL,
         credit="European Union, Copernicus Emergency Management Service · imagery "
                "via European Space Imaging · all rights reserved",
         description="CEMS graded the damage rather than only mapping the water: from "
                     "a WorldView-3 acquisition on 27 August at 05:05 UTC it counted "
                     "more than 240 buildings destroyed and 32 damaged in the area "
                     "shown around Syabrubesi. The map products are rights-reserved "
                     "and are linked, not reproduced here."),
    dict(display_order=120, provider="UNOSAT / UNITAR", product_type="impact_map",
         title="Satellite-detected mudflow and rockflow extent, Rasuwa",
         area="Rasuwa District", acquired_after=date(2026, 8, 27),
         url=UNOSAT_URL, credit="UNOSAT / UNITAR",
         description="Extent of the debris flow derived for 26-27 August, the first "
                     "independent UN mapping of how far the material travelled."),
    dict(display_order=130, provider="UNOSAT / UNITAR", product_type="impact_map",
         title="Mudflow and rockflow impact assessment, Rasuwa and Nuwakot",
         area="Rasuwa and Nuwakot districts",
         url=UNOSAT_URL, credit="UNOSAT / UNITAR",
         description="Impact assessment across the two districts nearest the source, "
                     "the pair that between them hold most of the missing."),
    dict(display_order=140, provider="Vantor (Maxar) Open Data",
         product_type="pre_post",
         title="Nepal-Flooding-Aug-2026 open imagery collection (16 scenes)",
         area="Rasuwagadhi to Trishuli Bazar",
         acquired_before=date(2021, 10, 16), acquired_after=date(2026, 9, 1),
         url=VANTOR_URL,
         credit="Vantor Open Data (formerly Maxar Open Data) · CC BY-NC 4.0",
         description="Sixteen 30-50 cm scenes released free for this event, spanning "
                     "an October 2021 archive baseline to 1 September 2026. This is "
                     "the only commercial collection the desk is licensed to display: "
                     "the pairs are shown in the Vantor widget."),
    dict(display_order=100, provider="ArcGIS StoryMaps", product_type="analysis",
         title="August 2026 Nepal Trishuli Flood (StoryMap)",
         area="Trishuli basin", url=STORYMAP_URL,
         credit="ArcGIS StoryMaps",
         description="Compiled imagery and mapping narrative covering the collapse, "
                     "the surge and the downstream damage."),
]

# ------------------------------------------------------------- chronology
# Same-day beats whose clock time is not published share the best-established
# timestamp for that day and are sequenced by display_order.
CHRONOLOGY = [
    dict(display_order=45, kind="response",
         occurred_at=datetime(2026, 8, 26, 12, 0, tzinfo=NPT),
         time_published=False,
         headline="Copernicus EMS Rapid Mapping activated as EMSR927",
         detail="The EU's emergency mapping service opens an activation over four "
                "Areas of Interest in Rasuwa, tasking commercial satellites to grade "
                "building damage rather than only trace the water.",
         source="Copernicus Emergency Management Service",
         source_url=EMSR927_URL),
    dict(display_order=55, kind="assessment",
         occurred_at=datetime(2026, 8, 27, 5, 5, tzinfo=timezone.utc),
         time_published=True,
         headline="WorldView-3 counts 240+ buildings destroyed at Syabrubesi",
         detail="A 05:05 UTC acquisition gives Copernicus EMS the first hard damage "
                "count of the event: more than 240 buildings destroyed and 32 damaged "
                "in the mapped area around Syabrubesi. NDRRMA's national toll stood at "
                "165 dead that morning.",
         source="Copernicus EMS · WorldView-3 via European Space Imaging",
         source_url=EMS_IMAGE_URL),
    dict(display_order=58, kind="assessment",
         occurred_at=datetime(2026, 8, 27, 5, 5, tzinfo=timezone.utc),
         time_published=False,
         headline="Vantor releases the first post-event 30 cm pass over the corridor",
         detail="Maxar's open-data programme publishes a 27 August scene over "
                "Rasuwagadhi, Timure and Syabrubesi under CC BY-NC 4.0. At 71 per cent "
                "monsoon cloud it is far from clear, but the braided debris channel "
                "reads through the gaps against an October 2021 baseline.",
         source="Vantor Open Data (formerly Maxar Open Data)",
         source_url=VANTOR_URL),
    dict(display_order=10, kind="trigger",
         occurred_at=datetime(2026, 8, 26, 2, 52, tzinfo=timezone.utc),
         time_published=True,
         headline="Bedrock collapses beneath the Langtang Lirung glacier",
         detail="Ice, rock and water fall into the valley inside Langtang National "
                "Park. The impact energy registers as an Ms 5.2 seismic signal at "
                "02:52 UTC and is detected worldwide. Reporting places the collapse at "
                "about 09:15 Nepal local time; both timings are as published and are "
                "not reconciled here.",
         source="Seismic networks · Planet Labs imagery, reported by Phys.org",
         source_url=PHYS_URL),
    dict(display_order=20, kind="impact",
         occurred_at=datetime(2026, 8, 26, 9, 15, tzinfo=NPT),
         time_published=True,
         headline="Surge destroys the Gyirong Port / Rasuwagadhi border crossing",
         detail="The flood enters the Bhote Koshi from the Tibet side and takes out the "
                "crossing. Imagery from April 2024 shows several large buildings and a "
                "basketball court on the site; afterwards almost nothing stands and the "
                "ground is scoured to bedrock.",
         source="Al Jazeera satellite imagery analysis", source_url=ALJAZEERA_URL),
    dict(display_order=30, kind="impact",
         occurred_at=datetime(2026, 8, 26, 9, 15, tzinfo=NPT),
         time_published=True,
         headline="Flood runs about 100 km down the Lende Khola and Trishuli",
         detail="Water rises as much as 9 m in 30 minutes along the valley, through "
                "Timure, Syabrubesi and on into Nuwakot, Dhading and Chitwan. Bodies "
                "were later recovered as far as 240 km downstream inside India.",
         source="Bloomberg visual investigation", source_url=BLOOMBERG_URL),
    dict(display_order=40, kind="response",
         occurred_at=datetime(2026, 8, 26, 14, 58, tzinfo=CEST),
         time_published=True,
         headline="International Charter Activation 1052 opened for Nepal",
         detail="Requested by the Asian Disaster Reduction Center on behalf of the "
                "Department of Hydrology and Meteorology, Ministry of Energy, Water "
                "Resources and Irrigation. Project managed by Samir Belabbes (UNITAR), "
                "with 18 products published from NRSC, ISRO, the British Geological "
                "Survey, SERTIT, ICIMOD and Copernicus EMS.",
         source="International Charter Space and Major Disasters", source_url=CHARTER_URL),
    dict(display_order=50, kind="assessment",
         occurred_at=datetime(2026, 8, 27, 9, 0, tzinfo=NPT),
         time_published=False,
         headline="First consolidated toll: 165 dead, 826 missing",
         detail="One day after the collapse, with the downstream districts not yet "
                "reached.",
         source="NDRRMA situation update, 27 Aug 2026", source_url=RELIEFWEB_URL),
    dict(display_order=60, kind="assessment",
         occurred_at=datetime(2026, 8, 27, 10, 30, tzinfo=NPT),
         time_published=False,
         headline="Sentinel-2 acquires the post-event natural-colour scene",
         detail="Paired against the 12 August acquisition, it shows the increase in "
                "river water along the Trishuli.",
         source="ESA / Copernicus", source_url=ESA_URL),
    dict(display_order=70, kind="assessment",
         occurred_at=datetime(2026, 8, 28, 9, 0, tzinfo=NPT),
         time_published=False,
         headline="Toll rises to 579 dead, 1,924 missing",
         detail="Reach extends into Nuwakot and Chitwan; about 93,000 people assessed "
                "as affected and roughly 500 foreign nationals unaccounted for.",
         source="NDRRMA situation update, 28 Aug 2026", source_url=NEPALDISASTER_URL),
    dict(display_order=80, kind="assessment",
         occurred_at=datetime(2026, 8, 28, 12, 0, tzinfo=NPT),
         time_published=False,
         headline="Charter publishes the first Nuwakot and Timure impact products",
         detail="Pre/post imagery for Nuwakot district damages and the "
                "Timure-Syaburbensi impact map.",
         source="International Charter Space and Major Disasters", source_url=CHARTER_URL),
    dict(display_order=90, kind="assessment",
         occurred_at=datetime(2026, 8, 29, 9, 0, tzinfo=NPT),
         time_published=False,
         headline="Toll rises to 626 dead as Chitwan recoveries mount",
         detail="Chitwan, roughly 160 km downstream, has by now recovered more bodies "
                "than any other district.",
         source="NDRRMA situation update, 29 Aug 2026", source_url=NEPALDISASTER_URL),
    dict(display_order=100, kind="assessment",
         occurred_at=datetime(2026, 8, 31, 9, 0, tzinfo=NPT),
         time_published=False,
         headline="Toll passes 900: 903 dead, 4,247 missing, 10,451 rescued",
         detail="UN OCHA reports access as the binding constraint on the response, with "
                "the Prithvi Highway cut at Krishnabhir.",
         source="NDRRMA, reported by UN OCHA, 31 Aug 2026", source_url=UN_URL),
    dict(display_order=110, kind="warning",
         occurred_at=datetime(2026, 8, 31, 12, 0, tzinfo=NPT),
         time_published=False,
         headline="China warns of a fresh glacier collapse and new water building up",
         detail="China's water ministry warns of continuing risk along the border after "
                "upstream flows picked up again, with new water accumulating behind the "
                "collapse debris. The threat to the valley is not over.",
         source="Ministry of Water Resources, PRC, 31 Aug 2026", source_url=WIKI_URL),
    dict(display_order=120, kind="assessment",
         occurred_at=datetime(2026, 9, 1, 9, 0, tzinfo=NPT),
         time_published=True,
         headline="NDRRMA reports 987 dead, 3,916 missing, 11,814 rescued",
         detail="Preliminary damage put at Rs 200bn, with rebuilding projected as high "
                "as Rs 762bn. AP and the New York Times reported the toll passing 1,000 "
                "the same day; both figures stand as published. This is the deadliest "
                "disaster in Nepal since the 2015 earthquake.",
         source="NDRRMA bulletin, 1 Sept 2026 09:00 NPT", source_url=NEPALDISASTER_URL),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for product in IMAGERY:
            stmt = insert(FloodImageryProduct).values(event_key=EVENT, **product)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_imagery_event_title",
                set_={k: stmt.excluded[k] for k in product if k != "title"},
            )
            await db.execute(stmt)

        for entry in CHRONOLOGY:
            stmt = insert(FloodChronologyEntry).values(event_key=EVENT, **entry)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_chronology_event_headline",
                set_={k: stmt.excluded[k] for k in entry if k != "headline"},
            )
            await db.execute(stmt)

        await db.commit()

        products = (await db.execute(
            select(FloodImageryProduct)
            .where(FloodImageryProduct.event_key == EVENT))).scalars().all()
        events = (await db.execute(
            select(FloodChronologyEntry)
            .where(FloodChronologyEntry.event_key == EVENT))).scalars().all()
        print(f"seeded {len(products)} imagery products, {len(events)} chronology entries")
        for p in sorted(products, key=lambda p: p.display_order):
            print(f"  {p.provider:24} {p.product_type:11} {p.title[:58]}")
        for e in sorted(events, key=lambda e: (e.occurred_at, e.display_order)):
            stamp = (f"{e.occurred_at.astimezone(NPT):%Y-%m-%d %H:%M} NPT" if e.time_published
                     else f"{e.occurred_at.astimezone(NPT):%Y-%m-%d}      —   ")
            print(f"  {stamp} {e.kind:11} "
                  f"{e.headline[:56]}")


if __name__ == "__main__":
    asyncio.run(main())
