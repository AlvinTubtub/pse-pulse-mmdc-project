"""Make future model artifact rows inactive by default.

Revision ID: 0006_model_artifacts_inactive_by_default
Revises: 0005_add_model_artifacts_and_forecast_lineage
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_model_artifacts_inactive_by_default"
down_revision: Union[str, None] = "0005_add_model_artifacts_and_forecast_lineage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter only the default. Existing explicit row values are preserved.
    with op.batch_alter_table("model_artifacts") as batch_op:
        batch_op.alter_column(
            "is_active",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=sa.text("false"),
        )


def downgrade() -> None:
    with op.batch_alter_table("model_artifacts") as batch_op:
        batch_op.alter_column(
            "is_active",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            server_default=sa.text("true"),
        )
