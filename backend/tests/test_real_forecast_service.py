"""Unit tests for RealForecastService atomic persistence, rollback, lineage, and safety gating."""

from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.forecasting.real.artifacts.schema import (
    ModelArtifactCompatibilityError,
    OFFICIAL_SOURCE_COMMIT,
    OFFICIAL_SOURCE_REPOSITORY,
)
from backend.app.forecasting.real.artifacts.writer import persist_model_artifact
from backend.app.forecasting.real.config import (
    DEFAULT_ARIMA_CONFIG,
    DEFAULT_LAG_REGRESSION_CONFIG,
    ModelId,
)
from backend.app.forecasting.real.features.regression_features import build_regression_dataset
from backend.app.forecasting.real.models.arima import ArimaSpecification
from backend.app.forecasting.real.training.refit_arima import refit_arima_for_production
from backend.app.forecasting.real.training.refit_lir import refit_lir_for_production
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.price import DailyPrice
from backend.app.models.sector import Sector
from backend.app.services.real_forecast_service import (
    RealForecastIntegrityError,
    RealForecastService,
    RealForecastingError,
    RealModelsDisabledError,
)
from backend.tests.test_real_models import _generate_synthetic_series


@pytest.fixture(autouse=True)
def enable_real_models(monkeypatch):
    """Enable real models by default in tests unless explicitly overridden."""
    monkeypatch.setenv("REAL_MODELS_ENABLED", "true")
    from backend.app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_db_session():
    """Create in-memory SQLite database session with complete schema."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed sector
    sec = Sector(id=1, name="Banking", code="FIN")
    session.add(sec)

    # Seed model metadata
    m_lir = ModelMetadata(id=1, name="Lag-Informed Regression", code="LAG_REGRESSION", version="1.0.0", is_active=True)
    m_arima = ModelMetadata(id=2, name="ARIMA", code="ARIMA", version="1.0.0", is_active=True)
    session.add_all([m_lir, m_arima])
    session.commit()

    yield session
    session.close()


def _populate_company_and_artifacts(
    session,
    artifacts_root: Path,
    bundle_version: str,
    symbol: str,
    company_id: int,
    start_price: float = 100.0,
):
    """Seed company, prices, and persisted artifacts for a given symbol."""
    comp = Company(id=company_id, symbol=symbol, name=f"{symbol} Corp", sector_id=1, is_active=True)
    session.add(comp)
    session.flush()

    records = _generate_synthetic_series(60, start_price=start_price)
    for r in records:
        dp = DailyPrice(
            company_id=comp.id,
            trade_date=r.trading_date,
            open_price=Decimal(str(r.open)),
            high_price=Decimal(str(r.high)),
            low_price=Decimal(str(r.low)),
            close_price=Decimal(str(r.close)),
            volume=Decimal(str(r.volume)),
        )
        session.add(dp)
    session.commit()

    # Persist artifacts to disk
    sym_dir = artifacts_root / bundle_version / symbol
    sym_dir.mkdir(parents=True, exist_ok=True)
    trained_through = records[-1].trading_date
    row_count = len(records)

    # LIR
    dataset = build_regression_dataset(records, DEFAULT_LAG_REGRESSION_CONFIG.features)
    fitted_lir = refit_lir_for_production(dataset, chosen_alpha=0.01)
    persist_model_artifact(
        output_directory=sym_dir,
        symbol=symbol,
        model_code="LAG_REGRESSION",
        model_version=bundle_version,
        fitted_model=fitted_lir,
        hyperparameters={
            "alpha": 0.01,
            "feature_names": list(fitted_lir.fit_metadata.feature_names),
            "pacf_selected_lags": list(fitted_lir.pacf_selected_lags),
        },
        trained_through=trained_through,
        data_row_count=row_count,
    )

    # ARIMA
    spec = ArimaSpecification(order=(1, 1, 0), trend="n")
    fitted_arima = refit_arima_for_production(records, selected_specification=spec)
    persist_model_artifact(
        output_directory=sym_dir,
        symbol=symbol,
        model_code="ARIMA",
        model_version=bundle_version,
        fitted_model=fitted_arima.model,
        hyperparameters={"order": [1, 1, 0], "trend": "n"},
        trained_through=trained_through,
        data_row_count=row_count,
    )


def test_atomic_forecast_persistence_and_lineage(test_db_session, tmp_path):
    """Verify that forecasting across companies persists all forecasts atomically with full lineage."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    # Seed 2 companies (BPI and BDO) -> 2 companies x 2 models = 4 forecasts
    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)
    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BDO", 2, 140.0)

    service = RealForecastService(db=test_db_session)
    summary = service.generate_and_persist_forecasts(
        artifacts_root=artifacts_root,
        bundle_version=bundle_version,
        target_symbols=["BPI", "BDO"],
    )

    assert summary.status == "COMPLETED"
    assert summary.total_forecasts_generated == 4
    assert summary.total_forecasts_persisted == 4

    # Verify forecasts in DB
    fcs = test_db_session.query(Forecast).all()
    assert len(fcs) == 4
    for fc in fcs:
        assert fc.is_demo is False
        assert fc.model_artifact_id is not None
        assert fc.origin_date is not None
        assert fc.predicted_delta is not None
        assert fc.predicted_price is not None
        assert fc.pipeline_run_id is not None

    # Verify ModelArtifact records in DB with complete lineage
    db_arts = test_db_session.query(ModelArtifact).all()
    assert len(db_arts) == 4  # 2 companies * 2 models
    for art in db_arts:
        assert art.historical_data_source_repository == OFFICIAL_SOURCE_REPOSITORY
        assert art.historical_data_source_commit == OFFICIAL_SOURCE_COMMIT
        assert art.source_repository == OFFICIAL_SOURCE_REPOSITORY
        assert art.source_commit == OFFICIAL_SOURCE_COMMIT
        assert art.is_active is True


def test_identical_rerun_idempotent_unchanged(test_db_session, tmp_path):
    """Verify identical rerun returns UNCHANGED with 0 updates and 0 inserts."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)

    service = RealForecastService(db=test_db_session)
    first_summary = service.generate_and_persist_forecasts(
        artifacts_root=artifacts_root,
        bundle_version=bundle_version,
        target_symbols=["BPI"],
    )
    assert first_summary.total_forecasts_persisted == 2
    assert test_db_session.query(Forecast).count() == 2

    # Second identical run
    second_summary = service.generate_and_persist_forecasts(
        artifacts_root=artifacts_root,
        bundle_version=bundle_version,
        target_symbols=["BPI"],
    )
    assert second_summary.status == "COMPLETED"
    assert second_summary.total_forecasts_persisted == 0
    assert second_summary.total_forecasts_unchanged == 2
    for item in second_summary.items:
        assert item.status == "UNCHANGED"

    # DB records count must remain exactly 2 with 0 mutations
    assert test_db_session.query(Forecast).count() == 2


def test_differing_rerun_raises_real_forecast_integrity_error(test_db_session, tmp_path):
    """Verify that a forecast rerun with differing price or delta raises RealForecastIntegrityError."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)

    service = RealForecastService(db=test_db_session)
    service.generate_and_persist_forecasts(
        artifacts_root=artifacts_root,
        bundle_version=bundle_version,
        target_symbols=["BPI"],
    )

    # Tamper with the persisted forecast price directly in the database
    first_fc = test_db_session.query(Forecast).first()
    first_fc.predicted_price = Decimal("9999.9999")
    test_db_session.commit()

    with pytest.raises(RealForecastIntegrityError, match="Real forecast integrity violation"):
        service.generate_and_persist_forecasts(
            artifacts_root=artifacts_root,
            bundle_version=bundle_version,
            target_symbols=["BPI"],
        )


def test_cross_company_artifact_rejected(test_db_session, tmp_path):
    """Verify that an artifact belonging to another symbol is rejected."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    # Seed BPI in DB, but populate artifacts under BPI folder that claim symbol 'ALI'
    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)

    # Tamper with the companion metadata to claim symbol ALI
    meta_path = artifacts_root / bundle_version / "BPI" / "lag_regression.metadata.json"
    meta_data = json.loads(meta_path.read_text(encoding="utf-8"))
    meta_data["symbol"] = "ALI"
    meta_path.write_text(json.dumps(meta_data), encoding="utf-8")

    service = RealForecastService(db=test_db_session)
    with pytest.raises(RealForecastingError, match="symbol mismatch"):
        service.generate_and_persist_forecasts(
            artifacts_root=artifacts_root,
            bundle_version=bundle_version,
            target_symbols=["BPI"],
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_code", "LAG_REGRESSION", "model_code mismatch"),
        ("model_version", "wrong-version", "model_version mismatch"),
    ],
)
def test_artifact_family_and_version_mismatch_rejected(
    test_db_session, tmp_path, field, value, message
):
    """Reject an artifact from another model family or requested bundle version."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"
    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1)

    meta_path = artifacts_root / bundle_version / "BPI" / "arima.metadata.json"
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    payload[field] = value
    meta_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RealForecastingError, match=message):
        RealForecastService(db=test_db_session).generate_and_persist_forecasts(
            artifacts_root=artifacts_root,
            bundle_version=bundle_version,
            target_symbols=["BPI"],
        )
    assert test_db_session.query(Forecast).filter(Forecast.is_demo.is_(False)).count() == 0


def test_successful_complete_synthetic_run_persists_15_by_2(test_db_session, tmp_path):
    """All 15 synthetic companies produce two lineage-complete real forecasts each."""
    bundle_version = "complete-synthetic-v1"
    artifacts_root = tmp_path / "models"
    symbols = (
        "ALI", "APX", "BPI", "GLO", "ICT", "JFC", "MBT", "MEG", "MER",
        "NIKL", "PGOLD", "SCC", "SECB", "SHLPH", "SMPH",
    )
    for company_id, symbol in enumerate(symbols, start=1):
        _populate_company_and_artifacts(
            test_db_session, artifacts_root, bundle_version, symbol, company_id,
            start_price=100.0 + company_id,
        )

    summary = RealForecastService(db=test_db_session).generate_and_persist_forecasts(
        artifacts_root=artifacts_root,
        bundle_version=bundle_version,
    )
    forecasts = test_db_session.query(Forecast).filter(Forecast.is_demo.is_(False)).all()
    assert summary.total_forecasts_generated == 30
    assert summary.total_forecasts_persisted == 30
    assert len(forecasts) == 30
    assert len(test_db_session.query(ModelArtifact).all()) == 30
    assert all(
        forecast.model_artifact_id
        and forecast.origin_date
        and forecast.predicted_delta is not None
        and forecast.predicted_price is not None
        and forecast.is_demo is False
        for forecast in forecasts
    )


def test_demo_and_real_forecasts_coexist(test_db_session, tmp_path):
    """Verify demo forecasts (is_demo=True) and real forecasts (is_demo=False) cleanly coexist."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)

    # Seed demo forecast for BPI
    demo_fc = Forecast(
        company_id=1,
        model_id=1,
        model_artifact_id=None,
        origin_date=None,
        target_date=date(2026, 3, 2),
        predicted_price=Decimal("120.0000"),
        predicted_delta=Decimal("1.5000"),
        is_demo=True,
    )
    test_db_session.add(demo_fc)
    test_db_session.commit()

    service = RealForecastService(db=test_db_session)
    summary = service.generate_and_persist_forecasts(
        artifacts_root=artifacts_root,
        bundle_version=bundle_version,
        target_symbols=["BPI"],
    )
    assert summary.status == "COMPLETED"

    all_fcs = test_db_session.query(Forecast).all()
    demo_fcs = [f for f in all_fcs if f.is_demo is True]
    real_fcs = [f for f in all_fcs if f.is_demo is False]

    assert len(demo_fcs) == 1
    assert len(real_fcs) == 2
    assert demo_fcs[0].model_artifact_id is None
    for r in real_fcs:
        assert r.model_artifact_id is not None


def test_atomic_rollback_on_failure(test_db_session, tmp_path):
    """Verify that if one company fails, transaction rolls back and 0 forecasts are persisted."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)
    # Add a company with NO artifacts on disk to cause an error during batch
    bad_comp = Company(id=99, symbol="FAIL", name="Fail Corp", sector_id=1, is_active=True)
    test_db_session.add(bad_comp)
    test_db_session.commit()

    service = RealForecastService(db=test_db_session)
    with pytest.raises(RealForecastingError):
        service.generate_and_persist_forecasts(
            artifacts_root=artifacts_root,
            bundle_version=bundle_version,
            target_symbols=["BPI", "FAIL"],
        )

    # Database must contain 0 forecasts due to atomic rollback
    fcs = test_db_session.query(Forecast).all()
    assert len(fcs) == 0


def test_safety_gate_rejection_in_production(test_db_session, tmp_path, monkeypatch):
    """Verify that REAL_MODELS_ENABLED=False raises RealModelsDisabledError in production."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)

    # Set production environment and REAL_MODELS_ENABLED=False
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("REAL_MODELS_ENABLED", "false")

    from backend.app.config import get_settings
    get_settings.cache_clear()

    service = RealForecastService(db=test_db_session)
    try:
        with pytest.raises(RealModelsDisabledError, match="REAL_MODELS_ENABLED is False"):
            service.generate_and_persist_forecasts(
                artifacts_root=artifacts_root,
                bundle_version=bundle_version,
                target_symbols=["BPI"],
            )
    finally:
        get_settings.cache_clear()


def test_safety_gate_rejection_in_development(test_db_session, tmp_path, monkeypatch):
    """Verify that REAL_MODELS_ENABLED=False also raises RealModelsDisabledError in development."""
    bundle_version = "2026.03.01-v1"
    artifacts_root = tmp_path / "models"

    _populate_company_and_artifacts(test_db_session, artifacts_root, bundle_version, "BPI", 1, 115.0)

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("REAL_MODELS_ENABLED", "false")

    from backend.app.config import get_settings
    get_settings.cache_clear()

    service = RealForecastService(db=test_db_session)
    try:
        with pytest.raises(RealModelsDisabledError, match="REAL_MODELS_ENABLED is False"):
            service.generate_and_persist_forecasts(
                artifacts_root=artifacts_root,
                bundle_version=bundle_version,
                target_symbols=["BPI"],
            )
    finally:
        get_settings.cache_clear()
