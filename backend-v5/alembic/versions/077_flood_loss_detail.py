"""Merge the 071/076 branches and add BIPAD loss-detail columns.

Two jobs in one revision:

1. **Merge heads.** History branched at 070 into 071 and 072->076, so
   ``alembic upgrade head`` was ambiguous and failed — which meant the compose
   ``migrate`` service exited 255 on every boot. Naming both as down_revision
   makes this a merge point, so plain ``head`` resolves again.

2. **Loss detail.** BIPAD's incident payload carries ``loss`` as an *ID*, not
   the figures, so deaths/injured/estimated_loss were always stored as 0. The
   real numbers live at ``/api/v1/loss/{id}/`` and are far richer than the four
   columns we had: gender-disaggregated casualties, evacuations, livestock, and
   destroyed houses/roads/bridges. These columns hold what the flood desk
   reports; ``loss_synced_at`` records when we last reconciled with BIPAD, since
   assessments are revised upward for days after an event.

Revision ID: 077
Revises: 071, 076
"""

from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = ("071", "076")
branch_labels = None
depends_on = None


# (column, type, server_default)
_LOSS_COLUMNS = [
    # Casualty detail beyond the existing deaths/injured/missing counts.
    ("people_affected", sa.Integer(), "0"),
    ("families_relocated", sa.Integer(), "0"),
    ("families_evacuated", sa.Integer(), "0"),
    # Physical damage.
    ("houses_destroyed", sa.Integer(), "0"),
    ("houses_affected", sa.Integer(), "0"),
    ("roads_destroyed", sa.Integer(), "0"),
    ("bridges_destroyed", sa.Integer(), "0"),
    ("livestock_destroyed", sa.Integer(), "0"),
    # Economic loss, all NPR. BIPAD reports infrastructure and agriculture
    # separately from the headline estimate, and often fills only one of them.
    ("infrastructure_loss_npr", sa.Float(), "0"),
    ("agriculture_loss_npr", sa.Float(), "0"),
]


def upgrade() -> None:
    for name, type_, default in _LOSS_COLUMNS:
        op.add_column(
            "disaster_incidents",
            sa.Column(name, type_, nullable=False, server_default=default),
        )

    # BIPAD's loss record id, so a sync can be retried without re-reading the
    # incident, and NULL cleanly means "never synced".
    op.add_column(
        "disaster_incidents",
        sa.Column("bipad_loss_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "disaster_incidents",
        sa.Column("loss_synced_at", sa.DateTime(timezone=True), nullable=True),
    )

    # The flood desk's hot path: "flood-family hazards in the last N days,
    # worst first". Partial index keeps it small — most incidents have no loss.
    op.create_index(
        "ix_incidents_loss_sync",
        "disaster_incidents",
        ["loss_synced_at"],
        postgresql_where=sa.text("loss_synced_at IS NULL"),
    )
    op.create_index(
        "ix_incidents_hazard_deaths",
        "disaster_incidents",
        ["hazard_type", "incident_on", "deaths"],
    )


def downgrade() -> None:
    op.drop_index("ix_incidents_hazard_deaths", table_name="disaster_incidents")
    op.drop_index("ix_incidents_loss_sync", table_name="disaster_incidents")
    op.drop_column("disaster_incidents", "loss_synced_at")
    op.drop_column("disaster_incidents", "bipad_loss_id")
    for name, _type, _default in reversed(_LOSS_COLUMNS):
        op.drop_column("disaster_incidents", name)
