"""0001_initial_schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-10-01 23:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. sectors table
    op.create_table(
        'sectors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sectors_id'), 'sectors', ['id'], unique=False)
    op.create_index(op.f('ix_sectors_name'), 'sectors', ['name'], unique=True)
    op.create_index(op.f('ix_sectors_code'), 'sectors', ['code'], unique=True)

    # 2. companies table
    op.create_table(
        'companies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('sector_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('listing_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['sector_id'], ['sectors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_companies_id'), 'companies', ['id'], unique=False)
    op.create_index(op.f('ix_companies_symbol'), 'companies', ['symbol'], unique=True)
    op.create_index(op.f('ix_companies_sector_id'), 'companies', ['sector_id'], unique=False)

    # 3. daily_prices table
    op.create_table(
        'daily_prices',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('open_price', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('high_price', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('low_price', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('close_price', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('volume', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('value', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'trade_date', name='uq_company_trade_date'),
    )
    op.create_index(op.f('ix_daily_prices_id'), 'daily_prices', ['id'], unique=False)
    op.create_index(op.f('ix_daily_prices_company_id'), 'daily_prices', ['company_id'], unique=False)
    op.create_index(op.f('ix_daily_prices_trade_date'), 'daily_prices', ['trade_date'], unique=False)
    op.create_index('ix_daily_prices_company_date', 'daily_prices', ['company_id', 'trade_date'], unique=False)

    # 4. model_metadata table (composite unique on code and version for multi-versioning)
    op.create_table(
        'model_metadata',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('version', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'version', name='uq_model_code_version'),
    )
    op.create_index(op.f('ix_model_metadata_id'), 'model_metadata', ['id'], unique=False)
    op.create_index(op.f('ix_model_metadata_code'), 'model_metadata', ['code'], unique=False)

    # 5. pipeline_runs table
    op.create_table(
        'pipeline_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('records_ingested', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('forecasts_generated', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('is_demo_run', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pipeline_runs_id'), 'pipeline_runs', ['id'], unique=False)
    op.create_index(op.f('ix_pipeline_runs_run_id'), 'pipeline_runs', ['run_id'], unique=True)
    op.create_index(op.f('ix_pipeline_runs_status'), 'pipeline_runs', ['status'], unique=False)

    # 6. forecasts table (includes pipeline_run_id for historical snapshots)
    op.create_table(
        'forecasts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('model_id', sa.Integer(), nullable=False),
        sa.Column('pipeline_run_id', sa.Integer(), nullable=True),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column('predicted_price', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('lower_bound', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('upper_bound', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('confidence_level', sa.Float(), nullable=False, server_default=sa.text('0.95')),
        sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['model_id'], ['model_metadata.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'model_id', 'target_date', 'pipeline_run_id', name='uq_forecast_company_model_date_run'),
    )
    op.create_index(op.f('ix_forecasts_id'), 'forecasts', ['id'], unique=False)
    op.create_index(op.f('ix_forecasts_company_id'), 'forecasts', ['company_id'], unique=False)
    op.create_index(op.f('ix_forecasts_model_id'), 'forecasts', ['model_id'], unique=False)
    op.create_index(op.f('ix_forecasts_pipeline_run_id'), 'forecasts', ['pipeline_run_id'], unique=False)
    op.create_index(op.f('ix_forecasts_target_date'), 'forecasts', ['target_date'], unique=False)
    op.create_index('ix_forecasts_company_target_date', 'forecasts', ['company_id', 'target_date'], unique=False)


def downgrade() -> None:
    op.drop_table('forecasts')
    op.drop_table('pipeline_runs')
    op.drop_table('model_metadata')
    op.drop_table('daily_prices')
    op.drop_table('companies')
    op.drop_table('sectors')
