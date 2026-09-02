"""flood_facts + geocode_cache: automatically extracted, sourced facts.

Revision ID: 082
Revises: 081

Every row in flood_facts is one sentence of one published story turned into a
typed fact (a figure, a place, a subject) with the sentence kept verbatim. The
boards read these as `auto` rows beside the hand-verified seeds. geocode_cache
keeps Nominatim answers so a place is asked once.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "082"
down_revision = "081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flood_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False, index=True),
        sa.Column("story_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("story_url", sa.Text, nullable=True),
        sa.Column("outlet", sa.Text, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fact_type", sa.String(24), nullable=False, index=True),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("subject_code", sa.String(32), nullable=True),
        sa.Column("place_text", sa.Text, nullable=True),
        sa.Column("district", sa.String(64), nullable=True),
        sa.Column("place_lat", sa.Float, nullable=True),
        sa.Column("place_lng", sa.Float, nullable=True),
        sa.Column("place_confidence", sa.String(24), nullable=True),
        sa.Column("figure", sa.Float, nullable=True),
        sa.Column("unit", sa.String(24), nullable=True),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("extractor", sa.String(48), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(16), nullable=False, server_default="auto", index=True),
        sa.Column("dedupe_key", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "geocode_cache",
        sa.Column("query", sa.Text, primary_key=True),
        sa.Column("lat", sa.Float, nullable=True),
        sa.Column("lng", sa.Float, nullable=True),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("osm_type", sa.String(24), nullable=True),
        sa.Column("osm_class", sa.String(48), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "flood_extraction_runs",
        sa.Column("story_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("extractor", sa.String(48), nullable=False),
        sa.Column("facts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("flood_extraction_runs")
    op.drop_table("geocode_cache")
    op.drop_table("flood_facts")
