"""Comprehensive tests for PSE Daily Quotation Report (DQR) ingestion foundation.

Covers:
- PSEDQRFileProvider text and PDF parsing
- Trade date extraction and mismatch guards
- Zero-price prohibition and non-traded row handling
- DataValidator financial sanity and NaN/Inf rejection
- Intra-batch duplicate detection
- Idempotent database persistence and dry-run guarantees
- SHA-256 duplicate detection and --force bypass
- Production DEMO_MODE forecast safety guard
- API /pipeline/status provenance reporting
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from backend.pipeline.ingest.models import EODQuote
from backend.pipeline.ingest.providers.pse_dqr_file import PSEDQRFileProvider
from backend.pipeline.ingest.eod_ingest import EODIngestionService
from backend.pipeline.validation.data_validator import DataValidator
from backend.pipeline.persistence.db_saver import DatabaseSaver
from backend.pipeline.runner import run_pipeline
from backend.app.models.company import Company
from backend.app.models.price import DailyPrice
from backend.app.models.market_data_import import MarketDataImport
from backend.app.models.forecast import Forecast
from backend.app.models.pipeline_run import PipelineRun
from backend.app.config import get_settings

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "pse_dqr"
TXT_FIXTURE = FIXTURES_DIR / "sample_dqr.txt"
PDF_FIXTURE = FIXTURES_DIR / "sample_dqr.pdf"
CORRECTED_FIXTURE = FIXTURES_DIR / "sample_dqr_corrected.txt"


@pytest.fixture(autouse=True)
def clean_dqr_state(db_session: Session):
    """Ensure clean state for test trade date and imports before and after each test."""
    def cleanup():
        db_session.query(DailyPrice).filter(DailyPrice.trade_date == date(2026, 10, 1)).delete()
        db_session.query(MarketDataImport).delete()
        # Clean test pipeline runs to prevent side-effects on subsequent tests
        runs = db_session.query(PipelineRun).filter(PipelineRun.run_id != "demo-init-run-0001").all()
        for r in runs:
            db_session.query(Forecast).filter(Forecast.pipeline_run_id == r.id).delete()
            db_session.delete(r)
        db_session.commit()

    cleanup()
    yield
    cleanup()


# ==============================================================================
# 1. PARSER TESTS
# ==============================================================================

def test_parser_loads_text_fixture():
    """Verify parser extracts quotes from official DQR text layout."""
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(TXT_FIXTURE)

    assert len(quotes) >= 4
    symbols = {q.symbol for q in quotes}
    assert "SMPH" in symbols
    assert "ALI" in symbols
    assert "BDO" in symbols
    assert "BPI" in symbols
    assert "MONDE" in symbols

    # Non-traded DMC with dashes must NOT be parsed into a quote with 0 prices
    assert "DMC" not in symbols

    smph = next(q for q in quotes if q.symbol == "SMPH")
    assert smph.trade_date == date(2026, 10, 1)
    assert smph.open_price == Decimal("28.20")
    assert smph.high_price == Decimal("28.80")
    assert smph.low_price == Decimal("28.00")
    assert smph.close_price == Decimal("28.60")
    assert smph.volume == 1250000
    assert smph.value == Decimal("35625000")


def test_parser_loads_pdf_fixture():
    """Verify parser extracts quotes from official DQR PDF using pypdf."""
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(PDF_FIXTURE)

    assert len(quotes) >= 3
    symbols = {q.symbol for q in quotes}
    assert "SMPH" in symbols
    assert "BDO" in symbols
    assert "ALI" in symbols
    assert "DMC" not in symbols  # Non-traded equity skipped

    bdo = next(q for q in quotes if q.symbol == "BDO")
    assert bdo.trade_date == date(2026, 10, 1)
    assert bdo.close_price == Decimal("142.00")
    assert bdo.volume == 650000


def test_parser_target_date_validation_success():
    """Verify passing matching target_date succeeds."""
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(TXT_FIXTURE, target_date=date(2026, 10, 1))
    assert len(quotes) > 0


def test_parser_target_date_mismatch_raises():
    """Verify passing mismatched target_date raises ValueError."""
    provider = PSEDQRFileProvider()
    with pytest.raises(ValueError, match="does not match requested target date"):
        provider.load_quotes(TXT_FIXTURE, target_date=date(2026, 10, 2))


def test_parser_file_not_found():
    """Verify non-existent file raises FileNotFoundError."""
    provider = PSEDQRFileProvider()
    with pytest.raises(FileNotFoundError):
        provider.load_quotes(Path("non_existent_dqr.txt"))


def test_parser_date_formats():
    """Verify regex date extraction across various header date formats."""
    provider = PSEDQRFileProvider()

    # Month DD, YYYY
    d1 = provider._find_date_in_text("REPORT FOR October 01, 2026\n...")
    assert d1 == date(2026, 10, 1)

    # ISO YYYY-MM-DD
    d2 = provider._find_date_in_text("DATE: 2026-10-01\n...")
    assert d2 == date(2026, 10, 1)

    # Slash MM/DD/YYYY
    d3 = provider._find_date_in_text("DATE: 10/01/2026\n...")
    assert d3 == date(2026, 10, 1)


# ==============================================================================
# 2. VALIDATOR TESTS
# ==============================================================================

def test_validator_valid_eod_quote():
    """Verify valid EODQuote passes validation."""
    quote = EODQuote(
        trade_date=date(2026, 10, 1),
        symbol="SMPH",
        open_price=Decimal("28.20"),
        high_price=Decimal("28.80"),
        low_price=Decimal("28.00"),
        close_price=Decimal("28.60"),
        volume=1250000,
        value=Decimal("35625000"),
    )
    ok, errors = DataValidator.validate_ohlc_record(quote)
    assert ok is True
    assert len(errors) == 0


def test_validator_rejects_zero_or_negative_price():
    """Verify zero price is strictly prohibited."""
    quote = EODQuote(
        trade_date=date(2026, 10, 1),
        symbol="SMPH",
        open_price=Decimal("0.00"),
        high_price=Decimal("28.80"),
        low_price=Decimal("0.00"),
        close_price=Decimal("28.60"),
        volume=1250000,
    )
    ok, errors = DataValidator.validate_ohlc_record(quote)
    assert ok is False
    assert any("strictly positive" in e for e in errors)


def test_validator_rejects_nan_and_inf():
    """Verify NaN and Inf are rejected."""
    dict_record = {
        "symbol": "SMPH",
        "trade_date": "2026-10-01",
        "open_price": float("nan"),
        "high_price": 30.0,
        "low_price": 28.0,
        "close_price": 29.0,
        "volume": 1000,
    }
    ok, errors = DataValidator.validate_ohlc_record(dict_record)
    assert ok is False
    assert any("NaN" in e or "finite" in e for e in errors)

    dict_inf = {
        "symbol": "SMPH",
        "trade_date": "2026-10-01",
        "open_price": 29.0,
        "high_price": float("inf"),
        "low_price": 28.0,
        "close_price": 29.0,
        "volume": 1000,
    }
    ok2, errors2 = DataValidator.validate_ohlc_record(dict_inf)
    assert ok2 is False
    assert any("NaN" in e or "finite" in e for e in errors2)


def test_validator_intra_batch_deduplication():
    """Verify duplicate (symbol, trade_date) within a single batch is rejected."""
    q1 = EODQuote(
        trade_date=date(2026, 10, 1),
        symbol="SMPH",
        open_price=Decimal("28.20"),
        high_price=Decimal("28.80"),
        low_price=Decimal("28.00"),
        close_price=Decimal("28.60"),
        volume=1250000,
    )
    q2 = EODQuote(
        trade_date=date(2026, 10, 1),
        symbol="SMPH",
        open_price=Decimal("28.20"),
        high_price=Decimal("28.80"),
        low_price=Decimal("28.00"),
        close_price=Decimal("28.60"),
        volume=1250000,
    )
    validator = DataValidator()
    valid, invalid = validator.validate_dataset([q1, q2])

    assert len(valid) == 1
    assert len(invalid) == 1
    assert any("Duplicate" in err for err in invalid[0]["validation_errors"])


# ==============================================================================
# 3. DATABASE PERSISTENCE & IDEMPOTENCY TESTS
# ==============================================================================

def test_saver_persists_daily_prices(db_session: Session):
    """Verify inserting quotes into daily_prices with untracked filtering."""
    saver = DatabaseSaver(db_session)
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(TXT_FIXTURE)

    summary = saver.persist_daily_prices(
        quotes=quotes,
        sha256_hash="dummy_hash_1",
        source_filename="sample_dqr.txt",
        dry_run=False,
    )

    assert summary.status == "COMPLETED"
    assert summary.records_seen == len(quotes)
    # Tracked companies: SMPH, ALI, BDO, BPI (4)
    # Untracked: MONDE (1)
    assert summary.records_tracked == 4
    assert summary.records_untracked == 1
    assert summary.records_inserted == 4
    assert summary.records_updated == 0
    assert summary.records_unchanged == 0

    # Verify rows in DB
    smph_comp = db_session.query(Company).filter(Company.symbol == "SMPH").first()
    assert smph_comp is not None
    p_record = (
        db_session.query(DailyPrice)
        .filter(DailyPrice.company_id == smph_comp.id, DailyPrice.trade_date == date(2026, 10, 1))
        .first()
    )
    assert p_record is not None
    assert Decimal(str(p_record.close_price)).quantize(Decimal("0.01")) == Decimal("28.60")


def test_saver_idempotent_reimport(db_session: Session):
    """Verify running import a second time on identical data results in 0 inserts/updates and 4 unchanged."""
    saver = DatabaseSaver(db_session)
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(TXT_FIXTURE)

    # First run
    s1 = saver.persist_daily_prices(quotes, sha256_hash="hash_a", source_filename="sample.txt")
    assert s1.records_inserted == 4

    # Second run (exact same quotes)
    s2 = saver.persist_daily_prices(quotes, sha256_hash="hash_a", source_filename="sample.txt")
    assert s2.records_inserted == 0
    assert s2.records_updated == 0
    assert s2.records_unchanged == 4


def test_saver_updates_changed_price(db_session: Session):
    """Verify reimporting with an amended price updates the existing record."""
    saver = DatabaseSaver(db_session)
    q1 = [
        EODQuote(
            trade_date=date(2026, 10, 1),
            symbol="SMPH",
            open_price=Decimal("28.20"),
            high_price=Decimal("28.80"),
            low_price=Decimal("28.00"),
            close_price=Decimal("28.60"),
            volume=1000,
        )
    ]
    saver.persist_daily_prices(q1, source_filename="test.txt")

    # Modified close price and volume
    q2 = [
        EODQuote(
            trade_date=date(2026, 10, 1),
            symbol="SMPH",
            open_price=Decimal("28.20"),
            high_price=Decimal("29.00"),
            low_price=Decimal("28.00"),
            close_price=Decimal("28.95"),
            volume=2000,
        )
    ]
    s2 = saver.persist_daily_prices(q2, source_filename="test.txt")
    assert s2.records_updated == 1
    assert s2.records_inserted == 0
    assert s2.records_unchanged == 0

    smph = db_session.query(Company).filter(Company.symbol == "SMPH").first()
    p = db_session.query(DailyPrice).filter(DailyPrice.company_id == smph.id, DailyPrice.trade_date == date(2026, 10, 1)).first()
    assert Decimal(str(p.close_price)).quantize(Decimal("0.01")) == Decimal("28.95")
    assert p.volume == 2000


def test_saver_dry_run_zero_db_mutations(db_session: Session):
    """Verify dry_run=True leaves the database completely untouched."""
    saver = DatabaseSaver(db_session)
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(TXT_FIXTURE)

    summary = saver.persist_daily_prices(quotes, source_filename="sample.txt", dry_run=True)
    assert summary.status == "DRY_RUN"
    assert summary.records_inserted == 4

    # Assert no daily_prices were committed
    count = db_session.query(DailyPrice).filter(DailyPrice.trade_date == date(2026, 10, 1)).count()
    assert count == 0


def test_saver_records_market_data_import(db_session: Session):
    """Verify provenance audit entry is recorded in market_data_imports."""
    saver = DatabaseSaver(db_session)
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(TXT_FIXTURE)

    summary = saver.persist_daily_prices(quotes, sha256_hash="test_sha256_abc", source_filename="sample_dqr.txt")
    audit = saver.record_market_data_import(summary)

    assert audit.id is not None
    assert audit.sha256 == "test_sha256_abc"
    assert audit.source_filename == "sample_dqr.txt"
    assert audit.status == "COMPLETED"
    assert audit.trade_date == date(2026, 10, 1)

    # Check query helper
    found = saver.get_import_by_sha256("test_sha256_abc")
    assert found is not None
    assert found.id == audit.id


# ==============================================================================
# 4. SERVICE & SHA-256 DUPLICATE DETECTION TESTS
# ==============================================================================

def test_service_sha256_duplicate_guard(db_session: Session):
    """Verify importing same file twice raises ValueError without --force."""
    svc = EODIngestionService()
    saver = DatabaseSaver(db_session)

    quotes, sha256_hash = svc.ingest_from_file(TXT_FIXTURE, force=False, db=db_session)
    summary = saver.persist_daily_prices(quotes, sha256_hash=sha256_hash, source_filename=TXT_FIXTURE.name)
    saver.record_market_data_import(summary)

    # Second attempt without force must fail
    with pytest.raises(ValueError, match="already successfully imported"):
        svc.ingest_from_file(TXT_FIXTURE, force=False, db=db_session)

    # With force=True, must succeed
    q_forced, hash_forced = svc.ingest_from_file(TXT_FIXTURE, force=True, db=db_session)
    assert len(q_forced) == len(quotes)
    assert hash_forced == sha256_hash


# ==============================================================================
# 5. RUNNER CLI & SAFETY GUARD TESTS
# ==============================================================================

def test_runner_dry_run_executes_without_commit(db_session: Session):
    """Verify run_pipeline with dry_run=True does not persist records."""
    code = run_pipeline(
        source_file=TXT_FIXTURE,
        trade_date=date(2026, 10, 1),
        dry_run=True,
        db=db_session,
    )
    assert code == 0

    # Ensure no import audit record was created
    audit_count = db_session.query(MarketDataImport).count()
    assert audit_count == 0


def test_runner_ingest_only_flag(db_session: Session):
    """Verify --ingest-only runs ingestion but does not generate new forecasts."""
    initial_forecasts = db_session.query(Forecast).count()

    code = run_pipeline(
        source_file=TXT_FIXTURE,
        trade_date=date(2026, 10, 1),
        ingest_only=True,
        force=True,
        db=db_session,
    )
    assert code == 0

    final_forecasts = db_session.query(Forecast).count()
    assert final_forecasts == initial_forecasts  # No new forecasts created


def test_runner_production_demo_mode_safety(db_session: Session, monkeypatch):
    """Verify that in production (DEMO_MODE=False), stub forecasts are never generated."""
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()

    try:
        initial_forecasts = db_session.query(Forecast).count()

        code = run_pipeline(
            source_file=TXT_FIXTURE,
            trade_date=date(2026, 10, 1),
            ingest_only=False,  # Even when not ingest_only!
            force=True,
            db=db_session,
        )
        assert code == 0

        final_forecasts = db_session.query(Forecast).count()
        # Stub forecasts must be completely skipped in production
        assert final_forecasts == initial_forecasts
    finally:
        get_settings.cache_clear()


def test_runner_second_run_duplicate_file_skipped(db_session: Session):
    """Verify re-running exact same file without --force logs ALREADY_IMPORTED/SKIPPED and adds zero rows."""
    # First run
    code1 = run_pipeline(source_file=PDF_FIXTURE, trade_date=date(2026, 10, 1), ingest_only=True, db=db_session)
    assert code1 == 0
    count1 = db_session.query(DailyPrice).filter(DailyPrice.trade_date == date(2026, 10, 1)).count()
    assert count1 == 3  # SMPH, BDO, ALI

    # Second run without --force
    code2 = run_pipeline(source_file=PDF_FIXTURE, trade_date=date(2026, 10, 1), ingest_only=True, db=db_session)
    assert code2 == 0
    count2 = db_session.query(DailyPrice).filter(DailyPrice.trade_date == date(2026, 10, 1)).count()
    assert count2 == count1  # Exactly zero new or duplicate rows!


def test_runner_corrected_source_updates_existing_row(db_session: Session):
    """Verify corrected source file with different SHA updates existing row rather than duplicating."""
    # First run: initial report (SMPH close = 28.60)
    code1 = run_pipeline(source_file=TXT_FIXTURE, trade_date=date(2026, 10, 1), ingest_only=True, db=db_session)
    assert code1 == 0

    smph = db_session.query(Company).filter(Company.symbol == "SMPH").first()
    p1 = db_session.query(DailyPrice).filter(DailyPrice.company_id == smph.id, DailyPrice.trade_date == date(2026, 10, 1)).first()
    assert p1 is not None
    assert Decimal(str(p1.close_price)).quantize(Decimal("0.01")) == Decimal("28.60")

    # Second run: corrected report (different SHA-256, SMPH close = 28.65)
    code2 = run_pipeline(source_file=CORRECTED_FIXTURE, trade_date=date(2026, 10, 1), ingest_only=True, db=db_session)
    assert code2 == 0

    # Verify existing row was updated and NOT duplicated
    p_rows = db_session.query(DailyPrice).filter(DailyPrice.company_id == smph.id, DailyPrice.trade_date == date(2026, 10, 1)).all()
    assert len(p_rows) == 1
    assert Decimal(str(p_rows[0].close_price)).quantize(Decimal("0.01")) == Decimal("28.65")


# ==============================================================================
# 6. PIPELINE API STATUS ENDPOINT PROVENANCE
# ==============================================================================

def test_pipeline_status_endpoint_reports_import_provenance(client, db_session: Session):
    """Verify GET /api/v1/pipeline/status includes last_market_data_import."""
    saver = DatabaseSaver(db_session)
    provider = PSEDQRFileProvider()
    quotes = provider.load_quotes(TXT_FIXTURE)

    summary = saver.persist_daily_prices(
        quotes=quotes,
        sha256_hash="test_status_sha256",
        source_filename="sample_dqr.txt",
    )
    saver.record_market_data_import(summary)

    response = client.get("/api/v1/pipeline/status")
    assert response.status_code == 200
    data = response.json()

    assert data["last_market_data_import"] is not None
    imp = data["last_market_data_import"]
    assert imp["sha256"] == "test_status_sha256"
    assert imp["source_filename"] == "sample_dqr.txt"
    assert imp["records_inserted"] == 4
    assert imp["status"] == "COMPLETED"
