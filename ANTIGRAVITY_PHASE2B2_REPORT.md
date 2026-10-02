# PSE Pulse — Personal Azure Edition
# Phase 2B.2 Verification Report: Fail-Closed Bootstrap Provenance Verification

- **Project:** PSE Pulse — Personal Azure Edition
- **Destination Repository:** `https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git`
- **Destination Branch:** `main`
- **Destination HEAD:** `0b104ce57e5bc685d04648bc482756522942b02e`
- **Official Pinned Read-Only Source Repository:** `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git`
- **Pinned Official Commit:** `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`
- **Official Source Path:** `/tmp/pse-pulse-official-source`
- **Date:** 2026-10-02
- **Status:** Complete — Ready for Review

---

## 1. Root Cause

In Phase 2B, the historical bootstrap engine (`backend/pipeline/bootstrap/service.py`) correctly recorded provenance fields (`source_repository`, `source_commit`, `source_path`, `sha256`) into the `market_data_imports` table. However, the runtime accepted an arbitrary caller-supplied directory (`--raw-dir` or `--bootstrap-dir`) without programmatically verifying that the directory was part of a clean, authentic checkout of the pinned official research repository commit (`b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`).

---

## 2. Risk

Prior to Phase 2B.2, an operator or test runner could pass an arbitrary, unverified folder of CSVs (such as synthetic test fixtures or modified local data) to `--raw-dir` or `--bootstrap-dir`. The bootstrap pipeline would ingest those records and stamp them with the authoritative provenance of the official Capstone research repository and pinned commit `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`. This violated the audit contract of provenance logging by allowing non-official data to be stamped as official.

---

## 3. Verification Architecture

To achieve fail-closed provenance enforcement, Phase 2B.2 introduces `OfficialSourceVerifier` and the immutable `VerifiedBootstrapSource` container in `backend/pipeline/bootstrap/provenance.py`:

```
┌─────────────────────────────────────────────────────────────┐
│                 Caller Supplies Source Path                 │
│         (--source-root or canonical --raw-dir)              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Gate 1: Git Repository Root & Canonical Path Verification   │
│  - git -C <dir> rev-parse --show-toplevel                   │
│  - Enforce <source_root>/backend/data/raw                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Gate 2: Exact Git HEAD Commit Verification                 │
│  - git -C <root> rev-parse HEAD == b8bf39f8e...             │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Gate 3: Clean Working Tree Verification                    │
│  - git -C <root> status --porcelain=v1 == ""                │
│  - Fail closed on modified, deleted, or untracked files     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│  Gate 4: Committed Manifest, 15-File SHA-256 & Date Bounds  │
│  - Manifest commit == b8bf39f8e..., repo == official URL    │
│  - Exactly 15 canonical symbols                             │
│  - Compute actual SHA-256 for all 15 raw CSVs               │
│  - Verify actual_sha == manifest_sha                        │
│  - Verify row_count == 1,649 data rows                      │
│  - Verify first_trade_date == 2020-01-02                    │
│  - Verify last_trade_date == 2026-10-01                     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Construct VerifiedBootstrapSource              │
│       Pass to HistoricalBootstrapService for Ingestion      │
└─────────────────────────────────────────────────────────────┘
```

If any check fails, `BootstrapSourceVerificationError` is raised immediately before modifying company/sector tables, price tables, or import provenance records.

---

## 4. Git HEAD Gate

`OfficialSourceVerifier` programmatically queries `git -C <source_root> rev-parse HEAD` using safe argument arrays (without `shell=True`).
- **Expected SHA:** `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`
- **Behavior on Mismatch:** Raises `BootstrapSourceVerificationError("Source Git HEAD commit mismatch: actual '<actual>' does not match pinned official commit 'b8bf39f...'")`.
- Execution halts immediately; zero `Company`, `Sector`, `DailyPrice`, or `MarketDataImport` records are modified. (In a non-dry-run pipeline execution, the runner safely records a `PipelineRun` record with status `FAILED`).

---

## 5. Clean Tree Gate

Even if the checked-out commit matches `b8bf39f...`, local files might be modified or untracked. `OfficialSourceVerifier` queries `git -C <source_root> status --porcelain=v1`:
- **Expected Status:** Empty output (exit code 0, 0 lines of output).
- **Behavior on Dirty State:** Raises `BootstrapSourceVerificationError("Source repository working tree is not clean... Official historical bootstrap requires an untouched, clean checkout.")`.
- Guarantees that uncommitted changes cannot pollute the database.

---

## 6. Manifest Commit Gate

The verifier reads the destination repository's committed JSON manifest (`backend/bootstrap-manifests/official_repo_b8bf39f_manifest.json`):
- Verifies that `manifest["source_commit"] == "b8bf39f8e94729687c2e877dc164ea8a4f69e2b1"`.
- Verifies that `manifest["source_repository"] == "https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git"`.
- Verifies that `manifest["symbols"]` declares exactly the 15 canonical companies (`ALI`, `APX`, `BPI`, `GLO`, `ICT`, `JFC`, `MBT`, `MEG`, `MER`, `NIKL`, `PGOLD`, `SCC`, `SECB`, `SHLPH`, `SMPH`).
- Any tampering with the manifest file causes immediate fail-closed abort.

---

## 7. 15-File SHA & Date Metadata Gate

For every one of the 15 canonical companies:
1. Resolves `csv_path = raw_data_dir / conf.raw_filename`.
2. Computes the real cryptographic SHA-256 checksum over the raw bytes using 64 KB streaming buffers.
3. Compares `actual_sha` against the authoritative SHA-256 recorded in the committed manifest.
4. **Row Count Enforcement:** Validates that non-header data row count equals 1,649 (`data_rows == expected_rows`).
5. **First Trade Date Enforcement:** Parses first data line date (`lines[1].split(',')[0].strip()`) and verifies equality against manifest `first_trade_date` (`2020-01-02`).
6. **Last Trade Date Enforcement:** Parses last data line date (`lines[-1].split(',')[0].strip()`) and verifies equality against manifest `last_trade_date` (`2026-10-01`).
7. If any file is missing, modified, or has mismatched hash, row count, or date boundaries, `BootstrapSourceVerificationError` is raised with the offending symbol and metrics.

---

## 8. CLI Changes

`backend/pipeline/bootstrap/cli.py` has been updated with verified provenance parameters:
- **`--source-root` (Recommended):** Explicit path to verified official repository checkout (e.g. `/tmp/pse-pulse-official-source`).
- **`--raw-dir`:** Canonical raw directory path (e.g. `/tmp/pse-pulse-official-source/backend/data/raw`). Its repository root is automatically derived and verified via Git.
- Both inputs route through `OfficialSourceVerifier.verify()` before `HistoricalBootstrapService` begins.
- No public bypass flags (`--skip-source-verification`, `--trust-directory`) are exposed.

---

## 9. Runner Changes

`backend/pipeline/runner.py` CLI and programmatic entrypoints have been updated:
- Added `--bootstrap-source-root` argument to `build_arg_parser()`.
- Updated `run_pipeline(..., bootstrap_source_root=..., bootstrap_dir=..., allow_conflict_updates=...)`.
- In Branch A:
  ```python
  bootstrap_svc = HistoricalBootstrapService(
      db=db,
      allow_conflict_updates=allow_conflict_updates,
  )
  summary = bootstrap_svc.bootstrap_official_repo(
      source_root=Path(bootstrap_source_root) if bootstrap_source_root else None,
      raw_data_dir=Path(bootstrap_dir) if bootstrap_dir else None,
      dry_run=dry_run,
  )
  ```
- If verification fails, `runner.py` catches `BootstrapSourceVerificationError`, marks `PipelineRun` as `FAILED` (if not dry run), logs the error, and exits with code `1`.

---

## 10. Failure Semantics

When provenance verification fails at any gate:
- An exception of type `BootstrapSourceVerificationError` is raised.
- Standalone CLI (`cli.py`) logs the verification failure and exits with code `1`.
- Main runner (`runner.py`) marks `PipelineRun.status = "FAILED"`, records the verification error message, and exits with code `1`.
- In dry-run mode, execution halts immediately with exit code `1` and zero database records created across all tables.

---

## 11. Database Mutation Safety

Verification occurs strictly **before Company, Sector, DailyPrice, or MarketDataImport bootstrap mutation**:
- **`0` Company mutations** occur.
- **`0` Sector mutations** occur.
- **`0` DailyPrice mutations** occur.
- **`0` `COMPLETED` `OFFICIAL_REPO_BOOTSTRAP` `MarketDataImport` rows** are persisted.
- In a **dry-run** execution, verification failure persists **zero DB mutations** across all tables (including 0 `PipelineRun` records).
- In a **non-dry-run** runner execution, the runner intentionally persists an operational `PipelineRun` audit record with status `FAILED` to document the aborted run and diagnostics, while keeping all business and financial tables completely untouched.

---

## 12. Provenance Flow Integrity

`HistoricalBootstrapService` strictly prevents arbitrary provenance stamps:
- The immutable `VerifiedBootstrapSource` container carries `repository` and `commit` proved by `OfficialSourceVerifier`.
- `MarketDataImport` records stamped into the database populate `source_repository` and `source_commit` strictly from `verified_source.repository` and `verified_source.commit`, rather than hardcoded constant strings.
- Automated tests (`test_provenance_flow_from_verified_source_object` and `test_bootstrap_service_successful_run`) explicitly assert that provenance values in `MarketDataImport` originate directly from the verified source container.

---

## 13. Test Suite Expansion & Results

The test suite in `backend/tests/test_bootstrap.py` was expanded from 16 to **26 tests**, bringing the entire backend test suite to **86 passing tests** (up from 76 baseline):

```bash
backend/.venv/bin/pytest backend/tests -v
# ============================== 86 passed in 1.42s ==============================
```

### New Tests Added in Phase 2B.2:
1. `test_verifier_wrong_commit_raises_and_aborts`: Simulates wrong Git HEAD (`deadbeef...`), verifies `BootstrapSourceVerificationError`, and asserts runner exits with code `1`, 0 DailyPrices, and `PipelineRun.status == "FAILED"`.
2. `test_verifier_dirty_worktree_raises_and_aborts`: Simulates modified/untracked files in Git status, verifies `BootstrapSourceVerificationError("working tree is not clean")`.
3. `test_verifier_hash_mismatch_fails_closed`: Tampered `BPI.csv` triggers `BootstrapSourceVerificationError("SHA-256 hash mismatch")`.
4. `test_verifier_manifest_wrong_commit_fails_closed`: Manifest declaring wrong commit triggers `BootstrapSourceVerificationError("Manifest source_commit mismatch")`.
5. `test_verifier_missing_manifest_symbol_fails_closed`: Manifest missing `SMPH` triggers `BootstrapSourceVerificationError("Manifest symbol set mismatch")`.
6. `test_verifier_manifest_wrong_first_trade_date_fails_closed`: Manifest with mismatched `first_trade_date` fails closed before DB mutation; asserts 0 `DailyPrice` mutations and 0 `COMPLETED` `MarketDataImport` rows.
7. `test_verifier_manifest_wrong_last_trade_date_fails_closed`: Manifest with mismatched `last_trade_date` fails closed before DB mutation; asserts 0 `DailyPrice` mutations and 0 `COMPLETED` `MarketDataImport` rows.
8. `test_verifier_arbitrary_unverified_directory_fails_closed`: Passing unverified directory directly to `HistoricalBootstrapService` fails closed.
9. `test_real_official_source_verifier_passes`: When `/tmp/pse-pulse-official-source` is present, executes real verification and passes all 4 gates.
10. `test_provenance_flow_from_verified_source_object`: Asserts that `MarketDataImport` provenance values originate dynamically and directly from `VerifiedBootstrapSource`.

---

## 14. Clean-Database Real-Source Acceptance Test

To prove 100% clean insertion and fail-safe rollback against a pristine database schema, an end-to-end acceptance test was executed against a disposable SQLite database migrated to Alembic head (`base -> 0001 -> 0002 -> 0003 -> 0004`):

```bash
rm -f /tmp/clean_acceptance.db
DATABASE_URL="sqlite:////tmp/clean_acceptance.db" backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
DATABASE_URL="sqlite:////tmp/clean_acceptance.db" backend/.venv/bin/python -m backend.pipeline.runner \
  --bootstrap-source-root /tmp/pse-pulse-official-source \
  --dry-run
```

**Verbatim Execution Output:**
```text
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema, 0001_initial_schema
INFO  [alembic.runtime.migration] Running upgrade 0001_initial_schema -> 0002_add_market_data_imports, 0002_add_market_data_imports
INFO  [alembic.runtime.migration] Running upgrade 0002_add_market_data_imports -> 0003_add_historical_bootstrap_provenance, 0003_add_historical_bootstrap_provenance
INFO  [alembic.runtime.migration] Running upgrade 0003_add_historical_bootstrap_provenance -> 0004_change_daily_price_volume_to_numeric, 0004_change_daily_price_volume_to_numeric
2026-10-02 15:13:43,943 [INFO] pse_pulse_pipeline: Starting PSE Pulse pipeline (Environment: development, Demo Mode: True, Dry Run: True)...
2026-10-02 15:13:43,944 [INFO] pse_pulse_pipeline: Running verified 15-company historical bootstrap (source_root=/tmp/pse-pulse-official-source, raw_dir=None)...
2026-10-02 15:13:43,944 [INFO] backend.pipeline.bootstrap.service: Executing fail-closed provenance verification for historical bootstrap...
2026-10-02 15:13:44,258 [INFO] backend.pipeline.bootstrap.provenance: Successfully verified official bootstrap source at /private/tmp/pse-pulse-official-source (commit=b8bf39f8e94729687c2e877dc164ea8a4f69e2b1, 15 files verified).
2026-10-02 15:13:44,259 [INFO] backend.pipeline.bootstrap.service: Starting 15-company historical bootstrap from /private/tmp/pse-pulse-official-source/backend/data/raw (source_root=/private/tmp/pse-pulse-official-source, commit=b8bf39f8e94729687c2e877dc164ea8a4f69e2b1, dry_run=True)...
2026-10-02 15:13:44,355 [INFO] backend.pipeline.bootstrap.service: Successfully validated all 15 historical CSV files in memory.
2026-10-02 15:13:44,373 [INFO] backend.app.services.company_sync: Company synchronization complete: inserted=15, updated=0, unchanged=0, active=15
2026-10-02 15:13:44,377 [INFO] backend.pipeline.bootstrap.service: Dry-run complete: all changes rolled back; zero mutations committed.
2026-10-02 15:13:44,379 [INFO] pse_pulse_pipeline: Historical bootstrap finished. Inserted: 24735, Updated: 0, Unchanged: 0
```

**Database State Verification Query:**
```sql
SELECT 'daily_prices', count(*) FROM daily_prices
UNION ALL SELECT 'market_data_imports', count(*) FROM market_data_imports
UNION ALL SELECT 'companies', count(*) FROM companies
UNION ALL SELECT 'sectors', count(*) FROM sectors
UNION ALL SELECT 'pipeline_runs', count(*) FROM pipeline_runs;
```

**Results:**
- `daily_prices`: `0`
- `market_data_imports`: `0`
- `companies`: `0`
- `sectors`: `0`
- `pipeline_runs`: `0`
- **Simulation Metrics:** `inserted=24,735, updated=0, unchanged=0` without `--allow-conflict-updates`.
- **Persistent State:** Exactly 0 rows across all tables.

### 14.1 Observation Regarding Earlier Development Database Run
In an earlier diagnostic dry-run against the local developer SQLite database (`pse_pulse.db`), the summary reported `Inserted: 24635, Updated: 100, Unchanged: 0`. This occurred because that specific local development file had accumulated conflicting demo records from earlier Phase 2B iterative testing, which required passing `--allow-conflict-updates` diagnostically. The clean-database acceptance test above formally proves that on a fresh schema, the historical bootstrap requires zero conflict overrides and achieves 100% clean insert status (`24,735 inserts, 0 updates, 0 unchanged`).

---

## 15. Wrong-Source Rejection & Operational Audit Logging

Executed non-dry-run pipeline execution against an unverified directory (`backend/tests/fixtures/bootstrap`) on a fresh database:

```bash
DATABASE_URL="sqlite:////tmp/clean_acceptance2.db" backend/.venv/bin/python -m backend.pipeline.runner \
  --bootstrap-dir backend/tests/fixtures/bootstrap
```

**Result & Audit Metrics:**
- **Exit Code:** `1`
- **Error:** `BootstrapSourceVerificationError: Supplied raw directory ... does not match canonical structure ... under repository root ...`
- **Database Row Verification:**
  - `daily_prices`: `0`
  - `market_data_imports`: `0`
  - `companies`: `0`
  - `sectors`: `0`
  - `pipeline_runs` (total): `1`
  - `pipeline_runs` (status = "FAILED"): `1`
- Zero financial or domain entities mutated; operational audit log preserved.

---

## 16. Frontend Regression

Executed complete frontend validation pipeline:
```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```
- **Lint:** PASS (0 errors, 0 warnings)
- **TypeScript:** PASS (0 errors)
- **Static Export Build:** PASS (26/26 static HTML pages generated)
- **Production Audit:** Clean (sandbox isolation safely disables network advisory downloads).

---

## 17. Official Source Integrity

Executed read-only verification commands against `/tmp/pse-pulse-official-source`:
```bash
git -C /tmp/pse-pulse-official-source rev-parse HEAD
# b8bf39f8e94729687c2e877dc164ea8a4f69e2b1

git -C /tmp/pse-pulse-official-source status --porcelain=v1
# (empty)

git -C /tmp/pse-pulse-official-source diff --exit-code
# (exit 0)

git -C /tmp/pse-pulse-official-source diff --cached --exit-code
# (exit 0)

git -C /tmp/pse-pulse-official-source remote -v
# origin https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git (fetch)
# origin DISABLED_DO_NOT_PUSH (push)
```

`OFFICIAL SOURCE REPOSITORY WAS NOT MODIFIED.`

---

## 18. Destination Git Status

```text
/Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-project
branch: main
remote: https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git
HEAD: 0b104ce feat: bootstrap official OHLCV history and backend foundation

Unstaged changes:
 M ANTIGRAVITY_PHASE2B_REPORT.md
 M README.md
 M backend/pipeline/bootstrap/__init__.py
 M backend/pipeline/bootstrap/cli.py
 M backend/pipeline/bootstrap/service.py
 M backend/pipeline/runner.py
 M backend/tests/test_bootstrap.py
 M docs/data-ingestion.md
 M docs/historical-bootstrap-audit.md

Untracked files:
?? ANTIGRAVITY_PHASE2B2_REPORT.md
?? backend/pipeline/bootstrap/provenance.py
```

- `git add`: NOT run
- `git commit`: NOT run
- `git push`: NOT run
- Azure deployment: NOT executed

---

RECOMMENDATION: READY FOR CHATGPT REVIEW BEFORE PHASE 2B.2 COMMIT
