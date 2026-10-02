# Historical OHLCV Bootstrap Audit Report

This document records the comprehensive audit and reconciliation of the historical daily OHLCV dataset ported from the pinned official source repository:

- **Source Repository:** `https://github.com/AlvinTubtub/Capstone2-A4103-DigitalDelvers-SY26-27.git`
- **Pinned Source Commit:** `b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`
- **Source Directory:** `backend/data/raw/*.csv`
- **Audit Date:** 2026-10-02
- **Bootstrap Manifest:** [`backend/bootstrap-manifests/official_repo_b8bf39f_manifest.json`](../backend/bootstrap-manifests/official_repo_b8bf39f_manifest.json)

---

## 1. Full 15-Company Universe Reconciliation

The official dataset comprises fifteen (15) core equities spanning five key sectors of the Philippine Stock Exchange. Every company file contains exactly **1,649 trading days** from **January 2, 2020 to October 1, 2026**, for an aggregate corpus of **24,735 rows**.

| Symbol | Company Name | Sector | Rows | Date Range | First Close | Last Close | SHA-256 Checksum |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **ALI** | Ayala Land, Inc. | Property | 1,649 | 2020-01-02 to 2026-10-01 | 44.90 | 35.80 | `d15fb349c16909de28d293cdd5f8429c4a4f69a2f2b1d33eef82b2194f202d51` |
| **APX** | Apex Mining Co., Inc. | Mining and Oil | 1,649 | 2020-01-02 to 2026-10-01 | 1.34 | 3.25 | `44ca7605758889730d5189c4bb8b855ce202bf6a1eba282248b1f88f427649c4` |
| **BPI** | Bank of the Philippine Islands | Financials | 1,649 | 2020-01-02 to 2026-10-01 | 87.90 | 141.50 | `22ddebe6526f4c664ea8fcb347ef754da667e0e34691741dd19920b040eca4f8` |
| **GLO** | Globe Telecom, Inc. | Services | 1,649 | 2020-01-02 to 2026-10-01 | 2,020.00 | 2,330.00 | `e5830daf700b23b47eaaccc1b5b621e74bdb74605339584fb706f681c19182a1` |
| **ICT** | International Container Terminal Services | Services | 1,649 | 2020-01-02 to 2026-10-01 | 128.00 | 405.00 | `37b43032eb2fcf5a54a7a065bb4844f210e20643dfa6f5586ac0159284caa0a8` |
| **JFC** | Jollibee Foods Corporation | Industrial | 1,649 | 2020-01-02 to 2026-10-01 | 214.00 | 262.00 | `1ce4b7c7c5c91f451beee4c70140db564e68c775ead35a49f0eebb45e92ddd9d` |
| **MBT** | Metropolitan Bank & Trust Company | Financials | 1,649 | 2020-01-02 to 2026-10-01 | 66.30 | 76.50 | `567199389b58ffda3c4a8be5aadc2f0dc66d1365f00eaf7302c03e1359cf0e0d` |
| **MEG** | Megaworld Corporation | Property | 1,649 | 2020-01-02 to 2026-10-01 | 4.01 | 2.15 | `7fdc5038bff1db1d563e1d601a51ced86319a4f8ee219d78f34fd2ee8cb28eed` |
| **MER** | Manila Electric Company | Industrial | 1,649 | 2020-01-02 to 2026-10-01 | 317.00 | 425.00 | `937cdee1bb02a27f4c7bb419109e8e685ef8cf2220c66af5de6db16032fdb862` |
| **NIKL**| Nickel Asia Corporation | Mining and Oil | 1,649 | 2020-01-02 to 2026-10-01 | 2.45 | 3.80 | `8d523b0a410613cd853f0258a72c733a99db639120183992c434cd46c975c7f2` |
| **PGOLD**| Puregold Price Club, Inc. | Services | 1,649 | 2020-01-02 to 2026-10-01 | 39.80 | 32.50 | `fb200d59909c12109fe91906fd67b2de2be7d92e7bde1e68d1f995cb885da3e4` |
| **SCC** | Semirara Mining and Power Corp. | Mining and Oil | 1,649 | 2020-01-02 to 2026-10-01 | 21.65 | 33.40 | `a021416b025e5f58ed8a9f777600635d6239d220ec011a73f370c5ec354844c4` |
| **SECB**| Security Bank Corporation | Financials | 1,649 | 2020-01-02 to 2026-10-01 | 196.00 | 88.00 | `a383fc2f07e2e2eb279a09ef0bd36eff59e45a6304725bf09c5972dd523f2e46` |
| **SHLPH**| Shell Pilipinas Corporation | Industrial | 1,649 | 2020-01-02 to 2026-10-01 | 32.60 | 14.12 | `3a709ea69eb03a5402c207b47a17e4834b82980a7732f201ecdb2a85b5b15b7e` |
| **SMPH**| SM Prime Holdings, Inc. | Property | 1,649 | 2020-01-02 to 2026-10-01 | 42.10 | 31.00 | `4940470d00520dad4679f33bde4979a37d62c892c5acbbd171d8c8dba2dcde27` |
| **TOTAL**| **15 Companies** | **5 Sectors** | **24,735** | **2020-01-02 to 2026-10-01** | — | — | **15 SHA-256 Verified Files** |

---

## 2. Data Quality & Integrity Validation

All 24,735 rows across the 15 CSV files underwent comprehensive automated data quality auditing against production standards:

1. **Null Check:** 0 null cells across all columns (`Date, Open, High, Low, Close, Volume`).
2. **Date Continuity:** Exactly 1,649 trading sessions.
3. **Cross-Company Synchronicity:** Every trading date is present across all 15 symbols simultaneously. There are zero partial-coverage dates or missing symbol sessions.
4. **OHLC Bounding Rules:**
   - $\text{High} \ge \text{Low}$: 24,735 / 24,735 (100.0% valid).
   - $\text{High} \ge \max(\text{Open}, \text{Close})$: 24,735 / 24,735 (100.0% valid).
   - $\text{Low} \le \min(\text{Open}, \text{Close})$: 24,735 / 24,735 (100.0% valid).
   - $\text{Price} > 0$: 24,735 / 24,735 (100.0% valid).
   - $\text{Volume} \ge 0$: 24,735 / 24,735 (100.0% valid).

---

## 3. Analysis & Treatment of Fractional Volume Anomaly

During precision validation, an anomaly was identified in the raw source files: **28 rows across 3 banking symbols contain `.5` fractional volume values**.

### 3.1 Distribution of Fractional Rows

All 28 instances occurred during July and August 2026:

| Symbol | Total Instances | Date Range | Sample Values |
| :--- | :---: | :---: | :--- |
| **BPI** | 1 | 2026-07-02 | `182,688,245.5` |
| **MBT** | 17 | 2026-07-03 to 2026-07-31 | `47,807,302.5`, `160,914,164.5`, `118,339,467.5` |
| **SECB** | 10 | 2026-07-06 to 2026-08-03 | `23,698,886.5`, `18,527,872.5`, `14,220,510.5` |
| **Total** | **28** | **2026-07-02 to 2026-08-03** | — |

The remaining 24,707 rows across the universe contain integer volumes (represented as `.0` in CSV floats).

### 3.2 Root Cause Analysis
Philippine Stock Exchange equities trade exclusively in integer shares according to board-lot rules. The `.5` fractional volume observed in these banking equities originates from upstream web scraping / data extraction in the research repo that computed volume by dividing reported daily turnover by an average execution price, or odd-lot block trades weighted across cross-trades.

### 3.3 Fractional Volume Fidelity in PSE Pulse Architecture
In PostgreSQL and SQLite, trading volume was previously stored in `daily_prices.volume` as a `BigInteger` (`int8`). To eliminate truncation and preserve the official historical source data with 100% mathematical fidelity, Alembic revision `0004_change_daily_price_volume_to_numeric` migrates `daily_prices.volume` to `Numeric(20, 4)`.

Key Guarantees:
1. **Zero Rounding or Imputation:** Source CSV volume values are parsed directly from raw strings using `Decimal(raw_value.strip())`. Rounding, flooring, ceiling, or integer casting is completely eliminated.
2. **Exact Source Parity:** All 28 fractional rows (BPI: 1 row, MBT: 17 rows, SECB: 10 rows) store exact decimal values (e.g. `182688245.5000` for raw `182688245.5`).
3. **Whole-Dataset Parity:** Across all 24,735 rows, database values match the source files with exactly **0 OHLC mismatches, 0 volume mismatches, and 0 date mismatches**.
4. **Exact Conflict Detection:** The bootstrap conflict detector compares volume as exact `Decimal` values via `_dec_equal`. If database volume has `X.0` and source has `X.5`, `HistoricalPriceConflictError` triggers immediately, protecting data integrity.

---

## 4. Idempotency & Provenance Guarantees

The historical bootstrap pipeline enforces:

1. **Atomic Ingestion:** All 15 companies and 24,735 rows are committed inside a single database transaction. If any company fails validation or a price conflict is detected, the entire transaction rolls back.
2. **Duplicate Run Idempotency:** Executing the bootstrap against an already populated database results in `0 inserted, 0 updated, 24,735 unchanged`, with zero row duplication.
3. **Conflict Detection:** If an existing `daily_prices` record differs in OHLCV values from the bootstrap file, `HistoricalPriceConflictError` is raised immediately, halting execution and preventing silent overwrites.
4. **Provenance Tracking:** Every execution creates an immutable audit record in `market_data_imports` with `source_type="historical_bootstrap"`, recording:
   - `source_repository`: Official GitHub repository URL
   - `source_commit`: Pinned Git commit SHA (`b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`)
   - `source_path`: Relative file path within the source repository
   - `file_hash`: SHA-256 checksum of the ingested file
   - `first_trade_date` & `last_trade_date`: Precise temporal boundaries
   - `records_inserted`, `records_updated`, `records_unchanged`: Exact mutation counts.

---

## 5. Fail-Closed Provenance Verification (Phase 2B.2)

To prevent unverified or arbitrary directories from receiving pinned official source provenance stamps, PSE Pulse implements `OfficialSourceVerifier`:

1. **Gate 1 — Git Repository Root & Canonical Path:** Verifies that the supplied path belongs to a valid Git repository root and resolves canonically to `<source_root>/backend/data/raw`. Arbitrary directories or path traversals fail immediately.
2. **Gate 2 — Git HEAD Commit:** Verifies programmatically via `git -C <root> rev-parse HEAD` that the repository checkout matches the exact pinned official commit (`b8bf39f8e94729687c2e877dc164ea8a4f69e2b1`).
3. **Gate 3 — Clean Working Tree:** Verifies programmatically via `git -C <root> status --porcelain=v1` that the checkout is untouched (empty status). Any uncommitted modifications, deletions, or untracked files fail closed.
4. **Gate 4 — Committed Manifest & SHA-256 Parity:** Validates all 15 raw CSV files against `backend/bootstrap-manifests/official_repo_b8bf39f_manifest.json`. Every file must match the authoritative SHA-256 hash, row count (1,649 data rows), and trade date bounds.

Database provenance fields (`source_repository`, `source_commit`) in `MarketDataImport` are populated strictly from the resulting `VerifiedBootstrapSource` container. Any verification failure aborts execution before any Company, Sector, DailyPrice, or MarketDataImport bootstrap records are created or modified (yielding 0 market data mutations; dry-run persists zero database mutations across all tables, while a non-dry-run runner safely persists a `PipelineRun` record with status `FAILED`).
