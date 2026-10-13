"""PostgreSQL 16 checks for the production-session claim boundary.

This module requires an explicitly named disposable local/CI database. It
refuses non-local hosts and databases not named for this test job.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.models.company import Company
from backend.app.models.forecast import Forecast
from backend.app.models.market_data_import import MarketDataImport
from backend.app.models.model_metadata import ModelMetadata
from backend.app.models.pipeline_run import PipelineRun
from backend.app.models.price import DailyPrice
from backend.app.models.production_session import ProductionSession
from backend.app.models.sector import Sector
from backend.app.production_inputs import ApprovedCalendar
from backend.pipeline import production_runner as runner


@pytest.fixture(scope="module")
def postgres_session_factory():
    import os

    database_url = os.environ.get("PSE_TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("PSE_TEST_DATABASE_URL is required for PostgreSQL integration tests.")
    parsed = make_url(database_url)
    if (parsed.drivername != "postgresql+psycopg"
            or parsed.host not in {"postgres", "localhost", "127.0.0.1"}
            or parsed.database != "pse_phase4d1_test"):
        pytest.fail("PostgreSQL tests only permit the disposable local pse_phase4d1_test database.")
    engine = create_engine(database_url, pool_size=4, max_overflow=0, pool_pre_ping=True)
    with engine.connect() as connection:
        version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
        assert 160000 <= version < 170000, "PostgreSQL integration service must be version 16."
        assert connection.execute(text("SELECT to_regclass('public.production_sessions')")).scalar_one()
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _unused_trade_date() -> date:
    return date(2100, 1, 1) + timedelta(days=uuid4().int % 1_000_000)


def _cleanup_claims(session_factory, trade_date: date) -> None:
    with session_factory() as db:
        row = db.query(ProductionSession).filter_by(trade_date=trade_date).one_or_none()
        run_id = row.pipeline_run_id if row is not None else None
        if row is not None:
            db.delete(row)
            db.commit()
        if run_id is not None:
            db.query(PipelineRun).filter_by(id=run_id).delete(synchronize_session=False)
            db.commit()


def test_competing_claims_serialize_and_second_sees_durable_running_row(postgres_session_factory):
    trade_date = _unused_trade_date()
    barrier = Barrier(2)

    def attempt_claim() -> str:
        with postgres_session_factory() as db:
            barrier.wait(timeout=10)
            runner._lock_production_session_date(db, trade_date)
            existing = (db.query(ProductionSession)
                        .filter_by(trade_date=trade_date)
                        .with_for_update()
                        .one_or_none())
            if existing is not None:
                status = existing.status
                db.rollback()
                return f"rejected:{status}"
            run = PipelineRun(status="RUNNING", is_demo_run=False)
            db.add(run)
            db.flush()
            runner._set_session(
                db, trade_date, "RUNNING", "f" * 64,
                pipeline_run_id=run.id,
                message="Disposable PostgreSQL concurrency fixture.",
                commit=False,
            )
            db.commit()  # The transaction advisory lock ends here; the row remains durable.
            return "claimed"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt_claim), pool.submit(attempt_claim)]
            results = sorted(future.result(timeout=20) for future in futures)
        assert results == ["claimed", "rejected:RUNNING"]
        with postgres_session_factory() as db:
            assert db.query(ProductionSession).filter_by(trade_date=trade_date).count() == 1
            row = db.query(ProductionSession).filter_by(trade_date=trade_date).one()
            assert row.status == "RUNNING"
            assert db.query(PipelineRun).filter_by(id=row.pipeline_run_id).one().status == "RUNNING"
    finally:
        _cleanup_claims(postgres_session_factory, trade_date)


def test_concurrent_finalization_has_one_winner_on_the_durable_claim(postgres_session_factory):
    trade_date = _unused_trade_date()
    with postgres_session_factory() as db:
        run = PipelineRun(status="RUNNING", is_demo_run=False)
        db.add(run)
        db.flush()
        runner._set_session(
            db, trade_date, "RUNNING", "f" * 64,
            pipeline_run_id=run.id, message="Concurrent finalization fixture.", commit=False,
        )
        db.commit()
        run_id = run.id
    barrier = Barrier(2)

    def finalize() -> str:
        with postgres_session_factory() as db:
            barrier.wait(timeout=10)
            row = runner._lock_finalization_claim(db, trade_date, run_id)
            if row.status == "COMPLETED":
                db.rollback()
                return "already-completed"
            row.status = "COMPLETED"
            db.query(PipelineRun).filter_by(id=run_id).one().status = "COMPLETED"
            db.commit()
            return "finalized"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(future.result(timeout=20) for future in (pool.submit(finalize), pool.submit(finalize)))
        assert results == ["already-completed", "finalized"]
        with postgres_session_factory() as db:
            row = db.query(ProductionSession).filter_by(trade_date=trade_date).one()
            assert row.status == "COMPLETED"
            assert row.pipeline_run_id == run_id
            assert db.query(PipelineRun).filter_by(id=run_id).one().status == "COMPLETED"
    finally:
        _cleanup_claims(postgres_session_factory, trade_date)


@pytest.mark.parametrize("status", ["RUNNING", "COMPLETED", "FAILED"])
def test_database_rejects_duplicate_session_date(postgres_session_factory, status):
    trade_date = _unused_trade_date()
    try:
        with postgres_session_factory() as db:
            db.add(ProductionSession(trade_date=trade_date, status=status, calendar_sha256="a" * 64))
            db.commit()
        with postgres_session_factory() as db:
            db.add(ProductionSession(trade_date=trade_date, status=status, calendar_sha256="b" * 64))
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()
    finally:
        _cleanup_claims(postgres_session_factory, trade_date)


def test_actual_runner_rejects_existing_running_and_failed_sessions(postgres_session_factory):
    for status, expected, retry_failed in (
        ("RUNNING", "already running", False),
        ("FAILED", "explicit owner-authorized retry", False),
        ("COMPLETED", "valid only for an existing FAILED", True),
    ):
        trade_date = _unused_trade_date()
        calendar = ApprovedCalendar("c" * 64, trade_date, trade_date, frozenset({trade_date}))
        try:
            with postgres_session_factory() as db:
                run = None
                if status == "RUNNING":
                    run = PipelineRun(status="RUNNING", is_demo_run=False)
                    db.add(run)
                    db.flush()
                db.add(ProductionSession(
                    trade_date=trade_date, status=status, calendar_sha256="c" * 64,
                    pipeline_run_id=run.id if run is not None else None,
                ))
                db.commit()
                with pytest.raises(runner.ProductionRunError, match=expected):
                    runner.run_session(
                        db, trade_date, calendar, None, None, None,
                        SimpleNamespace(), Path("/unused"), "unused",
                        retry_failed=retry_failed,
                    )
                assert db.query(ProductionSession).filter_by(trade_date=trade_date).one().status == status
        finally:
            _cleanup_claims(postgres_session_factory, trade_date)


def test_competing_explicit_retries_rollback_provisional_data_and_fail_atomically(
    postgres_session_factory, monkeypatch, tmp_path,
):
    trade_date = _unused_trade_date()
    prior_date = trade_date - timedelta(days=1)
    calendar = ApprovedCalendar("d" * 64, trade_date, trade_date, frozenset({trade_date}))
    source = tmp_path / "approved-source.txt"
    manifest = tmp_path / "approved-source.json"
    source.write_text("disposable source fixture", encoding="utf-8")
    manifest.write_text("{}", encoding="utf-8")
    inference_started = Barrier(2)
    release_inference = Barrier(2)
    failed_state_written = Barrier(2)
    release_failure_commit = Barrier(2)

    with postgres_session_factory() as db:
        sector = Sector(name=f"PG test {uuid4()}", code=f"T{uuid4().hex[:8]}")
        db.add(sector)
        db.flush()
        company = Company(symbol=f"T{uuid4().hex[:5]}", name="Disposable PostgreSQL fixture", sector_id=sector.id, is_active=True)
        metadata = ModelMetadata(name="Disposable", code="ARIMA", version="pg-test", is_active=True)
        db.add_all([company, metadata])
        db.flush()
        approved_import = MarketDataImport(
            source_filename="approved-history.txt", trade_date=prior_date,
            sha256="e" * 64, status="COMPLETED", records_seen=1, records_valid=1,
        )
        prior_price = DailyPrice(
            company_id=company.id, trade_date=prior_date,
            open_price=10, high_price=11, low_price=9, close_price=10, volume=1,
        )
        existing_failed = ProductionSession(
            trade_date=trade_date, status="FAILED", calendar_sha256=calendar.sha256,
        )
        db.add_all([approved_import, prior_price, existing_failed])
        db.commit()
        company_id, company_symbol, metadata_id = company.id, company.symbol, metadata.id
        approved_import_id = approved_import.id
        sector_id = sector.id

    source_sha = "a" * 64
    source_manifest_sha = "b" * 64
    model_manifest_sha = "c" * 64
    monkeypatch.setattr(runner, "verify_source_manifest", lambda *a, **k: (
        {"source_url": "https://example.invalid/disposable", "reviewed_by": "CI fixture"},
        source_sha, source_manifest_sha,
    ))
    monkeypatch.setattr(runner, "validate_production_settings", lambda settings: None)

    def validate_models(db, artifacts_root, bundle_version):
        company = db.query(Company).filter_by(id=company_id).one()
        return [company], model_manifest_sha, {}

    monkeypatch.setattr(runner, "validate_approved_models", validate_models)
    parsed_row = SimpleNamespace(symbol=company_symbol, trade_date=trade_date)
    monkeypatch.setattr(runner, "EODIngestionService", lambda: SimpleNamespace(
        ingest_from_file=lambda *a, **k: ([parsed_row], source_sha),
    ))
    monkeypatch.setattr(runner, "DataValidator", lambda: SimpleNamespace(
        validate_dataset=lambda rows, **kwargs: (rows, []),
    ))
    monkeypatch.setattr(runner, "_verify_idempotent_import", lambda *a, **k: None)

    def stage_import(db, source_file, session_date, symbols, ingestion):
        imported = MarketDataImport(
            source_filename=source_file.name, trade_date=session_date,
            sha256=source_sha, status="COMPLETED", records_seen=1, records_valid=1,
            records_inserted=1,
        )
        db.add(imported)
        db.flush()
        db.add(DailyPrice(
            company_id=company_id, trade_date=session_date,
            open_price=12, high_price=13, low_price=11, close_price=12, volume=1,
        ))
        db.flush()
        return 1, source_sha, imported.id

    monkeypatch.setattr(runner, "_ingest_verified_source", stage_import)

    class FailingForecastService:
        def __init__(self, db, **kwargs):
            self.db = db

        def generate_and_persist_forecasts(self, **kwargs):
            self.db.add(Forecast(
                company_id=company_id, model_id=metadata_id,
                pipeline_run_id=kwargs["pipeline_run"].id,
                origin_date=trade_date, target_date=trade_date + timedelta(days=1),
                predicted_price=12, predicted_delta=0.1, confidence_level=0.95,
                is_demo=False,
            ))
            inference_started.wait(timeout=15)
            release_inference.wait(timeout=15)
            raise RuntimeError("injected final validation failure")

    monkeypatch.setattr(runner, "RealForecastService", FailingForecastService)
    first_result = []

    def first_retry():
        with postgres_session_factory() as db:
            original_commit = db.commit
            commits = 0

            def hold_failure_commit():
                nonlocal commits
                commits += 1
                if commits == 2:
                    failed_state_written.wait(timeout=15)
                    release_failure_commit.wait(timeout=15)
                original_commit()

            db.commit = hold_failure_commit
            first_result.append(runner.run_session(
                db, trade_date, calendar, source, manifest, source_manifest_sha,
                SimpleNamespace(), Path("/unused"), "disposable-bundle", retry_failed=True,
            ))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first_retry)
        inference_started.wait(timeout=15)
        with postgres_session_factory() as db:
            with pytest.raises(runner.ProductionRunError, match="valid only for an existing FAILED"):
                runner.run_session(
                    db, trade_date, calendar, source, manifest, source_manifest_sha,
                    SimpleNamespace(), Path("/unused"), "disposable-bundle", retry_failed=True,
                )
        # The winning retry remains RUNNING/RUNNING while provisional rows are staged.
        with postgres_session_factory() as db:
            session_row = db.query(ProductionSession).filter_by(trade_date=trade_date).one()
            run_row = db.query(PipelineRun).filter_by(id=session_row.pipeline_run_id).one()
            assert (session_row.status, run_row.status) == ("RUNNING", "RUNNING")
            assert db.query(MarketDataImport).filter_by(trade_date=trade_date).count() == 0
            assert db.query(DailyPrice).filter_by(company_id=company_id, trade_date=trade_date).count() == 0
            assert db.query(Forecast).filter_by(pipeline_run_id=run_row.id).count() == 0
            assert db.query(MarketDataImport).filter_by(id=approved_import_id).count() == 1
            assert db.query(DailyPrice).filter_by(company_id=company_id, trade_date=prior_date).count() == 1

        release_inference.wait(timeout=15)
        failed_state_written.wait(timeout=15)
        # Failure records are not visible until their shared transaction commits.
        with postgres_session_factory() as db:
            session_row = db.query(ProductionSession).filter_by(trade_date=trade_date).one()
            run_row = db.query(PipelineRun).filter_by(id=session_row.pipeline_run_id).one()
            assert (session_row.status, run_row.status) == ("RUNNING", "RUNNING")
        release_failure_commit.wait(timeout=15)
        assert future.result(timeout=20) is None

    assert first_result == [1]
    try:
        with postgres_session_factory() as db:
            session_row = db.query(ProductionSession).filter_by(trade_date=trade_date).one()
            run_row = db.query(PipelineRun).filter_by(id=session_row.pipeline_run_id).one()
            assert (session_row.status, run_row.status) == ("FAILED", "FAILED")
            assert db.query(MarketDataImport).filter_by(trade_date=trade_date).count() == 0
            assert db.query(DailyPrice).filter_by(company_id=company_id, trade_date=trade_date).count() == 0
            assert db.query(Forecast).filter_by(pipeline_run_id=run_row.id).count() == 0
            assert db.query(MarketDataImport).filter_by(id=approved_import_id).count() == 1
            assert db.query(DailyPrice).filter_by(company_id=company_id, trade_date=prior_date).count() == 1
    finally:
        with postgres_session_factory() as db:
            session_row = db.query(ProductionSession).filter_by(trade_date=trade_date).one_or_none()
            run_id = session_row.pipeline_run_id if session_row else None
            if session_row:
                db.delete(session_row)
                db.commit()
            if run_id:
                db.query(PipelineRun).filter_by(id=run_id).delete(synchronize_session=False)
            db.query(DailyPrice).filter_by(company_id=company_id).delete(synchronize_session=False)
            db.query(MarketDataImport).filter_by(id=approved_import_id).delete(synchronize_session=False)
            db.query(Company).filter_by(id=company_id).delete(synchronize_session=False)
            db.query(ModelMetadata).filter_by(id=metadata_id).delete(synchronize_session=False)
            db.query(Sector).filter_by(id=sector_id).delete(synchronize_session=False)
            db.commit()
