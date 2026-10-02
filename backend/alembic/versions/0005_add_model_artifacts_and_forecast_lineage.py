"""0005_add_model_artifacts_and_forecast_lineage

Revision ID: 0005_add_model_artifacts_and_forecast_lineage
Revises: 0004_change_daily_price_volume_to_numeric
Create Date: 2026-10-02 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005_add_model_artifacts_and_forecast_lineage'
down_revision: Union[str, None] = '0004_change_daily_price_volume_to_numeric'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create model_artifacts table
    op.create_table(
        'model_artifacts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('model_metadata_id', sa.Integer(), nullable=False),
        sa.Column('bundle_version', sa.String(length=50), nullable=False),
        sa.Column('artifact_format', sa.String(length=30), server_default='joblib', nullable=False),
        sa.Column('artifact_path', sa.String(length=500), nullable=False),
        sa.Column('artifact_sha256', sa.String(length=64), nullable=False),
        sa.Column('trained_through', sa.Date(), nullable=False),
        sa.Column('data_row_count', sa.Integer(), nullable=False),
        sa.Column('hyperparameters_json', sa.Text(), nullable=False),
        sa.Column('source_repository', sa.String(length=500), nullable=False),
        sa.Column('source_commit', sa.String(length=40), nullable=False),
        sa.Column('historical_data_source_repository', sa.String(length=500), nullable=False),
        sa.Column('historical_data_source_commit', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name='fk_model_artifacts_company_id'),
        sa.ForeignKeyConstraint(['model_metadata_id'], ['model_metadata.id'], name='fk_model_artifacts_model_metadata_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'model_metadata_id', 'bundle_version', name='uq_model_artifact_company_model_bundle'),
    )
    op.create_index('ix_model_artifacts_company_id', 'model_artifacts', ['company_id'], unique=False)
    op.create_index('ix_model_artifacts_model_metadata_id', 'model_artifacts', ['model_metadata_id'], unique=False)
    op.create_index('ix_model_artifacts_bundle_version', 'model_artifacts', ['bundle_version'], unique=False)
    op.create_index('ix_model_artifacts_artifact_sha256', 'model_artifacts', ['artifact_sha256'], unique=False)
    op.create_index('ix_model_artifacts_company_model', 'model_artifacts', ['company_id', 'model_metadata_id'], unique=False)

    # 2. Add nullable columns and foreign keys to forecasts table
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('model_artifact_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('origin_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('predicted_delta', sa.Numeric(precision=12, scale=4), nullable=True))
        batch_op.create_foreign_key('fk_forecasts_model_artifact_id', 'model_artifacts', ['model_artifact_id'], ['id'])
        batch_op.create_index('ix_forecasts_model_artifact_id', ['model_artifact_id'], unique=False)
        batch_op.create_index('ix_forecasts_origin_date', ['origin_date'], unique=False)


def downgrade() -> None:
    # 1. Drop added columns and indexes from forecasts
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.drop_index('ix_forecasts_origin_date')
        batch_op.drop_index('ix_forecasts_model_artifact_id')
        batch_op.drop_constraint('fk_forecasts_model_artifact_id', type_='foreignkey')
        batch_op.drop_column('predicted_delta')
        batch_op.drop_column('origin_date')
        batch_op.drop_column('model_artifact_id')

    # 2. Drop model_artifacts table
    op.drop_index('ix_model_artifacts_company_model', table_name='model_artifacts')
    op.drop_index('ix_model_artifacts_artifact_sha256', table_name='model_artifacts')
    op.drop_index('ix_model_artifacts_bundle_version', table_name='model_artifacts')
    op.drop_index('ix_model_artifacts_model_metadata_id', table_name='model_artifacts')
    op.drop_index('ix_model_artifacts_company_id', table_name='model_artifacts')
    op.drop_table('model_artifacts')
