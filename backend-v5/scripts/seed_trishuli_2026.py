#!/usr/bin/env python3
"""Seed official figures for the 26 August 2026 Trishuli glacier-collapse flood.

Every number here is as published by a disaster authority, with the authority
and the date it applies to recorded alongside it. Nothing is derived, averaged,
or reconciled across sources — where sources disagree (NDRRMA's 987 vs the
1,000+ carried by AP and NYT on the same day) both are kept and the desk shows
the disagreement rather than picking a winner.

Re-runnable: rows are upserted on (event_key, as_of, authority) for tolls and
(event_key, panel_key) for panels, so updating a figure means editing this file
and running it again.

Sources
-------
NDRRMA / Nepal Police figures compiled via nepaldisaster.com's situation page
(https://www.nepaldisaster.com/stats), cross-checked against:
  - UN News, "Nepal flooding deaths surpass 900 as needs climb" (31 Aug 2026)
    https://news.un.org/en/story/2026/08/1168233
  - Al Jazeera, "Nepal-China floods: What's the latest death toll..." (30 Aug)
    https://www.aljazeera.com/news/2026/8/30/nepal-china-flood-disaster-whats-the-latest-toll-how-many-are-missing
  - Wikipedia, "2026 Nepal floods" and "Timeline of the 2026 Nepal floods"
  - AP, "Mass burials in Nepal as death toll from flash floods exceeds 1,000"
"""
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.flood_event import FloodOfficialToll, FloodSituationPanel  # noqa: E402

EVENT = "trishuli-2026-08"

NDRRMA = "NDRRMA"
NDRRMA_URL = "https://bipadportal.gov.np/"
NEPALDISASTER = "https://www.nepaldisaster.com/stats"

# ---------------------------------------------------------------- toll series
# The trajectory matters as much as the latest number: this toll roughly
# sextupled between 27 and 31 August as downstream districts were reached.
TOLLS = [
    dict(as_of=date(2026, 8, 27), authority=NDRRMA, deaths=165, injured=73, missing=826,
         source_title="NDRRMA situation update, 27 Aug 2026",
         source_url="https://reliefweb.int/report/nepal/nepal-flood-response-situation-report-1-27-august-2026",
         note="First consolidated count, one day after the glacier collapse."),
    dict(as_of=date(2026, 8, 28), authority=NDRRMA, deaths=579, missing=1924,
         people_affected=93000, foreign_nationals_missing=500,
         source_title="NDRRMA situation update, 28 Aug 2026", source_url=NDRRMA_URL),
    dict(as_of=date(2026, 8, 29), authority=NDRRMA, deaths=626, missing=1924,
         source_title="NDRRMA situation update, 29 Aug 2026", source_url=NDRRMA_URL,
         district_tolls={
             "Chitwan": {"bodies_recovered": 233},
             "Nawalparasi East": {"bodies_recovered": 158},
             "Nuwakot": {"bodies_recovered": 51},
             "Gorkha": {"bodies_recovered": 48},
             "Nawalparasi West": {"bodies_recovered": 47},
             "Dhading": {"bodies_recovered": 45},
             "Tanahun": {"bodies_recovered": 31},
             "Rasuwa": {"bodies_recovered": 13},
         }),
    dict(as_of=date(2026, 8, 31), authority=NDRRMA, deaths=903, injured=1473,
         missing=4247, rescued=10451,
         source_title="NDRRMA, reported by UN OCHA, 31 Aug 2026",
         source_url="https://news.un.org/en/story/2026/08/1168233"),
    dict(as_of=date(2026, 9, 1), authority=NDRRMA, deaths=987, injured=279,
         missing=3916, rescued=11814, foreign_nationals_missing=583,
         damage_npr=200_000_000_000, damage_usd=4_500_000_000,
         damage_note="Preliminary government estimate, Rs 200bn (~USD 4-5bn). "
                     "The finance ministry has separately projected rebuilding "
                     "costs of up to Rs 762bn.",
         source_title="NDRRMA bulletin, 1 Sept 2026 09:00 NPT",
         source_url=NEPALDISASTER,
         district_tolls={
             "Chitwan": {"bodies_recovered": 321},
             "Nawalparasi East": {"bodies_recovered": 216},
             "Nawalparasi West": {"bodies_recovered": 170},
             "Nuwakot": {"bodies_recovered": 95},
             "Gorkha": {"bodies_recovered": 65},
             "Dhading": {"bodies_recovered": 55},
             "Tanahun": {"bodies_recovered": 38},
             "Rasuwa": {"bodies_recovered": 27},
         },
         note="Chitwan, ~160 km downstream, has recovered the most bodies; "
              "forensic DNA identification is in progress there. Rasuwa's low "
              "recovery count reflects debris depth near the source, not low "
              "impact — it holds the largest missing count."),
    # Kept deliberately: international wires reported 1,000+ the same day NDRRMA
    # published 987. Showing both is more honest than silently picking one.
    dict(as_of=date(2026, 9, 1), authority="AP / NYT (wire reports)", deaths=1010,
         missing=3916,
         source_title="AP: 'Mass burials in Nepal as death toll from flash floods exceeds 1,000'",
         source_url="https://en.wikipedia.org/wiki/2026_Nepal_floods",
         note="Wire services reported the toll passing 1,000 on 1 Sept, ahead of "
              "NDRRMA's published 987. Counts differ by whether provisionally "
              "identified bodies are included."),
]

# ------------------------------------------------------------------- panels
AS_OF = date(2026, 9, 1)

PANELS = [
    dict(panel_key="deaths", display_order=10,
         title="Confirmed deaths", subtitle="Nepal side · by district of recovery",
         headline_value="987", headline_label="confirmed dead",
         source="NDRRMA / Nepal Police · 1 Sept 09:00 NPT",
         rows=[
             {"label": "Chitwan", "value": "321"},
             {"label": "Nawalparasi East", "value": "216"},
             {"label": "Nawalparasi West", "value": "170"},
             {"label": "Nuwakot", "value": "95"},
             {"label": "Gorkha", "value": "65"},
             {"label": "Dhading", "value": "55"},
             {"label": "Tanahun", "value": "38"},
             {"label": "Rasuwa", "value": "27"},
         ],
         note="Chitwan — roughly 160 km downstream of the collapse — has recovered "
              "the most bodies, where forensic DNA identification is under way. "
              "Rasuwa's low count reflects debris depth at the source, not lower "
              "impact: it holds the largest missing figure."),

    dict(panel_key="missing", display_order=20,
         title="Missing and out of contact", subtitle="Nepal side · active NDRRMA registry",
         headline_value="3,916", headline_label="missing",
         source="NDRRMA / Nepal Police · 1 Sept 09:00 NPT",
         rows=[
             {"label": "Rasuwa", "value": "865"},
             {"label": "Linked to hydropower projects", "value": "639"},
             {"label": "Foreign nationals", "value": "583"},
             {"label": "Nepalis accompanying foreign tourists", "value": "127"},
             {"label": "Nuwakot", "value": "115"},
             {"label": "Makwanpur", "value": "65"},
             {"label": "Nepali Army personnel", "value": "45"},
             {"label": "Nepal Police personnel", "value": "25"},
             {"label": "Armed Police Force personnel", "value": "13"},
         ],
         note="Tibet's separately counted missing (546) are not included in this "
              "figure. Numbers fall as people are located and verified."),

    dict(panel_key="rescued", display_order=30,
         title="Rescued", subtitle="cumulative · rising daily",
         headline_value="11,814", headline_label="rescued",
         source="NDRRMA / Nepali Army · 1 Sept",
         rows=[
             {"label": "Named in the public registry", "value": "4,248"},
             {"label": "— of these, Nepali", "value": "3,918"},
             {"label": "— of these, foreign", "value": "330"},
             {"label": "Airlifted by the Nepali Army — Nepali", "value": "3,344"},
             {"label": "Airlifted by the Nepali Army — foreign", "value": "252"},
             {"label": "Rescue and relief flights flown", "value": "411"},
             {"label": "Logged in the NDRRMA rescue system", "value": "7,514"},
         ],
         note="Individually named entries feed family tracing."),

    dict(panel_key="medical", display_order=40,
         title="Injured and medical care", subtitle="hospitalised · treatments given",
         headline_value="279", headline_label="hospitalised",
         source="NDRRMA / Ministry of Health and Population · 1 Sept",
         rows=[
             {"label": "Still under intensive treatment", "value": "111"},
             {"label": "Treatments provided across the response", "value": "2,740"},
         ],
         note="Structured hospital care across Bharatpur, Pokhara, Dhading, "
              "Nuwakot and Kathmandu, plus mobile field clinics."),

    dict(panel_key="foreign", display_order=50,
         title="Foreign nationals missing", subtitle="by nationality · Nepal side",
         headline_value="583", headline_label="foreign nationals missing",
         source="Nepal Police / diplomatic missions · 1 Sept",
         rows=[
             {"label": "India", "value": "288"},
             {"label": "China (approx.)", "value": "100"},
             {"label": "United States", "value": "80"},
             {"label": "Ukraine", "value": "53"},
             {"label": "Malaysia", "value": "51"},
             {"label": "Australia", "value": "35"},
             {"label": "United Kingdom", "value": "33"},
             {"label": "Canada", "value": "32"},
             {"label": "South Korea", "value": "9"},
         ],
         note="Primarily pilgrims and trekkers on the Kailash Mansarovar and "
              "Langtang routes."),

    dict(panel_key="operations", display_order=60,
         title="Search operation and security forces", subtitle="live deployment across agencies",
         headline_value="21,008", headline_label="personnel mobilised",
         source="NDRRMA / Joint Command · 1 Sept",
         rows=[
             {"label": "Nepali Army", "value": "8,722"},
             {"label": "Nepal Police", "value": "7,894"},
             {"label": "Armed Police Force", "value": "4,203"},
             {"label": "Rescue and relief flights flown", "value": "411"},
             {"label": "Settlements still out of reach", "value": "2,498"},
             {"label": "Communication towers", "value": "connectivity restored"},
         ],
         note="Prithvi Highway remains cut at Krishnabhir; access is the binding "
              "constraint on the response, per UN OCHA."),

    dict(panel_key="hydropower", display_order=70,
         title="Hydropower tunnel rescue", subtitle="workers missing across 12 projects",
         headline_value="639", headline_label="workers missing",
         source="IPPAN / NDRRMA / Joint Rescue · 1 Sept",
         rows=[
             {"label": "Believed still inside tunnel systems", "value": "~500"},
             {"label": "Upper Trishuli-1 — believed inside", "value": "~300"},
             {"label": "Brought out of Trishuli 3A so far", "value": "~350"},
             {"label": "Airlifted from tunnels in the first two days", "value": "279"},
             {"label": "Hydropower facilities damaged or destroyed", "value": "27"},
         ],
         note="High-capacity sludge pump teams and underground rescue specialists "
              "are working at Upper Trishuli-1 and Chilime."),

    dict(panel_key="damage", display_order=80,
         title="Damage and infrastructure", subtitle="preliminary · Rs 200bn (~USD 4-5bn)",
         headline_value="Rs 200bn", headline_label="preliminary damage estimate",
         source="Government of Nepal / Dept. of Roads / NEA / IFRC · 1 Sept",
         rows=[
             {"label": "Roads and bridges", "value": "Rs 15bn"},
             {"label": "Bridges damaged", "value": "41"},
             {"label": "Road damaged", "value": "42 km"},
             {"label": "Generation knocked off the grid", "value": "431 MW"},
             {"label": "Under-construction capacity damaged", "value": "470 MW"},
             {"label": "Schools damaged or destroyed", "value": "38"},
             {"label": "Water and sanitation infrastructure", "value": "Rs 930m+"},
             {"label": "People affected (IFRC estimate)", "value": "93,000"},
             {"label": "Children needing psychosocial support", "value": "17,000"},
         ],
         note="The finance ministry has separately projected rebuilding costs of "
              "up to Rs 762bn (~USD 5bn). Nepal has appealed internationally for "
              "Bailey bridges."),

    dict(panel_key="aid", display_order=90,
         title="Relief funds and international aid", subtitle="pledged and arriving",
         headline_value="Rs 5.44bn", headline_label="PM Disaster Relief Fund",
         source="AP / BBC / Reuters / IFRC · 1 Sept",
         rows=[
             {"label": "Released to 15 local units", "value": "Rs 675m"},
             {"label": "IFRC emergency appeal", "value": "CHF 25m"},
             {"label": "Asian Development Bank", "value": "USD 5m"},
             {"label": "European Union", "value": "EUR 2m"},
             {"label": "Welthungerhilfe", "value": "EUR 2m"},
             {"label": "UN CERF", "value": "USD 2m"},
             {"label": "South Korea", "value": "USD 1m"},
             {"label": "Red Cross / IFRC DREF", "value": "CHF 1m"},
             {"label": "World Health Organization", "value": "USD 150,000"},
             {"label": "China — emergency supplies", "value": "50 t / 13,200 items"},
             {"label": "India — supplies", "value": "~50 t"},
         ],
         note="The UK ($6.8m), US and Canada ($3.6m each) and the UN ($2.5m) have "
              "also pledged support."),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for toll in TOLLS:
            stmt = insert(FloodOfficialToll).values(event_key=EVENT, **toll)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_toll_event_date_authority",
                set_={k: stmt.excluded[k] for k in toll if k not in ("as_of", "authority")},
            )
            await db.execute(stmt)

        for panel in PANELS:
            stmt = insert(FloodSituationPanel).values(event_key=EVENT, as_of=AS_OF, **panel)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_panel_event_key",
                set_={k: stmt.excluded[k] for k in panel if k != "panel_key"} | {"as_of": AS_OF},
            )
            await db.execute(stmt)

        await db.commit()

        tolls = (await db.execute(
            select(FloodOfficialToll).where(FloodOfficialToll.event_key == EVENT))).scalars().all()
        panels = (await db.execute(
            select(FloodSituationPanel).where(FloodSituationPanel.event_key == EVENT))).scalars().all()
        print(f"seeded {len(tolls)} toll snapshots, {len(panels)} situation panels")
        for t in sorted(tolls, key=lambda t: (t.as_of, t.authority)):
            print(f"  {t.as_of} {t.authority:24} dead={t.deaths} missing={t.missing}")


if __name__ == "__main__":
    asyncio.run(main())
