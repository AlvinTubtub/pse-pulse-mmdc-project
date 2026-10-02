# PSE Pulse Architecture & Technical Specification

> [!NOTE]
> PSE Pulse is an independent personal project engineered specifically for low-cost, low-memory hosting on an **Azure for Students** subscription.

---

## 1. High-Level System Overview

PSE Pulse combines a modern, statically compiled Next.js user interface with an asynchronous Python FastAPI backend. The entire architecture is tuned to run comfortably within **1 GiB of RAM** on an Azure `Standard_B2ats_v2` host.

```mermaid
flowchart TD
    Client["User Browser"] --> |HTTP / HTTPS| Nginx["Nginx Reverse Proxy (:80 / :443)"]
    
    subgraph "Ubuntu 24.04 LTS VM (1 GiB RAM)"
        Nginx --> |GET / | StaticFiles["Static Next.js Export (/var/www/pse-pulse/out)"]
        Nginx --> |/api/*, /docs| Backend["FastAPI / Uvicorn Service (127.0.0.1:8000)"]
        Cron["Systemd Timer (Weekdays 18:00 PHT)"] --> |Executes| Pipeline["EOD Pipeline CLI Runner"]
    end
    
    Backend --> |SQLAlchemy Connection Pool| Postgres["Azure Database for PostgreSQL (B1ms)"]
    Pipeline --> |Persists Quotes & Forecasts| Postgres
    Pipeline -.-> |Optional Backups (<5GB)| Blob["Azure Blob Storage (Standard LRS)"]
```

---

## 2. Request Flow & Routing

All incoming public traffic enters the VM via a single Azure Public IPv4:

1. **Static Frontend Requests (`/`, `/companies`, `/watchlist`, etc.):**
   - Handled entirely in Nginx kernel space via `try_files` and `sendfile`.
   - HTML files and static JavaScript chunks are served directly from disk.
   - **Zero Node.js process is required at runtime.**

2. **API & Monitoring Requests (`/api/v1/*`, `/health`, `/docs`):**
   - Reverse-proxied by Nginx to the local Uvicorn instance running on `127.0.0.1:8000`.
   - Proxy headers (`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`) pass client context securely.

3. **Background Scheduled Ingestion (`systemd` Timer):**
   - Triggers `pse-pulse-eod.service` on weekdays at 18:00 PHT.
   - Runs `backend.pipeline.runner` in a single-shot batch process.
   - Generates forecasts using active providers and updates PostgreSQL records.

---

## 3. Storage & Database Responsibilities

| Tier | Technology | Purpose |
| :--- | :--- | :--- |
| **Relational Data** | Azure Database for PostgreSQL Flexible Server (`Standard_B1ms`) | Normalised storage of companies, sectors, daily OHLC prices, forward forecasts, model metadata, and pipeline execution logs. |
| **Object Backups** | Azure Blob Storage (`Standard_LRS`, Hot) | Nightly JSON snapshots of latest predictions and historical backups (< 5 GB). |
| **Browser Storage** | `localStorage` | Client-side user watchlist and interface preferences, avoiding user state overhead on the backend. |

---

## 4. Key Architectural Design Decisions

### A. Why the Frontend is Statically Served (No Node.js Server in Production)
A continuously running Next.js Node.js server typically consumes between 150 MB and 300 MB of resident memory (RSS). On a host VM with only 1 GiB total RAM, dedicating ~30% of memory solely to an idle Node process presents a significant risk of Out-Of-Memory (OOM) crashes.
- By configuring Next.js with `output: 'export'`, build outputs are compiled ahead-of-time into pure HTML, CSS, and client-side JavaScript.
- Nginx serves these static assets with microsecond latency, zero Node runtime overhead, and negligible RAM usage (< 15 MB).

### B. Why PostgreSQL is External (Flexible Server B1ms)
Running a local PostgreSQL instance on the same 1 GiB VM alongside Nginx, FastAPI, and batch tasks would severely constrain host memory buffers.
- Azure Database for PostgreSQL Flexible Server offloads database storage, buffer pools, connection threads, and transactional durability to a managed B1ms instance (with 2 GiB dedicated RAM) included in Azure student credits.
- Isolating the database also prevents data corruption should the VM encounter memory pressure during batch runs.

### C. Why Heavy ML Training is Excluded from the Production VM
Frameworks like TensorFlow and PyTorch require hundreds of megabytes of wheel dependencies and gigabytes of memory during backpropagation and tensor transformations.
- PSE Pulse decouples the **forecasting interface** (`ForecastProvider`) from training workflows.
- In Phase 1, providers implement lightweight mathematical stubs (Lag-Informed Regression, ARIMA, LSTM projections).
- Future production machine learning models will be trained externally or offline, with only compact serialized parameters or ONNX runtimes deployed for inference.

### D. Why Public PostgreSQL Networking with Single-IP Firewall is Selected
> **Design Decision:** This personal deployment chooses PostgreSQL public access with a single-IP firewall and mandatory TLS to avoid provisioning an Azure Private DNS zone outside the explicitly approved free-service allowances.

While VNet integration is standard in enterprise environments, Azure Database for PostgreSQL Flexible Server VNet integration mandates an Azure Private DNS zone (`*.postgres.database.azure.com`). Private DNS zones incur monthly zone fees and DNS resolution charges outside the zero-cost student free-tier list.
By enabling public network access restricted exclusively to the VM's static public IPv4 via the server firewall, combined with mandatory TLS (`sslmode=require`), PSE Pulse maintains strong perimeter isolation while remaining strictly within the free-service bracket. Arbitrary public internet traffic and unapproved IP addresses are blocked at the Azure firewall layer.

---

## 5. Canonical 15-Company Domain Universe

The application tracks a canonical universe of 15 major Philippine equities across exactly **5 sectors** defined in `backend/app/domain/company_universe.py`:

- **Property (3):** `ALI` (Ayala Land), `MEG` (Megaworld), `SMPH` (SM Prime)
- **Financials (3):** `BPI` (Bank of the Philippine Islands), `MBT` (Metrobank), `SECB` (Security Bank)
- **Services (3):** `GLO` (Globe Telecom), `ICT` (ICTSI), `PGOLD` (Puregold)
- **Mining and Oil (3):** `APX` (Apex Mining), `NIKL` (Nickel Asia), `SCC` (Semirara)
- **Industrial (3):** `JFC` (Jollibee Foods), `MER` (Meralco), `SHLPH` (Shell Pilipinas)

The `CompanySyncService` (`backend/app/services/company_sync.py`) synchronizes these companies and their sectors into the PostgreSQL database idempotently, ensuring only the 15 canonical companies are marked active, before running any data ingestion or bootstrap routines.

---

## 6. Historical OHLCV Bootstrap Architecture (Phase 2B)

To provide deep historical data (2020–2026) for model scoring and backtesting, the historical bootstrap engine imports official historical datasets with strong safety guarantees:

- **All-or-Nothing Atomicity:** All 15 companies and 24,735 records are validated and committed in a single database transaction. If any symbol encounters a validation failure or price conflict, the entire transaction rolls back.
- **Conflict Detection:** Existing records are checked against incoming prices; differences trigger `HistoricalPriceConflictError` rather than silently mutating data.
- **Exact Numeric Volume Preservation:** Volume is stored as `Numeric(20, 4)` via Alembic revision `0004_change_daily_price_volume_to_numeric`, preserving all raw source volumes (including 28 banking rows with `.5` fractional turnover volume) with 100% mathematical fidelity.
- **Full Provenance Tracking:** Alembic revision `0003_add_historical_bootstrap_provenance` records repository URL, Git commit SHA, file path, symbol, date ranges, and exact mutation counts in `market_data_imports`.

---

## 7. Model Decoupling & Inference Serving (Phase 3 Architecture)

As detailed in [docs/model-porting-plan.md](model-porting-plan.md), [docs/model-artifact-contract.md](model-artifact-contract.md), and [docs/real-inference-design.md](real-inference-design.md):
- **Training is strictly offline:** Heavy libraries (PyTorch, TensorFlow, pmdarima) run on developer machines or isolated CI workers. The CLI tool `backend.app.forecasting.real.training.refit` generates versioned bundles.
- **Inference is lightweight:** Production uses pre-computed ARIMA parameters (`statsmodels.tsa.arima.model.ARIMA`) with online `append(actual, refit=False)` updating and scikit-learn Lag-Informed Regression (`StandardScaler` + `Lasso` cyclic coordinate descent).
- **Artifact Management:** Pre-trained model artifacts are versioned in `backend/artifacts/models/{bundle_version}/{symbol}/` with mandatory pre-deserialization SHA-256 manifest validation on startup.
- **Lineage Tracking:** Alembic revision `0005_add_model_artifacts_and_forecast_lineage` establishes relational lineage connecting `forecasts` to `model_artifacts`, origin dates, and price deltas.
- **Production Safety Gate:** `REAL_MODELS_ENABLED=False` is enforced by default in production settings to prevent premature activation until end-to-end evaluation is approved.
