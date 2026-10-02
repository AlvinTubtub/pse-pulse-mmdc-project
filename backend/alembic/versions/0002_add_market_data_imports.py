"""0002_add_market_data_imports

Revision ID: 0002_add_market_data_imports
Revises: 0001_initial_schema
Create Date: 2026-10-02 11:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_add_market_data_imports'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'market_data_imports',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_type', sa.String(length=64), nullable=False, server_default='PSE_DQR_FILE'),
        sa.Column('source_filename', sa.String(length=255), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=True),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='COMPLETED'),
        sa.Column('records_seen', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_valid', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_inserted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_rejected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_market_data_imports_id'), 'market_data_imports', ['id'], unique=False)
    op.create_index(op.f('ix_market_data_imports_sha256'), 'market_data_imports', ['sha256'], unique=False)
    op.create_index(op.f('ix_market_data_imports_trade_date'), 'market_data_imports', ['trade_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_market_data_imports_trade_date'), table_name='market_data_imports')
    op.drop_index(op.f('ix_market_data_imports_sha256'), table_name='market_data_imports')
    op.drop_index(op.f('ix_market_data_imports_id'), table_name='market_data_imports')
    op.drop_table('market_data_imports')
