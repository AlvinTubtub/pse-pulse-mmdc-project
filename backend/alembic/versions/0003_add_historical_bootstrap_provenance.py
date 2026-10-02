"""0003_add_historical_bootstrap_provenance

Revision ID: 0003_add_historical_bootstrap_provenance
Revises: 0002_add_market_data_imports
Create Date: 2026-10-02 13:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003_add_historical_bootstrap_provenance'
down_revision: Union[str, None] = '0002_add_market_data_imports'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('market_data_imports', sa.Column('source_repository', sa.String(length=255), nullable=True))
    op.add_column('market_data_imports', sa.Column('source_commit', sa.String(length=64), nullable=True))
    op.add_column('market_data_imports', sa.Column('source_path', sa.String(length=255), nullable=True))
    op.add_column('market_data_imports', sa.Column('symbol', sa.String(length=20), nullable=True))
    op.add_column('market_data_imports', sa.Column('first_trade_date', sa.Date(), nullable=True))
    op.add_column('market_data_imports', sa.Column('last_trade_date', sa.Date(), nullable=True))
    op.add_column('market_data_imports', sa.Column('records_unchanged', sa.Integer(), nullable=False, server_default='0'))
    op.create_index(op.f('ix_market_data_imports_symbol'), 'market_data_imports', ['symbol'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_market_data_imports_symbol'), table_name='market_data_imports')
    op.drop_column('market_data_imports', 'records_unchanged')
    op.drop_column('market_data_imports', 'last_trade_date')
    op.drop_column('market_data_imports', 'first_trade_date')
    op.drop_column('market_data_imports', 'symbol')
    op.drop_column('market_data_imports', 'source_path')
    op.drop_column('market_data_imports', 'source_commit')
    op.drop_column('market_data_imports', 'source_repository')
