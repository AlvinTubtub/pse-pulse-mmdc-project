"""0004_change_daily_price_volume_to_numeric

Revision ID: 0004_change_daily_price_volume_to_numeric
Revises: 0003_add_historical_bootstrap_provenance
Create Date: 2026-10-02 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004_change_daily_price_volume_to_numeric'
down_revision: Union[str, None] = '0003_add_historical_bootstrap_provenance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('daily_prices', schema=None) as batch_op:
        batch_op.alter_column(
            'volume',
            existing_type=sa.BigInteger(),
            type_=sa.Numeric(precision=20, scale=4),
            existing_nullable=False,
            existing_server_default=sa.text('0'),
        )


def downgrade() -> None:
    with op.batch_alter_table('daily_prices', schema=None) as batch_op:
        batch_op.alter_column(
            'volume',
            existing_type=sa.Numeric(precision=20, scale=4),
            type_=sa.BigInteger(),
            existing_nullable=False,
            existing_server_default=sa.text('0'),
        )
