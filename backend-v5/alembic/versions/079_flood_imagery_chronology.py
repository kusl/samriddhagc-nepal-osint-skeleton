"""Satellite imagery products and narrative chronology for flood events.

Adds two tables:

* ``flood_imagery_products`` — citable imagery artefacts for an event: the
  International Charter's activation products, before/after acquisition pairs
  from Sentinel-2, Landsat-9 and Planet, and news-published comparisons. These
  are distinct from the live NASA GIBS tile layers the map already consumes:
  a tile service answers "where is the water today", a Charter impact map
  answers "what did this specific place look like before and after".
* ``flood_chronology`` — dated narrative beats. The toll table records how the
  count moved; this records what happened, so the desk can interleave the two.

Revision ID: 079
Revises: 078
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flood_imagery_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        # pre_post | impact_map | analysis | tile_layer
        sa.Column("product_type", sa.String(length=32), nullable=False),
        sa.Column("acquired_before", sa.Date(), nullable=True),
        sa.Column("acquired_after", sa.Date(), nullable=True),
        sa.Column("sensor", sa.String(length=80), nullable=True),
        sa.Column("area", sa.String(length=160), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("credit", sa.Text(), nullable=True),
        sa.Column("published_on", sa.Date(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", "title", name="uq_imagery_event_title"),
    )
    op.create_index("ix_flood_imagery_products_event_key", "flood_imagery_products",
                    ["event_key"], unique=False)

    op.create_table(
        "flood_chronology",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        # Offset-aware: the seismic record is UTC, the surge is Nepal local.
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        # trigger | impact | response | assessment | warning
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", "headline", name="uq_chronology_event_headline"),
    )
    op.create_index("ix_flood_chronology_event_key", "flood_chronology",
                    ["event_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_flood_chronology_event_key", table_name="flood_chronology")
    op.drop_table("flood_chronology")
    op.drop_index("ix_flood_imagery_products_event_key", table_name="flood_imagery_products")
    op.drop_table("flood_imagery_products")
