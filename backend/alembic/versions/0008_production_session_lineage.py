"""Bind completed production sessions to their import and model bundle.

Revision ID: 0008_production_session_lineage
Revises: 0007_production_session_ledger
Create Date: 2026-10-09
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_production_session_lineage"
down_revision = "0007_production_session_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("production_sessions") as batch_op:
        batch_op.add_column(sa.Column("market_data_import_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("model_bundle_version", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("model_manifest_sha256", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_production_sessions_market_data_import_id",
            "market_data_imports",
            ["market_data_import_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("production_sessions") as batch_op:
        batch_op.drop_constraint(
            "fk_production_sessions_market_data_import_id",
            type_="foreignkey",
        )
        batch_op.drop_column("model_manifest_sha256")
        batch_op.drop_column("model_bundle_version")
        batch_op.drop_column("market_data_import_id")
