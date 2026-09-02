"""Live official-feed mirrors for the flood desk.

Until now the flood desk's figures were seeded by hand from NDRRMA's published
board, which meant the numbers were exactly as fresh as the last time somebody
edited a Python file. These three tables let a scheduled job mirror the official
feeds instead: the authority's situation reports and what parses out of them,
the photographs the government publishes for redistribution alongside news
leads that may only be linked, and the last good payload from each live feed.

They are deliberately not one table. A sitrep is a document with a citation, a
media item carries licence terms that govern how it may be rendered, and a
snapshot is a disposable cache of an upstream's current state. Collapsing them
would lose the distinction the desk has to render.

Revision ID: 081
Revises: 080
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flood_sitreps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False),
        # NDRRMA's own publication id — the natural key for an upsert.
        sa.Column("source_id", sa.Integer(), nullable=False),
        # Null on the daily updates, which are published without a number.
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("lang", sa.String(2), nullable=False, server_default="ne"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_ne", sa.Text(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        # Text, not a time: reports print "बिहान ९" with no minute, and
        # storing that as 09:00 would assert a precision NDRRMA did not.
        sa.Column("report_time", sa.Text(), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("extracted", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("text_excerpt", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("event_key", "source_id", name="uq_sitrep_event_source"),
    )
    op.create_index("ix_flood_sitreps_event_key", "flood_sitreps", ["event_key"])

    op.create_table(
        "flood_media_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_ne", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("credit", sa.Text(), nullable=True),
        sa.Column("outlet", sa.Text(), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        # Governs rendering, not styling: 'display' may be shown full size with
        # a credit, 'link_preview' only as a thumbnail linking to the publisher.
        sa.Column("licence_tier", sa.String(16), nullable=False,
                  server_default="link_preview"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("event_key", "source", "source_id",
                            name="uq_media_event_source_id"),
    )
    op.create_index("ix_flood_media_items_event_key", "flood_media_items", ["event_key"])

    op.create_table(
        "flood_live_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("feed", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("event_key", "feed", name="uq_snapshot_event_feed"),
    )
    op.create_index("ix_flood_live_snapshots_event_key", "flood_live_snapshots",
                    ["event_key"])


def downgrade() -> None:
    op.drop_index("ix_flood_live_snapshots_event_key", table_name="flood_live_snapshots")
    op.drop_table("flood_live_snapshots")
    op.drop_index("ix_flood_media_items_event_key", table_name="flood_media_items")
    op.drop_table("flood_media_items")
    op.drop_index("ix_flood_sitreps_event_key", table_name="flood_sitreps")
    op.drop_table("flood_sitreps")
