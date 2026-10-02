"""Comprehensive tests for official repository historical OHLCV bootstrap.

Covers:
- OfficialRepoHistoricalProvider parsing, schema validation, and OHLC/volume rules
- CompanySyncService idempotent synchronization
- HistoricalBootstrapService all-or-nothing atomicity, idempotency, and conflict detection
- Runner bootstrap CLI integration
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.domain.company_universe import OFFICIAL_15_COMPANIES
from backend.app.models.company import Company
from backend.app.models.sector import Sector
from backend.app.models.price import DailyPrice
from backend.app.models.market_data_import import MarketDataImport
from backend.app.models.pipeline_run import PipelineRun
from backend.app.services.company_sync import CompanySyncService
from backend.pipeline.bootstrap.models import HistoricalQuote
from backend.pipeline.bootstrap.official_repo_csv import (
    OfficialRepoHistoricalProvider,
    HistoricalCsvValidationError,
)
from backend.pipeline.bootstrap.service import (
    HistoricalBootstrapService,
    HistoricalPriceConflictError,
)
from backend.pipeline.runner import run_pipeline

BOOTSTRAP_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "bootstrap"


@pytest.fixture
def bootstrap_db():
    """Isolated clean in-memory database session for bootstrap tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


# ==============================================================================
# 1. PROVIDER & VALIDATOR TESTS
# ==============================================================================

def test_official_provider_parses_valid_csv():
    """Verify provider parses valid CSV fixture into typed HistoricalQuote objects."""
    provider = OfficialRepoHistoricalProvider()
    quotes, sha256_hash = provider.parse_file(
        BOOTSTRAP_FIXTURES_DIR / "SMPH.csv",
        expected_symbol="SMPH",
    )

    assert len(quotes) == 4
    assert len(sha256_hash) == 64
    first_q = quotes[0]
    assert first_q.symbol == "SMPH"
    assert first_q.trade_date == date(2026, 9, 28)
    assert first_q.open_price == Decimal("28.00")
    assert first_q.high_price == Decimal("30.00")
    assert first_q.low_price == Decimal("27.00")
    assert first_q.close_price == Decimal("28.50")
    assert first_q.volume == 1000000


def test_official_provider_missing_column_raises(tmp_path: Path):
    """Verify provider rejects CSV missing required columns."""
    bad_csv = tmp_path / "BAD.csv"
    bad_csv.write_text("Date,Open,High,Low,Close\n2026-09-28,10,12,9,11\n")

    provider = OfficialRepoHistoricalProvider()
    with pytest.raises(HistoricalCsvValidationError, match="missing required columns"):
        provider.parse_file(bad_csv, "BAD")


def test_official_provider_duplicate_date_raises(tmp_path: Path):
    """Verify provider rejects duplicate trading dates."""
    bad_csv = tmp_path / "DUP.csv"
    bad_csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-09-28,10,12,9,11,1000\n"
        "2026-09-28,11,13,10,12,2000\n"
    )

    provider = OfficialRepoHistoricalProvider()
    with pytest.raises(HistoricalCsvValidationError, match="Duplicate trade date"):
        provider.parse_file(bad_csv, "DUP")


def test_official_provider_invalid_ohlc_raises(tmp_path: Path):
    """Verify provider rejects invalid price boundaries (High < Low)."""
    bad_csv = tmp_path / "OHLC.csv"
    bad_csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-09-28,10,8,12,11,1000\n"
    )

    provider = OfficialRepoHistoricalProvider()
    with pytest.raises(HistoricalCsvValidationError, match="High .* cannot be below"):
        provider.parse_file(bad_csv, "OHLC")


def test_canonical_sectors_count_and_members():
    """Verify official universe defines exactly 5 canonical sectors."""
    sectors = set(c.sector for c in OFFICIAL_15_COMPANIES)
    assert len(sectors) == 5
    assert sectors == {
        "Financials",
        "Industrial",
        "Property",
        "Services",
        "Mining and Oil",
    }


def test_official_provider_preserves_exact_decimal_volume(tmp_path: Path):
    """Verify volume fractional values are preserved exactly without rounding."""
    frac_csv = tmp_path / "FRAC.csv"
    frac_csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-09-28,10,12,9,11,182688245.5\n"
        "2026-09-29,10,12,9,11,1250000.0\n"
        "2026-09-30,10,12,9,11,50000\n"
    )

    provider = OfficialRepoHistoricalProvider()
    quotes, _ = provider.parse_file(frac_csv, "FRAC")
    assert len(quotes) == 3
    assert quotes[0].volume == Decimal("182688245.5")
    assert quotes[1].volume == Decimal("1250000.0")
    assert quotes[2].volume == Decimal("50000")


# ==============================================================================
# 2. COMPANY SYNC TESTS
# ==============================================================================

def test_company_sync_service_idempotent(bootstrap_db: Session):
    """Verify CompanySyncService populates canonical 15 companies idempotently on clean DB."""
    syncer = CompanySyncService(bootstrap_db)

    # 1. Initial sync
    res1 = syncer.sync_companies(commit=True)
    assert res1.companies_inserted == 15
    assert res1.companies_updated == 0
    assert res1.total_active_companies == 15

    # 2. Verify all 15 symbols exist
    db_symbols = {c.symbol for c in bootstrap_db.query(Company).all()}
    expected = {c.symbol for c in OFFICIAL_15_COMPANIES}
    assert db_symbols == expected

    # 3. Second run must be no-op (0 inserted, 0 updated, 15 unchanged)
    res2 = syncer.sync_companies(commit=True)
    assert res2.companies_inserted == 0
    assert res2.companies_updated == 0
    assert res2.companies_unchanged == 15


def test_company_sync_deactivates_obsolete_companies(bootstrap_db: Session):
    """Verify CompanySyncService deactivates any existing non-canonical active companies."""
    syncer = CompanySyncService(bootstrap_db)
    sector_map = syncer.sync_sectors()
    sector = next(iter(sector_map.values()))

    # Insert a dummy demo company marked active
    dummy = Company(symbol="DUMMY", name="Dummy Demo Corp", sector_id=sector.id, is_active=True)
    bootstrap_db.add(dummy)
    bootstrap_db.commit()

    # Synchronize companies
    res = syncer.sync_companies(commit=True)
    assert res.total_active_companies == 15

    # Check dummy is deactivated
    dummy_db = bootstrap_db.query(Company).filter(Company.symbol == "DUMMY").first()
    assert dummy_db is not None
    assert dummy_db.is_active is False

    # Check all active companies are the 15 official companies
    active_symbols = {c.symbol for c in bootstrap_db.query(Company).filter(Company.is_active == True).all()}
    expected_symbols = {c.symbol for c in OFFICIAL_15_COMPANIES}
    assert active_symbols == expected_symbols


# ==============================================================================
# 3. BOOTSTRAP SERVICE TESTS
# ==============================================================================

def test_bootstrap_service_missing_file_fails_all_or_nothing(bootstrap_db: Session, tmp_path: Path):
    """Verify missing official CSV file aborts bootstrap with zero database changes."""
    incomplete_dir = tmp_path / "incomplete"
    incomplete_dir.mkdir()
    (incomplete_dir / "SMPH.csv").write_text(
        (BOOTSTRAP_FIXTURES_DIR / "SMPH.csv").read_text()
    )

    service = HistoricalBootstrapService(db=bootstrap_db)
    with pytest.raises(FileNotFoundError, match="missing"):
        service.bootstrap_official_repo(raw_data_dir=incomplete_dir)

    # Zero DailyPrice rows inserted
    assert bootstrap_db.query(DailyPrice).count() == 0


def test_bootstrap_service_successful_run(bootstrap_db: Session):
    """Verify successful 15-company bootstrap persists all quotes and audit provenance."""
    service = HistoricalBootstrapService(db=bootstrap_db)
    summary = service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)

    assert summary.status == "COMPLETED"
    assert summary.total_symbols == 15
    assert summary.total_rows_inserted == 60  # 15 * 4
    assert summary.total_rows_unchanged == 0

    # Verify DB rows
    total_db_prices = bootstrap_db.query(DailyPrice).count()
    assert total_db_prices == 60

    # Verify provenance rows
    imports = bootstrap_db.query(MarketDataImport).filter(
        MarketDataImport.source_type == "OFFICIAL_REPO_BOOTSTRAP"
    ).all()
    assert len(imports) == 15
    assert all(imp.status == "COMPLETED" for imp in imports)
    assert all(imp.records_inserted == 4 for imp in imports)


def test_bootstrap_service_second_run_idempotency(bootstrap_db: Session):
    """Verify re-running bootstrap is completely idempotent (0 inserted, all unchanged)."""
    service = HistoricalBootstrapService(db=bootstrap_db)

    # First run
    s1 = service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)
    assert s1.total_rows_inserted == 60

    # Second run
    s2 = service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)
    assert s2.total_rows_inserted == 0
    assert s2.total_rows_updated == 0
    assert s2.total_rows_unchanged == 60
    assert bootstrap_db.query(DailyPrice).count() == 60


def test_bootstrap_service_conflict_aborts_and_rolls_back(bootstrap_db: Session):
    """Verify conflict with existing database row aborts bootstrap and rolls back."""
    service = HistoricalBootstrapService(db=bootstrap_db)
    service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)

    # Modify one row in database
    smph = bootstrap_db.query(Company).filter(Company.symbol == "SMPH").first()
    p = bootstrap_db.query(DailyPrice).filter(
        DailyPrice.company_id == smph.id,
        DailyPrice.trade_date == date(2026, 10, 1),
    ).first()
    p.close_price = Decimal("999.99")
    bootstrap_db.commit()

    # Re-running without conflict updates must raise HistoricalPriceConflictError
    with pytest.raises(HistoricalPriceConflictError, match="Historical price conflict for SMPH"):
        service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)

    # Verify rollback: database row still has modified value, no partial updates
    bootstrap_db.rollback()
    p_check = bootstrap_db.query(DailyPrice).filter(
        DailyPrice.company_id == smph.id,
        DailyPrice.trade_date == date(2026, 10, 1),
    ).first()
    assert Decimal(str(p_check.close_price)) == Decimal("999.99")


def test_bootstrap_service_dry_run_zero_mutations(bootstrap_db: Session):
    """Verify dry_run executes validation but leaves zero database mutations."""
    service = HistoricalBootstrapService(db=bootstrap_db)
    summary = service.bootstrap_official_repo(
        raw_data_dir=BOOTSTRAP_FIXTURES_DIR,
        dry_run=True,
    )

    assert summary.status == "DRY_RUN"
    assert summary.total_rows_inserted == 60
    # Zero rows persisted in database
    assert bootstrap_db.query(DailyPrice).count() == 0
    assert bootstrap_db.query(MarketDataImport).count() == 0


def test_runner_bootstrap_flag(bootstrap_db: Session):
    """Verify runner executes historical bootstrap via --bootstrap-dir flag."""
    code = run_pipeline(
        bootstrap_dir=BOOTSTRAP_FIXTURES_DIR,
        db=bootstrap_db,
    )
    assert code == 0
    assert bootstrap_db.query(DailyPrice).count() == 60
    last_run = bootstrap_db.query(PipelineRun).order_by(PipelineRun.id.desc()).first()
    assert last_run is not None
    assert last_run.status == "COMPLETED"
    assert last_run.records_ingested == 60


def test_bootstrap_service_conflict_with_fractional_volume(bootstrap_db: Session, tmp_path: Path):
    """Verify volume difference between source (.5) and DB (.0) triggers conflict rollback."""
    test_dir = tmp_path / "frac_universe"
    test_dir.mkdir()
    for f in BOOTSTRAP_FIXTURES_DIR.glob("*.csv"):
        (test_dir / f.name).write_text(f.read_text())

    # Set SMPH row 1 to have volume 1000000.5
    smph_lines = (test_dir / "SMPH.csv").read_text().splitlines()
    row1_parts = smph_lines[1].split(",")
    row1_parts[5] = "1000000.5"
    smph_lines[1] = ",".join(row1_parts)
    (test_dir / "SMPH.csv").write_text("\n".join(smph_lines) + "\n")

    service = HistoricalBootstrapService(db=bootstrap_db)
    s1 = service.bootstrap_official_repo(raw_data_dir=test_dir)
    assert s1.status == "COMPLETED"

    # In DB, alter volume from 1000000.5 to 1000000.0
    smph = bootstrap_db.query(Company).filter(Company.symbol == "SMPH").first()
    p = bootstrap_db.query(DailyPrice).filter(
        DailyPrice.company_id == smph.id,
        DailyPrice.trade_date == date(2026, 9, 28),
    ).first()
    assert Decimal(str(p.volume)) == Decimal("1000000.5000")
    p.volume = Decimal("1000000.0000")
    bootstrap_db.commit()

    # Re-running bootstrap must raise HistoricalPriceConflictError
    with pytest.raises(HistoricalPriceConflictError, match="Historical price conflict for SMPH"):
        service.bootstrap_official_repo(raw_data_dir=test_dir)

    # Verify rollback: DB row remains altered, 0 partial changes committed
    bootstrap_db.rollback()
    p_check = bootstrap_db.query(DailyPrice).filter(
        DailyPrice.company_id == smph.id,
        DailyPrice.trade_date == date(2026, 9, 28),
    ).first()
    assert Decimal(str(p_check.volume)) == Decimal("1000000.0000")


def test_api_active_companies_regression():
    """Verify API endpoints /health, /api/v1/companies, /api/v1/pipeline/status on synchronized universe."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    CompanySyncService(db).sync_companies(commit=True)
    db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            # 1. Health
            r_health = client.get("/health")
            assert r_health.status_code == 200

            # 2. Companies list
            r_comps = client.get("/api/v1/companies")
            assert r_comps.status_code == 200
            comps = r_comps.json()
            assert len(comps) == 15
            returned_symbols = sorted(c["symbol"] for c in comps)
            expected_symbols = sorted(c.symbol for c in OFFICIAL_15_COMPANIES)
            assert returned_symbols == expected_symbols

            # 3. Pipeline status
            r_pipe = client.get("/api/v1/pipeline/status")
            assert r_pipe.status_code == 200
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
