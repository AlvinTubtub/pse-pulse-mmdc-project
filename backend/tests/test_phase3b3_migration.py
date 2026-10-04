"""0006 changes only the future is_active default and preserves stored values."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def test_model_artifact_default_migration_upgrade_downgrade_upgrade(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    database = tmp_path / "migration.sqlite"
    config = Config(str(repo / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(repo / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    command.upgrade(config, "0005_add_model_artifacts_and_forecast_lineage")
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO sectors (id,name,code,created_at) VALUES (1,'Property','PROP','2026-01-01 00:00:00')"))
        connection.execute(text("INSERT INTO companies (id,symbol,name,sector_id,created_at,updated_at) VALUES (1,'ALI','ALI',1,'2026-01-01 00:00:00','2026-01-01 00:00:00')"))
        for model_id, family in ((1, "LAG_REGRESSION"), (2, "ARIMA")):
            connection.execute(text("INSERT INTO model_metadata (id,name,code,version,created_at) VALUES (:id,:name,:code,'v1','2026-01-01 00:00:00')"), {"id": model_id, "name": family, "code": family})
            connection.execute(text("""INSERT INTO model_artifacts (id,company_id,model_metadata_id,bundle_version,artifact_format,artifact_path,artifact_sha256,trained_through,data_row_count,hyperparameters_json,source_repository,source_commit,historical_data_source_repository,historical_data_source_commit,is_active)
                VALUES (:id,1,:model_id,'old-v1','joblib','ALI/model.joblib',:sha,'2025-01-01',10,'{}','src',:commit,'src',:commit,:active)"""), {"id": f"old-{model_id}", "model_id": model_id, "sha": str(model_id) * 64, "commit": "a" * 40, "active": bool(model_id == 1)})
    command.upgrade(config, "head")
    with engine.begin() as connection:
        values = connection.execute(text("SELECT id,is_active FROM model_artifacts ORDER BY id")).all()
        assert values == [("old-1", 1), ("old-2", 0)]
        connection.execute(text("""INSERT INTO model_artifacts (id,company_id,model_metadata_id,bundle_version,artifact_format,artifact_path,artifact_sha256,trained_through,data_row_count,hyperparameters_json,source_repository,source_commit,historical_data_source_repository,historical_data_source_commit)
            VALUES ('new-1',1,1,'new-v1','joblib','ALI/model.joblib',:sha,'2026-01-01',10,'{}','src',:commit,'src',:commit)"""), {"sha": "c" * 64, "commit": "b" * 40})
        assert connection.execute(text("SELECT is_active FROM model_artifacts WHERE id='new-1'")).scalar_one() == 0
    command.downgrade(config, "0005_add_model_artifacts_and_forecast_lineage")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT id,is_active FROM model_artifacts ORDER BY id")).all() == [("new-1", 0), ("old-1", 1), ("old-2", 0)]
        connection.execute(text("""INSERT INTO model_artifacts (id,company_id,model_metadata_id,bundle_version,artifact_format,artifact_path,artifact_sha256,trained_through,data_row_count,hyperparameters_json,source_repository,source_commit,historical_data_source_repository,historical_data_source_commit)
            VALUES ('downgrade-default',1,2,'new-v2','joblib','ALI/model.joblib',:sha,'2026-01-01',10,'{}','src',:commit,'src',:commit)"""), {"sha": "d" * 64, "commit": "c" * 40})
        assert connection.execute(text("SELECT is_active FROM model_artifacts WHERE id='downgrade-default'")).scalar_one() == 1
    command.upgrade(config, "head")
    engine.dispose()
