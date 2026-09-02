"""Official casualty and damage figures for named flood disasters.

Why this table exists, separate from `disaster_incidents`:

BIPAD's incident feed — the platform's normal disaster source — did not record
the 26 August 2026 Trishuli disaster at all. Checked 2026-09-01: BIPAD's total
death count across *every* hazard since 25 August was 7, mostly snake bites,
while NDRRMA was reporting 1,003 dead and ~4,000 missing from the flood alone.
An incident-aggregation pipeline simply cannot represent a mega-disaster, because
the responders producing incident reports are busy responding.

So the headline figures come from the disaster authority directly, stored as an
append-only series of dated snapshots. Keeping the history matters: the toll on
this event ran 165 -> 579 -> 626 -> 903 -> 1,003 over five days, and that
trajectory is itself the story. Every row carries the authority that issued it
and a source URL, so no number on the desk is unattributable.
"""
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (Boolean, Date, DateTime, Float, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FloodOfficialToll(Base):
    """One dated figure set for one event, as published by one authority."""

    __tablename__ = "flood_official_tolls"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Stable slug for the event, e.g. "trishuli-2026-08".
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # The date the figures describe — not when we ingested them.
    as_of: Mapped[date] = mapped_column(Date, nullable=False)

    # Who published it: NDRRMA, UN OCHA, Nepal Police, IPPAN...
    authority: Mapped[str] = mapped_column(String(80), nullable=False)

    deaths: Mapped[Optional[int]] = mapped_column(Integer)
    missing: Mapped[Optional[int]] = mapped_column(Integer)
    injured: Mapped[Optional[int]] = mapped_column(Integer)
    rescued: Mapped[Optional[int]] = mapped_column(Integer)
    people_affected: Mapped[Optional[int]] = mapped_column(Integer)
    foreign_nationals_missing: Mapped[Optional[int]] = mapped_column(Integer)

    # Damage as published. USD is stored rather than derived, because the
    # authority quotes its own conversion and we should not silently re-rate it.
    damage_npr: Mapped[Optional[float]] = mapped_column(Float)
    damage_usd: Mapped[Optional[float]] = mapped_column(Float)
    damage_note: Mapped[Optional[str]] = mapped_column(Text)

    # Per-district figures where the authority breaks them out, as
    # {"Chitwan": {"bodies_recovered": 233}, ...}
    district_tolls: Mapped[Optional[dict]] = mapped_column(JSONB)

    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_title: Mapped[Optional[str]] = mapped_column(Text)
    note: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now())

    __table_args__ = (
        # One figure set per authority per day per event; a correction replaces
        # rather than duplicates.
        UniqueConstraint("event_key", "as_of", "authority", name="uq_toll_event_date_authority"),
    )

    def __repr__(self) -> str:
        return f"<FloodOfficialToll {self.event_key} {self.as_of} {self.authority} deaths={self.deaths}>"


class FloodSituationPanel(Base):
    """One published category breakdown for an event.

    NDRRMA publishes the situation as categories — deaths by district, missing
    by category, hydropower tunnel rescue, damage, international aid — each a
    headline figure with labelled sub-rows. Storing it in that shape keeps the
    desk faithful to the bulletin instead of flattening it into totals that lose
    the detail responders actually use.
    """

    __tablename__ = "flood_situation_panels"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    panel_key: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[Optional[str]] = mapped_column(Text)
    headline_value: Mapped[Optional[str]] = mapped_column(Text)
    headline_label: Mapped[Optional[str]] = mapped_column(Text)

    # [{"label": ..., "value": ...}] in published order.
    rows: Mapped[Optional[list]] = mapped_column(JSONB)

    note: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(Text)
    as_of: Mapped[Optional[date]] = mapped_column(Date)
    display_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(),
        onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("event_key", "panel_key", name="uq_panel_event_key"),
    )

    def __repr__(self) -> str:
        return f"<FloodSituationPanel {self.event_key}/{self.panel_key}>"


class FloodImageryProduct(Base):
    """One published satellite imagery product bearing on an event.

    Kept out of the tile-layer descriptors in the API: those are live raster
    services the map consumes, while these are one-off analytical products —
    Charter activation maps, before/after acquisition pairs, damage assessments
    — that exist as citable artefacts elsewhere. In terrain this cloudy the
    acquisition dates and the sensor are load-bearing, not metadata: a
    Sentinel-2 natural-colour pair and a Landsat-9 shortwave-infrared pair over
    the same valley answer different questions, so both are recorded rather
    than collapsed into "satellite imagery".
    """

    __tablename__ = "flood_imagery_products"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # "International Charter", "ESA Copernicus", "Planet Labs", "NASA GIBS"...
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # pre_post | impact_map | analysis | tile_layer
    product_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # The two acquisitions a before/after pair compares. Null on products that
    # are not a paired comparison.
    acquired_before: Mapped[Optional[date]] = mapped_column(Date)
    acquired_after: Mapped[Optional[date]] = mapped_column(Date)

    sensor: Mapped[Optional[str]] = mapped_column(String(80))
    area: Mapped[Optional[str]] = mapped_column(String(160))
    description: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    credit: Mapped[Optional[str]] = mapped_column(Text)
    published_on: Mapped[Optional[date]] = mapped_column(Date)
    display_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(),
        onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("event_key", "title", name="uq_imagery_event_title"),
    )

    def __repr__(self) -> str:
        return f"<FloodImageryProduct {self.event_key} {self.provider}: {self.title}>"


class FloodChronologyEntry(Base):
    """One dated beat in an event's narrative.

    The toll series in `flood_official_tolls` records how the count moved; this
    records what happened. They interleave on the desk — a revision to 987 dead
    means little without the collapse, the surge and the 100 km run downstream
    around it — so each entry carries its own source rather than inheriting the
    authority of the toll it sits beside.
    """

    __tablename__ = "flood_chronology"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Stored with an explicit offset. Nepal local time and the UTC timestamps on
    # the seismic and satellite records are 5h45m apart, and conflating them
    # would put the impact energy before the collapse that caused it.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # False when only the date is on the record, so the desk can render the beat
    # without a clock instead of asserting an hour nobody published.
    time_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)

    # trigger | impact | response | assessment | warning
    kind: Mapped[str] = mapped_column(String(24), nullable=False)

    source: Mapped[Optional[str]] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(),
        onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("event_key", "headline", name="uq_chronology_event_headline"),
    )

    def __repr__(self) -> str:
        return f"<FloodChronologyEntry {self.event_key} {self.occurred_at:%Y-%m-%d} {self.kind}>"


class FloodSitrep(Base):
    """One NDRRMA situation report on an event, and what parsed out of it.

    The PDF is the authority's own record and stays the citation; `extracted`
    is our reading of it, kept in a separate column so the two are never
    confused. A key is absent rather than zero when the report does not print
    that figure — the series runs twice daily in two languages and the Nepali
    editions extract with broken conjuncts, so most rows carry the document
    and nothing else, which is an honest state for them to be in.
    """

    __tablename__ = "flood_sitreps"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # NDRRMA's publication id. Stable across re-publication of the same report.
    source_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Null on the daily updates, which NDRRMA publishes without a sequence
    # number; inventing one would assert an order the authority did not.
    number: Mapped[Optional[int]] = mapped_column(Integer)
    lang: Mapped[str] = mapped_column(String(2), nullable=False, default="ne")

    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_ne: Mapped[Optional[str]] = mapped_column(Text)
    report_date: Mapped[Optional[date]] = mapped_column(Date)
    # As printed — "6:30 PM", "साँझ ६:००". Not normalised: a report saying only
    # "बिहान ९" has not published a minute and must not be shown with one.
    report_time: Mapped[Optional[str]] = mapped_column(Text)

    pdf_url: Mapped[Optional[str]] = mapped_column(Text)
    page_url: Mapped[Optional[str]] = mapped_column(Text)

    extracted: Mapped[Optional[dict]] = mapped_column(JSONB)
    text_excerpt: Mapped[Optional[str]] = mapped_column(Text)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(),
        onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("event_key", "source_id", name="uq_sitrep_event_source"),
    )

    def __repr__(self) -> str:
        return f"<FloodSitrep {self.event_key} #{self.number} {self.lang}>"


class FloodMediaItem(Base):
    """One picture the desk may put on the screen, and the terms it comes with.

    Two very different things share this table, and `licence_tier` is what keeps
    them apart. Government photographs from the OPMCM rescue portal and NDRRMA
    press notes are published for redistribution and render full size with a
    credit. A press lead is a news outlet's copyrighted photograph: it renders
    only as a small thumbnail beside the outlet's name and a link back to their
    page, which is a link preview and not a reproduction.

    Nothing here stores image bytes. The API proxies from `image_url` at read
    time, so an upstream that withdraws a photograph withdraws it from us too.
    """

    __tablename__ = "flood_media_items"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # opmcm_carousel | ndrrma_press | press_lead
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)

    # govt_photo | press_lead
    kind: Mapped[str] = mapped_column(String(24), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_ne: Mapped[Optional[str]] = mapped_column(Text)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    credit: Mapped[Optional[str]] = mapped_column(Text)
    outlet: Mapped[Optional[str]] = mapped_column(Text)
    page_url: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(Text)

    # display | link_preview — see the class docstring; the frontend renders
    # off this field, so it is not decoration.
    licence_tier: Mapped[str] = mapped_column(String(16), nullable=False,
                                              default="link_preview")

    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=func.now(),
        onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("event_key", "source", "source_id",
                         name="uq_media_event_source_id"),
    )

    def __repr__(self) -> str:
        return f"<FloodMediaItem {self.event_key} {self.source}/{self.source_id}>"


class FloodLiveSnapshot(Base):
    """The last good payload from one live feed, plus whether the last try worked.

    One row per feed, overwritten in place: this is a cache of the current
    upstream state, not a history — the history that matters is the toll series,
    which has its own table and its own guards.

    A failed poll sets `ok` false and records the error but leaves `payload`
    alone. The desk then shows the previous figures with an explicit staleness,
    which is the honest reading; blanking a panel because a ministry's API
    timed out would imply the response had stopped, not the feed.
    """

    __tablename__ = "flood_live_snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # ndrrma_rescue | ndrrma_status | opmcm_stats | bulletin_kpi | ndrrma_advisory
    feed: Mapped[str] = mapped_column(String(40), nullable=False)

    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("event_key", "feed", name="uq_snapshot_event_feed"),
    )

    def __repr__(self) -> str:
        return f"<FloodLiveSnapshot {self.event_key}/{self.feed} ok={self.ok}>"


class FloodFact(Base):
    """One sentence of one published story, turned into a typed fact.

    The boards (sites, assistance, tunnel ledger) read these as `auto` rows
    beside their hand-verified seeds. The sentence is kept verbatim so a
    reader can always see what was actually written; the figure and place
    are the desk's reading of it, and `status` says whether a person has
    looked ('auto' | 'verified' | 'rejected').
    """

    __tablename__ = "flood_facts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    story_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), index=True)
    story_url: Mapped[Optional[str]] = mapped_column(Text)
    outlet: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # burial | recovery | mortuary | forensic | transfer | team | aid | money | tunnel | road | toll
    fact_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    subject: Mapped[Optional[str]] = mapped_column(Text)
    subject_code: Mapped[Optional[str]] = mapped_column(String(32))
    place_text: Mapped[Optional[str]] = mapped_column(Text)
    district: Mapped[Optional[str]] = mapped_column(String(64))
    place_lat: Mapped[Optional[float]] = mapped_column(Float)
    place_lng: Mapped[Optional[float]] = mapped_column(Float)
    place_confidence: Mapped[Optional[str]] = mapped_column(String(24))
    figure: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(24))
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(8))
    extractor: Mapped[str] = mapped_column(String(48), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="auto", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 default=lambda: datetime.now(timezone.utc))


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    query: Mapped[str] = mapped_column(Text, primary_key=True)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    osm_type: Mapped[Optional[str]] = mapped_column(String(24))
    osm_class: Mapped[Optional[str]] = mapped_column(String(48))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 default=lambda: datetime.now(timezone.utc))


class FloodExtractionRun(Base):
    """One row per story the extractor has read, so a story is read once."""

    __tablename__ = "flood_extraction_runs"

    story_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor: Mapped[str] = mapped_column(String(48), nullable=False)
    facts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                             default=lambda: datetime.now(timezone.utc))
