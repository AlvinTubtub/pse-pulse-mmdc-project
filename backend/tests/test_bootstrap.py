"""Comprehensive tests for official repository historical OHLCV bootstrap.

Covers:
- OfficialRepoHistoricalProvider parsing, schema validation, and OHLC/volume rules
- CompanySyncService idempotent synchronization
- OfficialSourceVerifier fail-closed gates (commit, clean tree, manifest, SHA-256)
- HistoricalBootstrapService all-or-nothing atomicity, idempotency, and conflict detection
- Runner bootstrap CLI integration and provenance recording
"""

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
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
from backend.pipeline.bootstrap.provenance import (
    OfficialSourceVerifier,
    VerifiedBootstrapSource,
    BootstrapSourceVerificationError,
    EXPECTED_OFFICIAL_REPOSITORY,
    EXPECTED_OFFICIAL_COMMIT,
    DEFAULT_MANIFEST_PATH,
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


@pytest.fixture
def test_verified_source():
    """A pre-verified source pointing to test fixtures for DB-layer tests."""
    manifest_hashes = {conf.symbol: "test_sha_" + conf.symbol for conf in OFFICIAL_15_COMPANIES}
    return VerifiedBootstrapSource(
        repository=EXPECTED_OFFICIAL_REPOSITORY,
        commit=EXPECTED_OFFICIAL_COMMIT,
        source_root=BOOTSTRAP_FIXTURES_DIR.parent.parent.parent,
        raw_data_dir=BOOTSTRAP_FIXTURES_DIR,
        manifest_sha256s=manifest_hashes,
    )


@pytest.fixture
def mock_verifier(test_verified_source):
    """A mock verifier that returns test_verified_source."""
    mock = MagicMock(spec=OfficialSourceVerifier)
    mock.verify.return_value = test_verified_source
    return mock


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
    """Verify provider rejects invalid price relationships (Low > High)."""
    bad_csv = tmp_path / "BAD_OHLC.csv"
    bad_csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-09-28,10,12,15,11,1000\n"
    )

    provider = OfficialRepoHistoricalProvider()
    with pytest.raises(HistoricalCsvValidationError, match="High .* cannot be below"):
        provider.parse_file(bad_csv, "BAD_OHLC")


def test_canonical_sectors_count_and_members():
    """Verify the canonical universe defines exactly 5 sectors with 3 equities each."""
    sectors = {conf.sector for conf in OFFICIAL_15_COMPANIES}
    assert len(sectors) == 5
    assert sectors == {"Financials", "Industrial", "Property", "Services", "Mining and Oil"}

    counts_by_sector = {}
    for conf in OFFICIAL_15_COMPANIES:
        counts_by_sector[conf.sector] = counts_by_sector.get(conf.sector, 0) + 1

    assert all(count == 3 for count in counts_by_sector.values())


def test_official_provider_preserves_exact_decimal_volume(tmp_path: Path):
    """Verify provider parses fractional volume into exact Decimal without rounding."""
    frac_csv = tmp_path / "FRAC.csv"
    frac_csv.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "2026-07-02,87.9,89.5,87.0,88.0,182688245.5\n"
    )

    provider = OfficialRepoHistoricalProvider()
    quotes, _ = provider.parse_file(frac_csv, "FRAC")
    assert len(quotes) == 1
    assert quotes[0].volume == Decimal("182688245.5")


# ==============================================================================
# 2. COMPANY SYNC SERVICE TESTS
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
    assert res2.total_active_companies == 15

    # Check DB state
    assert bootstrap_db.query(Sector).count() == 5
    assert bootstrap_db.query(Company).filter(Company.is_active == True).count() == 15


def test_company_sync_deactivates_obsolete_companies(bootstrap_db: Session):
    """Verify company sync automatically deactivates obsolete active companies outside 15."""
    # Seed legacy demo companies
    sector = Sector(code="LEG", name="Legacy Sector")
    bootstrap_db.add(sector)
    bootstrap_db.flush()

    dummy = Company(symbol="DUMMY", name="Dummy Demo Corp", sector_id=sector.id, is_active=True)
    bootstrap_db.add(dummy)
    bootstrap_db.commit()

    syncer = CompanySyncService(bootstrap_db)
    res = syncer.sync_companies(commit=True)
    assert res.total_active_companies == 15

    dummy_db = bootstrap_db.query(Company).filter(Company.symbol == "DUMMY").first()
    assert dummy_db is not None
    assert dummy_db.is_active is False

    active_symbols = {c.symbol for c in bootstrap_db.query(Company).filter(Company.is_active == True).all()}
    expected_symbols = {c.symbol for c in OFFICIAL_15_COMPANIES}
    assert active_symbols == expected_symbols


# ==============================================================================
# 3. PROVENANCE VERIFIER TESTS (PHASE 2B.2)
# ==============================================================================

def test_verifier_wrong_commit_raises_and_aborts(bootstrap_db: Session, tmp_path: Path):
    """Verify wrong commit HEAD raises BootstrapSourceVerificationError, aborts with FAILED status."""
    repo = tmp_path / "repo"
    (repo / "backend" / "data" / "raw").mkdir(parents=True)

    def fake_git(args, cwd):
        if args[0] == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(repo), ""
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return 0, "deadbeef1234567890abcdef1234567890abcdef", ""
        if args[0] == "status":
            return 0, "", ""
        return 1, "", "unknown"

    verifier = OfficialSourceVerifier(git_runner=fake_git)
    with pytest.raises(BootstrapSourceVerificationError, match="Source Git HEAD commit mismatch"):
        verifier.verify(source_root=repo)

    # Verify runner fail-closed behavior with wrong commit
    with patch("backend.pipeline.bootstrap.service.OfficialSourceVerifier", return_value=verifier):
        code = run_pipeline(
            bootstrap_source_root=repo,
            db=bootstrap_db,
        )
        assert code == 1
        assert bootstrap_db.query(DailyPrice).count() == 0
        run_rec = bootstrap_db.query(PipelineRun).order_by(PipelineRun.id.desc()).first()
        assert run_rec is not None
        assert run_rec.status == "FAILED"
        assert "Source Git HEAD commit mismatch" in (run_rec.error_message or "")


def test_verifier_dirty_worktree_raises_and_aborts(tmp_path: Path):
    """Verify dirty worktree raises BootstrapSourceVerificationError before any DB action."""
    repo = tmp_path / "repo"
    (repo / "backend" / "data" / "raw").mkdir(parents=True)

    def fake_git(args, cwd):
        if args[0] == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(repo), ""
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return 0, EXPECTED_OFFICIAL_COMMIT, ""
        if args[0] == "status":
            return 0, " M backend/data/raw/BPI.csv\n?? scratch.txt", ""
        return 1, "", "unknown"

    verifier = OfficialSourceVerifier(git_runner=fake_git)
    with pytest.raises(BootstrapSourceVerificationError, match="working tree is not clean"):
        verifier.verify(source_root=repo)


def test_verifier_hash_mismatch_fails_closed(tmp_path: Path):
    """Verify file SHA-256 mismatch against manifest fails closed."""
    repo_root = tmp_path / "fake_repo"
    raw_dir = repo_root / "backend" / "data" / "raw"
    raw_dir.mkdir(parents=True)
    for f in BOOTSTRAP_FIXTURES_DIR.glob("*.csv"):
        (raw_dir / f.name).write_text(f.read_text())
    # Tamper with BPI.csv
    (raw_dir / "BPI.csv").write_text("Date,Open,High,Low,Close,Volume\n2026-09-28,1,2,1,2,100\n")

    def fake_git(args, cwd):
        if args[0] == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(repo_root), ""
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return 0, EXPECTED_OFFICIAL_COMMIT, ""
        if args[0] == "status":
            return 0, "", ""
        return 1, "", "unknown"

    verifier = OfficialSourceVerifier(git_runner=fake_git)
    with pytest.raises(BootstrapSourceVerificationError, match="SHA-256 hash mismatch"):
        verifier.verify(source_root=repo_root)


def test_verifier_manifest_wrong_commit_fails_closed(tmp_path: Path):
    """Verify manifest declaring wrong source_commit fails closed."""
    bad_manifest = tmp_path / "bad_manifest.json"
    data = json.loads(DEFAULT_MANIFEST_PATH.read_text())
    data["source_commit"] = "badcommit12345678901234567890"
    bad_manifest.write_text(json.dumps(data))

    repo = tmp_path / "repo"
    (repo / "backend" / "data" / "raw").mkdir(parents=True)

    def fake_git(args, cwd):
        if args[0] == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(repo), ""
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return 0, EXPECTED_OFFICIAL_COMMIT, ""
        if args[0] == "status":
            return 0, "", ""
        return 1, "", "unknown"

    verifier = OfficialSourceVerifier(manifest_path=bad_manifest, git_runner=fake_git)
    with pytest.raises(BootstrapSourceVerificationError, match="Manifest source_commit mismatch"):
        verifier.verify(source_root=repo)


def test_verifier_missing_manifest_symbol_fails_closed(tmp_path: Path):
    """Verify manifest missing a canonical symbol fails closed."""
    bad_manifest = tmp_path / "bad_manifest.json"
    data = json.loads(DEFAULT_MANIFEST_PATH.read_text())
    data["symbols"] = [s for s in data["symbols"] if s["symbol"] != "SMPH"]
    bad_manifest.write_text(json.dumps(data))

    repo = tmp_path / "repo"
    (repo / "backend" / "data" / "raw").mkdir(parents=True)

    def fake_git(args, cwd):
        if args[0] == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(repo), ""
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return 0, EXPECTED_OFFICIAL_COMMIT, ""
        if args[0] == "status":
            return 0, "", ""
        return 1, "", "unknown"

    verifier = OfficialSourceVerifier(manifest_path=bad_manifest, git_runner=fake_git)
    with pytest.raises(BootstrapSourceVerificationError, match="Manifest symbol set mismatch"):
        verifier.verify(source_root=repo)


def test_verifier_manifest_wrong_first_trade_date_fails_closed(tmp_path: Path, bootstrap_db: Session):
    """Verify manifest with mismatched first_trade_date fails closed before DB mutation."""
    import hashlib

    repo = tmp_path / "repo"
    raw_dir = repo / "backend" / "data" / "raw"
    raw_dir.mkdir(parents=True)
    for f in BOOTSTRAP_FIXTURES_DIR.glob("*.csv"):
        (raw_dir / f.name).write_text(f.read_text())

    bad_manifest = tmp_path / "bad_manifest.json"
    data = json.loads(DEFAULT_MANIFEST_PATH.read_text())
    for sym_entry in data["symbols"]:
        fpath = raw_dir / sym_entry["source_filename"]
        sym_entry["sha256"] = hashlib.sha256(fpath.read_bytes()).hexdigest()
        sym_entry["row_count"] = 4
        lines = [line.strip() for line in fpath.read_text().splitlines() if line.strip()]
        sym_entry["first_trade_date"] = lines[1].split(",")[0].strip()
        sym_entry["last_trade_date"] = lines[-1].split(",")[0].strip()

    # Tamper with first_trade_date for first symbol
    data["symbols"][0]["first_trade_date"] = "1999-01-01"
    bad_manifest.write_text(json.dumps(data))

    def fake_git(args, cwd):
        if args[0] == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(repo), ""
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return 0, EXPECTED_OFFICIAL_COMMIT, ""
        if args[0] == "status":
            return 0, "", ""
        return 1, "", "unknown"

    verifier = OfficialSourceVerifier(manifest_path=bad_manifest, git_runner=fake_git)
    with pytest.raises(BootstrapSourceVerificationError, match="Metadata first_trade_date mismatch"):
        verifier.verify(source_root=repo)

    # Verify zero database mutations occur
    service = HistoricalBootstrapService(db=bootstrap_db, verifier=verifier)
    with pytest.raises(BootstrapSourceVerificationError, match="Metadata first_trade_date mismatch"):
        service.bootstrap_official_repo(source_root=repo)

    assert bootstrap_db.query(DailyPrice).count() == 0
    assert bootstrap_db.query(MarketDataImport).filter(
        MarketDataImport.status == "COMPLETED"
    ).count() == 0


def test_verifier_manifest_wrong_last_trade_date_fails_closed(tmp_path: Path, bootstrap_db: Session):
    """Verify manifest with mismatched last_trade_date fails closed before DB mutation."""
    import hashlib

    repo = tmp_path / "repo"
    raw_dir = repo / "backend" / "data" / "raw"
    raw_dir.mkdir(parents=True)
    for f in BOOTSTRAP_FIXTURES_DIR.glob("*.csv"):
        (raw_dir / f.name).write_text(f.read_text())

    bad_manifest = tmp_path / "bad_manifest.json"
    data = json.loads(DEFAULT_MANIFEST_PATH.read_text())
    for sym_entry in data["symbols"]:
        fpath = raw_dir / sym_entry["source_filename"]
        sym_entry["sha256"] = hashlib.sha256(fpath.read_bytes()).hexdigest()
        sym_entry["row_count"] = 4
        lines = [line.strip() for line in fpath.read_text().splitlines() if line.strip()]
        sym_entry["first_trade_date"] = lines[1].split(",")[0].strip()
        sym_entry["last_trade_date"] = lines[-1].split(",")[0].strip()

    # Tamper with last_trade_date for first symbol
    data["symbols"][0]["last_trade_date"] = "2099-12-31"
    bad_manifest.write_text(json.dumps(data))

    def fake_git(args, cwd):
        if args[0] == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(repo), ""
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return 0, EXPECTED_OFFICIAL_COMMIT, ""
        if args[0] == "status":
            return 0, "", ""
        return 1, "", "unknown"

    verifier = OfficialSourceVerifier(manifest_path=bad_manifest, git_runner=fake_git)
    with pytest.raises(BootstrapSourceVerificationError, match="Metadata last_trade_date mismatch"):
        verifier.verify(source_root=repo)

    # Verify zero database mutations occur
    service = HistoricalBootstrapService(db=bootstrap_db, verifier=verifier)
    with pytest.raises(BootstrapSourceVerificationError, match="Metadata last_trade_date mismatch"):
        service.bootstrap_official_repo(source_root=repo)

    assert bootstrap_db.query(DailyPrice).count() == 0
    assert bootstrap_db.query(MarketDataImport).filter(
        MarketDataImport.status == "COMPLETED"
    ).count() == 0


def test_verifier_arbitrary_unverified_directory_fails_closed(bootstrap_db: Session):
    """Verify unverified arbitrary directory without Git root fails closed."""
    service = HistoricalBootstrapService(db=bootstrap_db)
    with pytest.raises(BootstrapSourceVerificationError):
        service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)

    assert bootstrap_db.query(DailyPrice).count() == 0


def test_real_official_source_verifier_passes():
    """Verify local clone /tmp/pse-pulse-official-source passes all verifier gates if present."""
    source_root = Path("/tmp/pse-pulse-official-source")
    if not source_root.exists():
        pytest.skip("Official source checkout not present on machine")

    verifier = OfficialSourceVerifier()
    verified = verifier.verify(source_root=source_root)
    assert verified.commit == EXPECTED_OFFICIAL_COMMIT
    assert verified.repository == EXPECTED_OFFICIAL_REPOSITORY
    assert len(verified.manifest_sha256s) == 15


# ==============================================================================
# 4. BOOTSTRAP SERVICE TESTS (WITH VERIFIED PROVENANCE)
# ==============================================================================

def test_bootstrap_service_missing_file_fails_all_or_nothing(bootstrap_db: Session, tmp_path: Path):
    """Verify missing official CSV file aborts bootstrap with zero database changes."""
    incomplete_dir = tmp_path / "incomplete"
    incomplete_dir.mkdir()
    (incomplete_dir / "SMPH.csv").write_text(
        (BOOTSTRAP_FIXTURES_DIR / "SMPH.csv").read_text()
    )
    verified = VerifiedBootstrapSource(
        repository=EXPECTED_OFFICIAL_REPOSITORY,
        commit=EXPECTED_OFFICIAL_COMMIT,
        source_root=tmp_path,
        raw_data_dir=incomplete_dir,
        manifest_sha256s={},
    )

    service = HistoricalBootstrapService(db=bootstrap_db)
    with pytest.raises(FileNotFoundError, match="missing"):
        service.bootstrap_official_repo(verified_source=verified)

    assert bootstrap_db.query(DailyPrice).count() == 0


def test_bootstrap_service_successful_run(bootstrap_db: Session, mock_verifier, test_verified_source):
    """Verify successful 15-company bootstrap persists all quotes and audit provenance."""
    service = HistoricalBootstrapService(db=bootstrap_db, verifier=mock_verifier)
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
    for imp in imports:
        assert imp.status == "COMPLETED"
        assert imp.records_inserted == 4
        # Assert provenance values match expected official constants
        assert imp.source_repository == EXPECTED_OFFICIAL_REPOSITORY
        assert imp.source_commit == EXPECTED_OFFICIAL_COMMIT
        # Assert provenance values originate from the verified source container
        assert imp.source_repository == test_verified_source.repository
        assert imp.source_commit == test_verified_source.commit


def test_provenance_flow_from_verified_source_object(bootstrap_db: Session):
    """Verify MarketDataImport provenance values originate directly from VerifiedBootstrapSource."""
    custom_repo = "https://github.com/custom-test/custom-repo.git"
    custom_commit = "custom_verified_commit_sha_12345"
    manifest_hashes = {conf.symbol: "test_sha_" + conf.symbol for conf in OFFICIAL_15_COMPANIES}

    verified = VerifiedBootstrapSource(
        repository=custom_repo,
        commit=custom_commit,
        source_root=BOOTSTRAP_FIXTURES_DIR.parent.parent.parent,
        raw_data_dir=BOOTSTRAP_FIXTURES_DIR,
        manifest_sha256s=manifest_hashes,
    )

    service = HistoricalBootstrapService(db=bootstrap_db)
    summary = service.bootstrap_official_repo(verified_source=verified)
    assert summary.status == "COMPLETED"

    imports = bootstrap_db.query(MarketDataImport).filter(
        MarketDataImport.source_type == "OFFICIAL_REPO_BOOTSTRAP"
    ).all()
    assert len(imports) == 15
    for imp in imports:
        assert imp.source_repository == custom_repo
        assert imp.source_commit == custom_commit


def test_bootstrap_service_second_run_idempotency(bootstrap_db: Session, mock_verifier):
    """Verify re-running bootstrap is completely idempotent (0 inserted, all unchanged)."""
    service = HistoricalBootstrapService(db=bootstrap_db, verifier=mock_verifier)

    # First run
    s1 = service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)
    assert s1.total_rows_inserted == 60

    # Second run
    s2 = service.bootstrap_official_repo(raw_data_dir=BOOTSTRAP_FIXTURES_DIR)
    assert s2.total_rows_inserted == 0
    assert s2.total_rows_updated == 0
    assert s2.total_rows_unchanged == 60
    assert bootstrap_db.query(DailyPrice).count() == 60


def test_bootstrap_service_conflict_aborts_and_rolls_back(bootstrap_db: Session, mock_verifier):
    """Verify conflict with existing database row aborts bootstrap and rolls back."""
    service = HistoricalBootstrapService(db=bootstrap_db, verifier=mock_verifier)
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


def test_bootstrap_service_dry_run_zero_mutations(bootstrap_db: Session, mock_verifier):
    """Verify dry_run executes validation but leaves zero database mutations."""
    service = HistoricalBootstrapService(db=bootstrap_db, verifier=mock_verifier)
    summary = service.bootstrap_official_repo(
        raw_data_dir=BOOTSTRAP_FIXTURES_DIR,
        dry_run=True,
    )

    assert summary.status == "DRY_RUN"
    assert summary.total_rows_inserted == 60
    # Zero rows persisted in database
    assert bootstrap_db.query(DailyPrice).count() == 0
    assert bootstrap_db.query(MarketDataImport).count() == 0


def test_runner_bootstrap_flag(bootstrap_db: Session, test_verified_source):
    """Verify runner executes historical bootstrap via --bootstrap-dir flag with verified source."""
    with patch("backend.pipeline.bootstrap.service.OfficialSourceVerifier.verify", return_value=test_verified_source):
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

    verified = VerifiedBootstrapSource(
        repository=EXPECTED_OFFICIAL_REPOSITORY,
        commit=EXPECTED_OFFICIAL_COMMIT,
        source_root=tmp_path,
        raw_data_dir=test_dir,
        manifest_sha256s={},
    )
    mock = MagicMock(spec=OfficialSourceVerifier)
    mock.verify.return_value = verified

    service = HistoricalBootstrapService(db=bootstrap_db, verifier=mock)
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
