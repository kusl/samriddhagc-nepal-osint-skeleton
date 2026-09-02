"""Official disaster-authority figures for named flood events.

Adds two tables:

* ``flood_official_tolls`` — an append-only series of dated headline figures per
  authority, so the toll's trajectory is preserved (165 -> 579 -> 626 -> 903 ->
  987 across five days on the 2026 Trishuli event).
* ``flood_situation_panels`` — the detailed category breakdowns NDRRMA publishes
  (deaths by district, missing by category, hydropower tunnel rescue, damage,
  international aid). Each panel is a headline figure plus labelled rows, which
  is both how the authority publishes it and how the desk renders it.

Both exist because BIPAD's incident API does not carry this event at all — see
app/models/flood_event.py for the measurement that established that.

Revision ID: 078
Revises: 077
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flood_official_tolls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("authority", sa.String(length=80), nullable=False),
        sa.Column("deaths", sa.Integer(), nullable=True),
        sa.Column("missing", sa.Integer(), nullable=True),
        sa.Column("injured", sa.Integer(), nullable=True),
        sa.Column("rescued", sa.Integer(), nullable=True),
        sa.Column("people_affected", sa.Integer(), nullable=True),
        sa.Column("foreign_nationals_missing", sa.Integer(), nullable=True),
        sa.Column("damage_npr", sa.Float(), nullable=True),
        sa.Column("damage_usd", sa.Float(), nullable=True),
        sa.Column("damage_note", sa.Text(), nullable=True),
        sa.Column("district_tolls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", "as_of", "authority",
                            name="uq_toll_event_date_authority"),
    )
    op.create_index("ix_flood_official_tolls_event_key", "flood_official_tolls",
                    ["event_key"], unique=False)

    op.create_table(
        "flood_situation_panels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_key", sa.String(length=64), nullable=False),
        sa.Column("panel_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("headline_value", sa.Text(), nullable=True),
        sa.Column("headline_label", sa.Text(), nullable=True),
        # [{"label": "Chitwan", "value": "321"}, ...] — ordered as published.
        sa.Column("rows", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", "panel_key", name="uq_panel_event_key"),
    )
    op.create_index("ix_flood_situation_panels_event_key", "flood_situation_panels",
                    ["event_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_flood_situation_panels_event_key", table_name="flood_situation_panels")
    op.drop_table("flood_situation_panels")
    op.drop_index("ix_flood_official_tolls_event_key", table_name="flood_official_tolls")
    op.drop_table("flood_official_tolls")
