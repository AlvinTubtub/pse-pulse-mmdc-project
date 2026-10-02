# End-of-Day (EOD) Market Data Ingestion

> [!NOTE]
> PSE Pulse operates as an independent personal application. Official PSE machine-readable market feeds are subscription products. The intended target format for Phase 2A is the official Philippine Stock Exchange (PSE) Daily Quotation Report (DQR) provided as a local PDF or text file.
> `PSEDQRFileProvider` parses the expected PSE DQR text layout using synthetic official-style fixtures. Compatibility with an actual official PSE Daily Quotation Report remains to be validated when the user supplies an authorized report file.

---

## 1. Pipeline Architecture

The EOD market data ingestion pipeline is structured around five decoupled stages:

```mermaid
flowchart LR
    A["Report File (PDF / TXT)"] --> B["Source Hashing & Deduplication"]
    B --> C["Provider Parsing (PSEDQRFileProvider)"]
    C --> D["Validation (DataValidator)"]
    D --> E["Idempotent Persistence (DatabaseSaver)"]
    E --> F["Provenance Logging (market_data_imports)"]
```

### Key Principles

1. **Source Independence:** The provider layer produces normalized `EODQuote` Pydantic models. Any future market data source (licensed FTP, vendor REST API) can implement `EODMarketDataProvider` without modifying validation or database persistence logic.
2. **Deterministic SHA-256 Deduplication:** Every incoming file is cryptographically hashed with SHA-256. Duplicate imports of the same file are detected and rejected before modifying the database, unless explicitly overridden with `--force`.
3. **Zero-Price Prohibition:** In PSE Daily Quotation Reports, non-traded equities have missing or dashed price fields. The pipeline strictly rejects or ignores non-traded rows rather than fabricating zeroes.
4. **Idempotent Upsert:** Re-running an import for an already processed session produces zero duplicate records. Matching prices are reported as `unchanged`, amendments are reported as `updated`, and new prices are `inserted`.
5. **Production Demo-Mode Safety:** In production (`DEMO_MODE=false`), stub forecast models are bypassed to guarantee that production databases never store synthetic predictions.

---

## 2. Ingestion CLI Usage

The pipeline is executed via the `backend.pipeline.runner` CLI entrypoint:

```bash
# Dry run: parse, validate, and check against DB without committing changes
python -m backend.pipeline.runner --source-file path/to/sample_dqr.pdf --dry-run

# Ingest an official PSE DQR file and commit to database
python -m backend.pipeline.runner --source-file path/to/sample_dqr.pdf

# Ingest market data only (skip downstream forecasting)
python -m backend.pipeline.runner --source-file path/to/sample_dqr.pdf --ingest-only

# Ingest with explicit trade date verification
python -m backend.pipeline.runner --source-file path/to/sample_dqr.pdf --trade-date 2026-10-01

# Force re-ingestion of a previously imported file
python -m backend.pipeline.runner --source-file path/to/sample_dqr.pdf --force
```

### Incoming Directory Auto-Discovery

If `--source-file` is omitted, the runner automatically inspects `data/incoming/` for recently added `.pdf`, `.txt`, or `.csv` files.

---

## 3. Financial Validation Rules

`DataValidator` enforces the following constraints before any quote reaches persistence:

- **Required Fields:** `symbol`, `trade_date`, `open_price`, `high_price`, `low_price`, `close_price`, `volume`.
- **Numeric Sanity:** `open_price`, `high_price`, `low_price`, `close_price` must be strictly positive finite numbers (`> 0`). `NaN`, `+Infinity`, and `-Infinity` are rejected.
- **OHLC Price Bounds:**
  - $\text{High} \ge \max(\text{Open}, \text{Close}, \text{Low})$
  - $\text{Low} \le \min(\text{Open}, \text{Close}, \text{High})$
- **Volume & Value:** Volume must be a non-negative integer ($\ge 0$). Turnover value (if present) must be non-negative ($\ge 0$).
- **Date Consistency:** If a target date is specified, report date must match. Future trade dates are rejected.
- **Intra-batch Deduplication:** If the report file contains duplicate quotes for the same `(symbol, trade_date)`, duplicates are rejected.

---

## 4. Provenance & Audit Log Schema (`market_data_imports`)

All import events are recorded in the `market_data_imports` table:

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer (PK) | Auto-incrementing primary key |
| `source_type` | VARCHAR(64) | Origin identifier (e.g. `PSE_DQR_FILE`) |
| `source_filename`| VARCHAR(255) | Name of the processed source file |
| `trade_date` | Date | Session trade date |
| `sha256` | VARCHAR(64) | SHA-256 cryptographic hash of source file |
| `imported_at` | DateTime (UTC) | Timestamp of import execution |
| `status` | VARCHAR(32) | Status: `COMPLETED`, `FAILED`, `DRY_RUN` |
| `records_seen` | Integer | Total quote rows read |
| `records_valid`| Integer | Rows passing validation |
| `records_inserted`| Integer | New `daily_prices` inserted |
| `records_updated` | Integer | Existing `daily_prices` updated |
| `records_rejected`| Integer | Rows failing validation |
| `error_message`| Text | Error traceback or failure details |

---

## 5. API Status Integration

The API endpoint `GET /api/v1/pipeline/status` includes provenance details from the most recent market data import under `last_market_data_import`, allowing frontend dashboards and health checks to monitor data freshness without manual database queries.

---

## 6. Actual PSE Report Compatibility

> [!WARNING]
> **Real-File Layout & Compatibility Notice:**
> - Current automated test suites and fixtures use synthetic files modeled on the expected PSE Daily Quotation Report text and table layout.
> - Actual official PSE PDF reports can exhibit complex multi-page pagination, wrapped security names, modified header formatting, or text extraction layout shifts depending on PDF generator versions.
> - **Operational Best Practice:** Operators should always run any new or previously unseen official PSE report with `--dry-run` first to inspect parsed symbols, prices, and validation results prior to committing to the database.
> - **Fail-Closed Safety:** In the event of an unparseable or unrecognized format, the parser fails closed (rejects rows or errors out) rather than guessing or fabricating numeric prices.
> - **No OCR Fallback:** The ingestion engine relies on standard text layer extraction via `pypdf`. Scanned or image-only PDF reports without embedded font text streams cannot be parsed and will fail closed.

