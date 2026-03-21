"""Add automated source reliability fields.

Revision ID: 074
Revises: 073
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_reliability",
        sa.Column("automation_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "source_reliability",
        sa.Column("automation_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "source_reliability",
        sa.Column("override_pinned", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "source_reliability",
        sa.Column("override_reliability_rating", sa.String(length=1), nullable=True),
    )
    op.add_column(
        "source_reliability",
        sa.Column("override_credibility_rating", sa.Integer(), nullable=True),
    )
    op.add_column(
        "source_reliability",
        sa.Column("override_confidence_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "source_reliability",
        sa.Column("override_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "source_reliability",
        sa.Column("override_set_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "source_reliability",
        sa.Column("override_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_source_reliability_override_set_by_id_users",
        "source_reliability",
        "users",
        ["override_set_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_source_reliability_override_set_by_id_users", "source_reliability", type_="foreignkey")
    op.drop_column("source_reliability", "override_set_at")
    op.drop_column("source_reliability", "override_set_by_id")
    op.drop_column("source_reliability", "override_notes")
    op.drop_column("source_reliability", "override_confidence_score")
    op.drop_column("source_reliability", "override_credibility_rating")
    op.drop_column("source_reliability", "override_reliability_rating")
    op.drop_column("source_reliability", "override_pinned")
    op.drop_column("source_reliability", "automation_updated_at")
    op.drop_column("source_reliability", "automation_metrics")
