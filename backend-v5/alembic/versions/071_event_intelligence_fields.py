"""Add event intelligence fields to story features and clusters.

Revision ID: 071
Revises: 070
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("story_features", sa.Column("provinces", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("story_features", sa.Column("municipalities", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("story_features", sa.Column("place_mentions", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("story_features", sa.Column("geo_confidence", sa.Float(), nullable=True))
    op.add_column("story_features", sa.Column("primary_province", sa.String(length=100), nullable=True))
    op.add_column("story_features", sa.Column("primary_municipality", sa.String(length=120), nullable=True))
    op.add_column("story_features", sa.Column("named_people", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("story_features", sa.Column("named_orgs", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("story_features", sa.Column("named_parties", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("story_features", sa.Column("named_infrastructure", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("story_features", sa.Column("event_type", sa.String(length=50), nullable=True))
    op.add_column("story_features", sa.Column("operational_domain", sa.String(length=50), nullable=True))
    op.add_column("story_features", sa.Column("event_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("story_features", sa.Column("freshness_score", sa.Float(), nullable=True))

    op.add_column("story_clusters", sa.Column("event_type", sa.String(length=50), nullable=True))
    op.add_column("story_clusters", sa.Column("primary_province", sa.String(length=100), nullable=True))
    op.add_column("story_clusters", sa.Column("primary_district", sa.String(length=100), nullable=True))
    op.add_column("story_clusters", sa.Column("primary_municipality", sa.String(length=120), nullable=True))
    op.add_column("story_clusters", sa.Column("geo_confidence", sa.Float(), nullable=True))
    op.add_column("story_clusters", sa.Column("main_entities", postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column("story_clusters", sa.Column("novelty_score", sa.Float(), nullable=True))
    op.add_column("story_clusters", sa.Column("heat_score", sa.Float(), nullable=True))
    op.add_column("story_clusters", sa.Column("spread_score", sa.Float(), nullable=True))
    op.add_column("story_clusters", sa.Column("event_confidence", sa.Float(), nullable=True))
    op.add_column("story_clusters", sa.Column("social_post_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("story_clusters", sa.Column("official_confirmation_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_index("ix_story_clusters_event_type", "story_clusters", ["event_type"], unique=False)
    op.create_index("ix_story_clusters_primary_province", "story_clusters", ["primary_province"], unique=False)
    op.create_index("ix_story_clusters_primary_district", "story_clusters", ["primary_district"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_story_clusters_primary_district", table_name="story_clusters")
    op.drop_index("ix_story_clusters_primary_province", table_name="story_clusters")
    op.drop_index("ix_story_clusters_event_type", table_name="story_clusters")

    op.drop_column("story_clusters", "official_confirmation_count")
    op.drop_column("story_clusters", "social_post_count")
    op.drop_column("story_clusters", "event_confidence")
    op.drop_column("story_clusters", "spread_score")
    op.drop_column("story_clusters", "heat_score")
    op.drop_column("story_clusters", "novelty_score")
    op.drop_column("story_clusters", "main_entities")
    op.drop_column("story_clusters", "geo_confidence")
    op.drop_column("story_clusters", "primary_municipality")
    op.drop_column("story_clusters", "primary_district")
    op.drop_column("story_clusters", "primary_province")
    op.drop_column("story_clusters", "event_type")

    op.drop_column("story_features", "freshness_score")
    op.drop_column("story_features", "event_time")
    op.drop_column("story_features", "operational_domain")
    op.drop_column("story_features", "event_type")
    op.drop_column("story_features", "named_infrastructure")
    op.drop_column("story_features", "named_parties")
    op.drop_column("story_features", "named_orgs")
    op.drop_column("story_features", "named_people")
    op.drop_column("story_features", "primary_municipality")
    op.drop_column("story_features", "primary_province")
    op.drop_column("story_features", "geo_confidence")
    op.drop_column("story_features", "place_mentions")
    op.drop_column("story_features", "municipalities")
    op.drop_column("story_features", "provinces")
