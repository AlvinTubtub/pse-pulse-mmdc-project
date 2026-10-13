"""Offline integration coverage for production EOD lineage and transaction gates."""

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.market_data_import import MarketDataImport
from backend.app.models.model_artifact import ModelArtifact
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.price import DailyPrice
from backend.app.models.production_session import ProductionSession
from backend.app.models.sector import Sector
from backend.app.production_inputs import ApprovedCalendar, ProductionInputError
from backend.pipeline import production_runner as runner


TRADE_DATE = date(2026, 10, 8)
TARGET_DATE = date(2026, 10, 12)
SOURCE_SHA = "a" * 64
SOURCE_MANIFEST_SHA = "b" * 64
MODEL_MANIFEST_SHA = "c" * 64
BUNDLE = "offline-approved-bundle"
MODEL_CODES = ("LAG_REGRESSION", "ARIMA", "LSTM")


@pytest.fixture
def completed_session_fixture(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Sector(id=1, name="Technology", code="TECH"))
    company = Company(id=1, symbol="ALI", name="Offline Fixture", sector_id=1, is_active=True)
    db.add(company)
    db.add(DailyPrice(
        id=1, company_id=company.id, trade_date=TRADE_DATE, open_price=100,
        high_price=101, low_price=99, close_price=100, volume=1000,
    ))
    metadata = [
        ModelMetadata(id=index, name=code, code=code, version="fixture", is_active=True)
        for index, code in enumerate(MODEL_CODES, 1)
    ]
    db.add_all(metadata)
    imported = MarketDataImport(
        id=1, source_type="PSE_DQR_FILE", source_filename="fixture.txt", trade_date=TRADE_DATE,
        sha256=SOURCE_SHA, status="COMPLETED", records_seen=10, records_valid=10,
        records_inserted=10, records_updated=0, records_unchanged=0, records_rejected=0,
    )
    run = PipelineRun(
        id=1, run_id="offline-completed-run", status="COMPLETED", is_demo_run=False,
        started_at=datetime(2026, 10, 8, 10, tzinfo=timezone.utc),
        completed_at=datetime(2026, 10, 8, 11, tzinfo=timezone.utc),
        records_ingested=10, forecasts_generated=len(MODEL_CODES), error_message=None,
    )
    db.add_all([imported, run])

    manifest_entries = []
    artifacts = []
    forecasts = []
    for index, code in enumerate(MODEL_CODES, 1):
        artifact_id = f"artifact-{code}"
        artifact_sha = str(index) * 64
        artifact_format = "pytorch_state_dict" if code == "LSTM" else "joblib"
        artifact_path = f"ALI/{code.lower()}.artifact"
        trained_through = date(2025, 9, 30)
        manifest_entries.append({
            "symbol": "ALI", "model_code": code, "artifact_format": artifact_format,
            "artifact_relative_path": artifact_path, "artifact_sha256": artifact_sha,
            "trained_through": trained_through.isoformat(), "data_row_count": 100,
        })
        artifacts.append(ModelArtifact(
            id=artifact_id, company_id=company.id, model_metadata_id=index,
            bundle_version=BUNDLE, artifact_format=artifact_format, artifact_path=artifact_path,
            artifact_sha256=artifact_sha, trained_through=trained_through, data_row_count=100,
            hyperparameters_json="{}", source_repository="https://github.com/official/source.git",
            source_commit="d" * 40, historical_data_source_repository="https://github.com/official/source.git",
            historical_data_source_commit="e" * 40, is_active=False,
        ))
        forecasts.append(Forecast(
            id=index, company_id=company.id, model_id=index, model_artifact_id=artifact_id,
            pipeline_run_id=run.id, origin_date=TRADE_DATE, target_date=TARGET_DATE,
            predicted_price=101.25, predicted_delta=0.25, confidence_level=0.95, is_demo=False,
        ))
    db.add_all(artifacts + forecasts)

    source_manifest = tmp_path / "approved-source.json"
    payload = {
        "schema_version": 1, "source_type": "PSE_DQR", "source_url": "https://www.pse.com.ph/fixture",
        "trade_date": TRADE_DATE.isoformat(), "retrieved_at": "2026-10-08T18:30:00+08:00",
        "reviewed_by": "offline-review-fixture", "file_sha256": SOURCE_SHA,
    }
    source_manifest.write_text(json.dumps(payload), encoding="utf-8")
    source_manifest.chmod(0o640)
    actual_source_manifest_sha = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    session_row = ProductionSession(
        id=1, trade_date=TRADE_DATE, status="COMPLETED", calendar_sha256="f" * 64,
        source_sha256=SOURCE_SHA, source_manifest_sha256=actual_source_manifest_sha,
        source_url=payload["source_url"], source_reviewer=payload["reviewed_by"],
        market_data_import_id=imported.id, model_bundle_version=BUNDLE,
        model_manifest_sha256=MODEL_MANIFEST_SHA, pipeline_run_id=run.id,
        message="offline fixture",
    )
    db.add(session_row)
    db.commit()

    manifest = {"symbols": ["ALI"], "entries": manifest_entries}
    monkeypatch.setattr(runner, "read_verified_manifest", lambda *a, **k: (manifest, MODEL_MANIFEST_SHA))
    monkeypatch.setattr(runner, "read_verified_artifact_metadata", lambda bundle_root, entry: {
        "source_repository": "https://github.com/official/source.git",
        "source_commit": "d" * 40,
        "historical_data_source_repository": "https://github.com/official/source.git",
        "historical_data_source_commit": "e" * 40,
        "hyperparameters": {},
    })
    calendar = ApprovedCalendar(
        "f" * 64, TRADE_DATE, TARGET_DATE, frozenset({TRADE_DATE, TARGET_DATE})
    )
    state = SimpleNamespace(
        db=db, engine=engine, company=company, imported=imported, run=run,
        forecasts=forecasts, artifacts=artifacts, session=session_row,
        manifest=manifest, calendar=calendar, source_manifest=source_manifest,
        source_manifest_sha=actual_source_manifest_sha,
    )
    yield state
    db.close()
    engine.dispose()


def test_completed_session_recheck_accepts_complete_approved_lineage(completed_session_fixture):
    state = completed_session_fixture
    runner._verify_completed_session(
        state.db, state.session, TRADE_DATE, state.calendar,
        state.source_manifest, state.source_manifest_sha, Path("/offline/bundles"),
    )


def test_production_session_date_lock_uses_postgres_transaction_advisory_lock():
    calls = []

    class FakeSession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))

    runner._lock_production_session_date(FakeSession(), TRADE_DATE)
    assert len(calls) == 1
    statement, parameters = calls[0]
    assert "pg_advisory_xact_lock" in statement
    assert parameters == {
        "namespace": runner.PRODUCTION_SESSION_LOCK_NAMESPACE,
        "session_date": TRADE_DATE.toordinal(),
    }


def test_running_production_session_rejects_retry(completed_session_fixture):
    state = completed_session_fixture
    state.session.status = "RUNNING"
    state.db.commit()
    with pytest.raises(runner.ProductionRunError, match="already running"):
        runner.run_session(
            state.db, TRADE_DATE, state.calendar, None, None, None,
            SimpleNamespace(), Path("/offline/bundles"), BUNDLE,
        )
    assert state.session.status == "RUNNING"


def test_failed_production_session_requires_explicit_retry(completed_session_fixture):
    state = completed_session_fixture
    state.session.status = "FAILED"
    state.db.commit()
    with pytest.raises(runner.ProductionRunError, match="explicit owner-authorized retry"):
        runner.run_session(
            state.db, TRADE_DATE, state.calendar, None, None, None,
            SimpleNamespace(), Path("/offline/bundles"), BUNDLE,
        )
    assert state.session.status == "FAILED"


def test_explicit_retry_requires_exact_staged_source_and_approval(tmp_path):
    failed = SimpleNamespace(status="FAILED")
    with pytest.raises(runner.ProductionRunError, match="exact staged source"):
        runner._validate_retry_authorization(failed, True, None, None)

    source_file = tmp_path / "approved-source.txt"
    source_manifest = tmp_path / "approved-source.json"
    source_file.write_text("fixture", encoding="utf-8")
    source_manifest.write_text("{}", encoding="utf-8")
    runner._validate_retry_authorization(failed, True, source_file, source_manifest)

    with pytest.raises(runner.ProductionRunError, match="only for an existing FAILED"):
        runner._validate_retry_authorization(None, True, source_file, source_manifest)


@pytest.mark.parametrize(
    "defect",
    [
        "missing_import_link",
        "wrong_import_hash",
        "wrong_source_manifest_pin",
        "wrong_origin",
        "wrong_target",
        "failed_pipeline_run",
        "incomplete_coverage",
        "synthetic_forecast",
        "wrong_artifact_lineage",
        "competing_run_duplicate",
    ],
)
def test_completed_session_recheck_rejects_broken_lineage(completed_session_fixture, defect):
    state = completed_session_fixture
    if defect == "missing_import_link":
        state.session.market_data_import_id = 999
    elif defect == "wrong_import_hash":
        state.imported.sha256 = "9" * 64
    elif defect == "wrong_source_manifest_pin":
        state.session.source_manifest_sha256 = "8" * 64
    elif defect == "wrong_origin":
        state.forecasts[0].origin_date = date(2026, 10, 7)
    elif defect == "wrong_target":
        state.forecasts[0].target_date = date(2026, 10, 13)
    elif defect == "failed_pipeline_run":
        state.run.status = "FAILED"
    elif defect == "incomplete_coverage":
        state.db.delete(state.forecasts[-1])
    elif defect == "synthetic_forecast":
        state.forecasts[0].is_demo = True
    elif defect == "wrong_artifact_lineage":
        state.artifacts[0].artifact_sha256 = "0" * 64
    elif defect == "competing_run_duplicate":
        state.db.add(PipelineRun(
            id=2, run_id="offline-other-run", status="COMPLETED", is_demo_run=False,
            started_at=datetime(2026, 10, 8, 12, tzinfo=timezone.utc),
            completed_at=datetime(2026, 10, 8, 13, tzinfo=timezone.utc),
            records_ingested=10, forecasts_generated=1,
        ))
        state.db.add(Forecast(
            company_id=state.company.id, model_id=state.forecasts[0].model_id,
            model_artifact_id=state.forecasts[0].model_artifact_id, pipeline_run_id=2,
            origin_date=TRADE_DATE, target_date=TARGET_DATE, predicted_price=101.25,
            predicted_delta=0.25, confidence_level=0.95, is_demo=False,
        ))
    state.db.flush()
    with pytest.raises((ProductionInputError, runner.ProductionRunError)):
        runner._verify_completed_session(
            state.db, state.session, TRADE_DATE, state.calendar,
            state.source_manifest, state.source_manifest_sha, Path("/offline/bundles"),
        )


def test_post_inference_validation_failure_rolls_back_unverified_forecasts(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    company = Company(id=1, symbol="ALI", name="Offline Fixture", sector_id=1, is_active=True)
    db.add(Sector(id=1, name="Technology", code="TECH"))
    db.add(company)
    metadata = [
        ModelMetadata(id=index, name=code, code=code, version="fixture", is_active=True)
        for index, code in enumerate(MODEL_CODES, 1)
    ]
    artifacts = [
        ModelArtifact(
            id=f"artifact-{code}", company_id=company.id, model_metadata_id=index,
            bundle_version=BUNDLE, artifact_format="joblib", artifact_path=f"ALI/{code}.artifact",
            artifact_sha256=str(index) * 64, trained_through=date(2025, 9, 30), data_row_count=100,
            hyperparameters_json="{}", source_repository="https://github.com/official/source.git",
            source_commit="d" * 40, historical_data_source_repository="https://github.com/official/source.git",
            historical_data_source_commit="e" * 40, is_active=True,
        )
        for index, code in enumerate(MODEL_CODES, 1)
    ]
    db.add_all(metadata + artifacts)
    db.commit()

    source_file = tmp_path / "fixture.txt"
    source_file.write_text("offline source fixture", encoding="utf-8")
    source_manifest = tmp_path / "fixture.json"
    source_manifest.write_text("{}", encoding="utf-8")
    approved_calendar = ApprovedCalendar(
        "f" * 64, TRADE_DATE, TARGET_DATE, frozenset({TRADE_DATE, TARGET_DATE})
    )
    quotes = [SimpleNamespace(
        symbol="ALI", trade_date=TRADE_DATE, open_price=100, high_price=101,
        low_price=99, close_price=100, volume=1000, value=None, source_filename="fixture.txt",
    )]
    monkeypatch.setattr(runner, "verify_source_manifest", lambda *a, **k: (
        {"source_url": "https://www.pse.com.ph/fixture", "reviewed_by": "offline"},
        SOURCE_SHA, SOURCE_MANIFEST_SHA,
    ))
    monkeypatch.setattr(runner, "validate_approved_models", lambda *a, **k: ([company], MODEL_MANIFEST_SHA, {
        ("ALI", code): artifact for code, artifact in zip(MODEL_CODES, artifacts, strict=True)
    }))
    monkeypatch.setattr(runner, "EODIngestionService", lambda: SimpleNamespace(
        ingest_from_file=lambda *a, **k: (quotes, SOURCE_SHA)
    ))
    monkeypatch.setattr(runner, "DataValidator", lambda: SimpleNamespace(
        validate_dataset=lambda rows, **kwargs: (rows, [])
    ))
    monkeypatch.setattr(runner, "_verify_idempotent_import", lambda *a, **k: None)

    def incomplete_inference(*, db, **kwargs):
        assert kwargs["expected_origin_date"] == TRADE_DATE
        assert kwargs["as_of_date"] == TRADE_DATE
        run = kwargs["pipeline_run"]
        db.add(Forecast(
            company_id=company.id, model_id=metadata[0].id,
            model_artifact_id=artifacts[0].id, pipeline_run_id=run.id,
            origin_date=TRADE_DATE, target_date=TARGET_DATE,
            predicted_price=101.25, predicted_delta=0.25, is_demo=False,
        ))
        return SimpleNamespace(
            status="PENDING_COMMIT", items=[SimpleNamespace(
                symbol="ALI", model_code=MODEL_CODES[0], origin_date=TRADE_DATE,
                target_date=TARGET_DATE, status="PERSISTED", predicted_close=101.25,
                predicted_delta=0.25, lower_bound=None, upper_bound=None,
            )], total_forecasts_persisted=1, total_forecasts_unchanged=0,
        )

    monkeypatch.setattr(runner, "RealForecastService", lambda **kwargs: SimpleNamespace(
        generate_and_persist_forecasts=incomplete_inference
    ))
    settings = SimpleNamespace(
        ENVIRONMENT="production", DEBUG=False, DEMO_MODE=False, AUTO_CREATE_SCHEMA=False,
        MODEL_ARTIFACT_ACTIVATION_ENABLED=False, REAL_MODELS_ENABLED=True,
        PROCESS_ROLE="production-eod",
    )
    commit_states = []
    original_commit = db.commit

    def capture_audit_state_before_commit():
        session_row = db.query(ProductionSession).filter_by(trade_date=TRADE_DATE).one_or_none()
        run_rows = db.query(PipelineRun).all()
        if session_row is not None and run_rows:
            commit_states.append((session_row.status, run_rows[-1].status))
        original_commit()

    monkeypatch.setattr(db, "commit", capture_audit_state_before_commit)
    result = runner.run_session(
        db, TRADE_DATE, approved_calendar, source_file, source_manifest,
        SOURCE_MANIFEST_SHA, settings, Path("/offline/bundles"), BUNDLE,
    )
    assert result == 1
    assert db.query(Forecast).filter(Forecast.pipeline_run_id.is_not(None)).count() == 0
    assert db.query(DailyPrice).count() == 0
    assert db.query(MarketDataImport).count() == 0
    session = db.query(ProductionSession).filter_by(trade_date=TRADE_DATE).one()
    assert session.status == "FAILED"
    run = db.query(PipelineRun).filter_by(id=session.pipeline_run_id).one()
    assert run.status == "FAILED"
    assert ("FAILED", "FAILED") in commit_states
    assert ("RUNNING", "FAILED") not in commit_states
    db.close()
    engine.dispose()
