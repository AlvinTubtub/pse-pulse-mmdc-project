"""Real serving requires exact pre-activated artifact lineage and never registers rows."""

from datetime import date
import inspect

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.forecasting.real.calendar import PSETradingCalendar
from backend.app.forecasting.real.config import ModelId
from backend.app.forecasting.real.domain import CompanyNextDayForecast, NextDayPrediction, OhlcvRecord
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.price import DailyPrice
from backend.app.models.sector import Sector
from backend.app.services import real_forecast_service as service_module
from backend.app.services.real_forecast_service import RealForecastingError, RealForecastService, RealModelsDisabledError

BUNDLE = "2026.10.01-authoritative-v1"
FAMILIES = ("LAG_REGRESSION", "ARIMA", "LSTM")
MODEL_IDS = {
    "LAG_REGRESSION": ModelId.LAG_REGRESSION,
    "ARIMA": ModelId.ARIMA,
    "LSTM": ModelId.LSTM,
}


def test_default_runtime_model_set_includes_all_three_families():
    default = inspect.signature(RealForecastService.generate_and_persist_forecasts).parameters["model_codes"].default
    assert default == (ModelId.LAG_REGRESSION.value, ModelId.ARIMA.value, ModelId.LSTM.value)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Sector(id=1, name="Property", code="PROP"))
    session.add_all([
        ModelMetadata(id=1, name="LIR", code="LAG_REGRESSION", version="0.1.0-stub", is_active=True),
        ModelMetadata(id=2, name="ARIMA", code="ARIMA", version="0.1.0-stub", is_active=True),
        ModelMetadata(id=3, name="LSTM", code="LSTM", version="0.1.0-stub", is_active=True),
    ])
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def real_enabled(monkeypatch):
    from backend.app.config import get_settings
    monkeypatch.setenv("REAL_MODELS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _setup_service(monkeypatch, db, tmp_path, *, active=True, tamper=None):
    symbol = "BPI"
    root = tmp_path / "candidate"
    (root / BUNDLE).mkdir(parents=True)
    company = Company(id=1, symbol=symbol, name="Bank", sector_id=1, is_active=True)
    db.add(company)
    history = []
    for day in range(1, 41):
        close = 100.0 + day * 0.25
        record = OhlcvRecord(date(2025, 1, 1).fromordinal(date(2025, 1, 1).toordinal() + day - 1), close, close + 1, close - 1, close, 1000)
        history.append(record)
        db.add(DailyPrice(company_id=1, trade_date=record.trading_date, open_price=close, high_price=close + 1, low_price=close - 1, close_price=close, volume=1000))
    db.flush()
    entries, loaded = [], {}
    for index, family in enumerate(FAMILIES):
        artifact_format = "pytorch_state_dict" if family == "LSTM" else "joblib"
        artifact_filename = "lstm.pt" if family == "LSTM" else f"{family.lower()}.joblib"
        artifact_sha256 = {"LAG_REGRESSION": "a", "ARIMA": "b", "LSTM": "c"}[family] * 64
        meta = {
            "symbol": symbol, "model_code": family, "model_version": BUNDLE,
            "artifact_format": artifact_format, "artifact_filename": artifact_filename,
            "artifact_sha256": artifact_sha256,
            "trained_through": history[19].trading_date.isoformat(), "data_row_count": 20,
            "hyperparameters": {}, "source_repository": "https://github.com/official/source.git",
            "source_commit": "b" * 40, "historical_data_source_repository": "https://github.com/official/source.git",
            "historical_data_source_commit": "b" * 40,
        }
        entry = {
            "symbol": symbol, "model_code": family, "model_version": BUNDLE,
            "artifact_format": artifact_format, "artifact_relative_path": f"{symbol}/{artifact_filename}",
            "artifact_sha256": meta["artifact_sha256"], "trained_through": meta["trained_through"], "data_row_count": 20,
        }
        entries.append(entry)
        loaded[family] = (object(), meta)
        if active:
            model_row = ModelArtifact(
                id=f"artifact-{family}", company_id=1, model_metadata_id=index + 1,
                bundle_version=BUNDLE, artifact_format=artifact_format, artifact_path=entry["artifact_relative_path"],
                artifact_sha256=entry["artifact_sha256"], trained_through=date.fromisoformat(entry["trained_through"]),
                data_row_count=20, hyperparameters_json="{}", source_repository=meta["source_repository"],
                source_commit=meta["source_commit"], historical_data_source_repository=meta["historical_data_source_repository"],
                historical_data_source_commit=meta["historical_data_source_commit"], is_active=True,
            )
            if tamper and family == "LAG_REGRESSION":
                setattr(model_row, tamper, date(2024, 1, 1) if tamper == "trained_through" else "wrong")
            db.add(model_row)
    if active:
        db.commit()

    monkeypatch.setattr(service_module, "read_verified_manifest", lambda *a, **k: ({"entries": entries}, "c" * 64))
    monkeypatch.setattr(service_module, "load_runtime_artifact", lambda **kwargs: type("Loaded", (), {"model": loaded[kwargs["model_code"]][0], "metadata": loaded[kwargs["model_code"]][1]})())
    def fake_predict(symbol, records, loaded_artifacts, *, calendar):
        origin = records[-1]
        target = calendar.next_trading_day(origin.trading_date)
        predictions = tuple(NextDayPrediction(
            symbol=symbol, model=MODEL_IDS[family],
            origin_date=origin.trading_date, forecast_for=target, origin_close=origin.close,
            predicted_delta=0.5, predicted_close=origin.close + 0.5,
            inference_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            model_artifact_id=None, bundle_version=BUNDLE,
        ) for family in FAMILIES)
        return CompanyNextDayForecast(symbol, origin.trading_date, target, predictions)
    monkeypatch.setattr(service_module, "predict_next_day_with_artifacts", fake_predict)
    return root, history


def test_disabled_real_forecasting_stays_disabled(monkeypatch, db_session, tmp_path):
    from backend.app.config import get_settings
    monkeypatch.setenv("REAL_MODELS_ENABLED", "false")
    get_settings.cache_clear()
    root, _ = _setup_service(monkeypatch, db_session, tmp_path)
    with pytest.raises(RealModelsDisabledError):
        RealForecastService(db_session).generate_and_persist_forecasts(root, BUNDLE, target_symbols=["BPI"], model_codes=FAMILIES)


@pytest.mark.parametrize("tamper", ["artifact_sha256", "artifact_path", "artifact_format", "bundle_version", "trained_through", "data_row_count", "source_commit"])
def test_serving_rejects_mismatched_active_lineage(monkeypatch, db_session, tmp_path, tamper):
    root, _ = _setup_service(monkeypatch, db_session, tmp_path, tamper=tamper)
    with pytest.raises(RealForecastingError, match="lineage mismatch"):
        RealForecastService(db_session).generate_and_persist_forecasts(root, BUNDLE, target_symbols=["BPI"], model_codes=FAMILIES)


def test_serving_rejects_missing_and_duplicate_active_rows(monkeypatch, db_session, tmp_path):
    root, _ = _setup_service(monkeypatch, db_session, tmp_path, active=False)
    with pytest.raises(RealForecastingError, match="exactly one active"):
        RealForecastService(db_session).generate_and_persist_forecasts(root, BUNDLE, target_symbols=["BPI"], model_codes=FAMILIES)


def test_serving_rejects_duplicate_active_lineage(monkeypatch, db_session, tmp_path):
    root, _ = _setup_service(monkeypatch, db_session, tmp_path)
    original = db_session.query(ModelArtifact).filter_by(id="artifact-LAG_REGRESSION").one()
    duplicate = ModelArtifact(
        id="older-active", company_id=original.company_id, model_metadata_id=original.model_metadata_id,
        bundle_version="older-bundle", artifact_format=original.artifact_format,
        artifact_path=original.artifact_path, artifact_sha256=original.artifact_sha256,
        trained_through=original.trained_through, data_row_count=original.data_row_count,
        hyperparameters_json=original.hyperparameters_json, source_repository=original.source_repository,
        source_commit=original.source_commit, historical_data_source_repository=original.historical_data_source_repository,
        historical_data_source_commit=original.historical_data_source_commit, is_active=True,
    )
    db_session.add(duplicate)
    db_session.commit()
    with pytest.raises(RealForecastingError, match="exactly one active"):
        RealForecastService(db_session).generate_and_persist_forecasts(root, BUNDLE, target_symbols=["BPI"], model_codes=FAMILIES)


def test_valid_active_lineage_serves_without_creating_artifact_rows(monkeypatch, db_session, tmp_path):
    root, _ = _setup_service(monkeypatch, db_session, tmp_path)
    before_artifacts = db_session.query(ModelArtifact).count()
    summary = RealForecastService(db_session).generate_and_persist_forecasts(root, BUNDLE, target_symbols=["BPI"], model_codes=FAMILIES)
    assert summary.total_forecasts_generated == 3
    assert summary.total_forecasts_persisted == 3
    non_demo_forecasts = db_session.query(Forecast).filter(Forecast.is_demo.is_(False))
    assert non_demo_forecasts.count() == 3
    persisted_families = {
        metadata.code
        for metadata in db_session.query(ModelMetadata)
        .join(Forecast, Forecast.model_id == ModelMetadata.id)
        .filter(Forecast.is_demo.is_(False))
        .all()
    }
    assert persisted_families == {"LAG_REGRESSION", "ARIMA", "LSTM"}
    assert db_session.query(ModelArtifact).count() == before_artifacts
    assert db_session.query(PipelineRun).filter(PipelineRun.is_demo_run.is_(False)).count() == 1
