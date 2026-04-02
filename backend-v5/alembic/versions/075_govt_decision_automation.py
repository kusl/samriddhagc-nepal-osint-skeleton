"""Add government decision automation tables.

Revision ID: 075
Revises: 074
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "govt_decision_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_key", sa.String(length=120), nullable=False),
        sa.Column("event_key", sa.String(length=120), nullable=False),
        sa.Column("candidate_signature", sa.String(length=120), nullable=False),
        sa.Column("source_story_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("source_announcement_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("representative_title", sa.Text(), nullable=True),
        sa.Column("representative_url", sa.Text(), nullable=True),
        sa.Column("office", sa.String(length=255), nullable=True),
        sa.Column("implementing_ministry", sa.String(length=255), nullable=True),
        sa.Column("decision_type", sa.String(length=80), nullable=True),
        sa.Column("decision_title", sa.Text(), nullable=True),
        sa.Column("decision_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=60), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("is_actual_decision", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("raw_model_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_key"),
    )
    op.create_index("ix_govt_decision_items_external_key", "govt_decision_items", ["external_key"], unique=False)
    op.create_index("ix_govt_decision_items_event_key", "govt_decision_items", ["event_key"], unique=False)
    op.create_index("ix_govt_decision_items_candidate_signature", "govt_decision_items", ["candidate_signature"], unique=False)
    op.create_index("ix_govt_decision_items_published_at", "govt_decision_items", ["published_at"], unique=False)
    op.create_index("idx_govt_decision_event_published", "govt_decision_items", ["event_key", "published_at"], unique=False)

    op.create_table(
        "govt_decision_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("govt_decision_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("final_office", sa.String(length=255), nullable=True),
        sa.Column("final_implementing_ministry", sa.String(length=255), nullable=True),
        sa.Column("final_decision_type", sa.String(length=80), nullable=True),
        sa.Column("final_decision_title", sa.Text(), nullable=True),
        sa.Column("final_decision_summary", sa.Text(), nullable=True),
        sa.Column("final_status", sa.String(length=60), nullable=True),
        sa.Column("final_source_url", sa.Text(), nullable=True),
        sa.Column("final_evidence_note", sa.Text(), nullable=True),
        sa.Column("final_confidence", sa.Float(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("needs_rerun", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rerun_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rerun_requested_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["govt_decision_item_id"], ["govt_decision_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rejected_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rerun_requested_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("govt_decision_item_id"),
    )
    op.create_index("ix_govt_decision_reviews_govt_decision_item_id", "govt_decision_reviews", ["govt_decision_item_id"], unique=False)
    op.create_index("ix_govt_decision_reviews_workflow_status", "govt_decision_reviews", ["workflow_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_govt_decision_reviews_workflow_status", table_name="govt_decision_reviews")
    op.drop_index("ix_govt_decision_reviews_govt_decision_item_id", table_name="govt_decision_reviews")
    op.drop_table("govt_decision_reviews")

    op.drop_index("idx_govt_decision_event_published", table_name="govt_decision_items")
    op.drop_index("ix_govt_decision_items_published_at", table_name="govt_decision_items")
    op.drop_index("ix_govt_decision_items_candidate_signature", table_name="govt_decision_items")
    op.drop_index("ix_govt_decision_items_event_key", table_name="govt_decision_items")
    op.drop_index("ix_govt_decision_items_external_key", table_name="govt_decision_items")
    op.drop_table("govt_decision_items")
