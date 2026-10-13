"""Add explicit production trading-session status and provenance ledger.

Revision ID: 0007_production_session_ledger
Revises: 0006_model_artifacts_inactive_by_default
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_production_session_ledger"
down_revision = "0006_model_artifacts_inactive_by_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("calendar_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("source_reviewer", sa.String(length=120), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('NON_TRADING', 'PENDING_SOURCE', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_production_sessions_status",
        ),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_date"),
    )
    op.create_index("ix_production_sessions_status", "production_sessions", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_production_sessions_status", table_name="production_sessions")
    op.drop_table("production_sessions")
