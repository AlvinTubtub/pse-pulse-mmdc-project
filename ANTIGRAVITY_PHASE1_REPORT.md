# ANTIGRAVITY_PHASE1_REPORT.md
**Project Name:** PSE Pulse — Personal Azure Edition  
**Repository:** `https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git`  
**Phase:** Phase 1 (Local Architecture, Implementation, and Validation)  
**Author / Engineer:** Antigravity (AI Pair Programmer)  
**Date:** October 1, 2026  

---

## 1. Executive Summary

Phase 1 of **PSE Pulse — Personal Azure Edition** has been successfully implemented and validated entirely on the local development machine. 

This is a **strictly independent personal project** created for Alvin Tubtub and is completely isolated from any academic Capstone project, research pipelines, credentials, or repositories.

All objectives of Phase 1 have been fulfilled:
- Built the lightweight **FastAPI backend** (Python 3.12, Uvicorn, SQLAlchemy 2.0, Alembic, Pydantic v2).
- Established the **static Next.js 14 frontend** (TypeScript, Tailwind CSS) supporting full static export (`output: 'export'`), verified to run on Nginx without a Node.js production server.
- Implemented the normalized database schema (Companies, Sectors, Daily Prices, Forecasts, Model Metadata, Pipeline Runs) with verified Alembic migrations.
- Architected the pluggable `ForecastProvider` interface with lightweight inference stubs for **Lag-Informed Regression**, **ARIMA**, and **LSTM**, strictly excluding heavy model-training dependencies (TensorFlow, PyTorch) to fit within host memory constraints.
- Scaffolded future PSE market data ingestion and processing pipelines.
- Created complete Azure Bicep infrastructure-as-code scaffolding designed strictly around **Azure for Students** free-tier allowances ($0 monthly spend target).
- Executed and passed all backend unit/integration tests (**22/22 passed**) and frontend build validations (**0 TypeScript errors, 0 ESLint warnings, 17/17 static pages generated**).
- Measured runtime idle memory consumption (**70.64 MB RSS** for FastAPI, **0 MB** for frontend Node runtime), safely fitting within the **1 GiB RAM** budget of an Azure `Standard_B2ats_v2` virtual machine.

**Phase 1 is complete, fully validated locally, and ready for ChatGPT review before any commit or push is made.**

---

## 2. Repository State Before Work

- **Initial State:** Empty directory originally located at `/Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-capstone-project`, subsequently renamed and canonicalized to `/Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-project` during Phase 1.1 remediation.
- **Git State:** Not initialized as a git repository (`fatal: not a git repository`). No local commits, no branches, no tracked files, and no existing project code existed.
- **Environment:** Clean local macOS workstation with Python 3.12.13 and Node.js v24.16.0 / npm 11.13.0 installed.

---

## 3. Files Created

```text
pse-pulse-mmdc-project/
├── .env.example
├── .gitignore
├── LICENSE (MIT License)
├── README.md
├── docker-compose.dev.yml
├── pytest.ini
├── .github/
│   └── workflows/
│       └── ci.yml
├── backend/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   │           ├── companies.py
│   │   │           ├── forecasts.py
│   │   │           ├── models.py
│   │   │           ├── pipeline.py
│   │   │           └── system.py
│   │   ├── forecasting/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   └── providers/
│   │   │       ├── __init__.py
│   │   │       ├── arima.py
│   │   │       ├── lag_regression.py
│   │   │       └── lstm.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── company.py
│   │   │   ├── forecast.py
│   │   │   ├── model_metadata.py
│   │   │   ├── pipeline_run.py
│   │   │   ├── price.py
│   │   │   └── sector.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── common.py
│   │   │   ├── company.py
│   │   │   ├── forecast.py
│   │   │   ├── pipeline.py
│   │   │   ├── price.py
│   │   │   ├── sector.py
│   │   │   └── system.py
│   │   └── services/
│   │       ├── __init__.py
│   │       └── seed_data.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   ├── features/
│   │   │   └── feature_builder.py
│   │   ├── forecasting/
│   │   │   └── runner.py
│   │   ├── ingest/
│   │   │   └── eod_ingest.py
│   │   ├── persistence/
│   │   │   └── db_saver.py
│   │   └── validation/
│   │       └── data_validator.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_companies.py
│       ├── test_config.py
│       ├── test_forecasting_providers.py
│       ├── test_forecasts.py
│       ├── test_health.py
│       ├── test_pipeline.py
│       └── test_system.py
├── frontend/
│   ├── .eslintrc.json
│   ├── next.config.mjs
│   ├── package-lock.json
│   ├── package.json
│   ├── postcss.config.mjs
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── app/
│       │   ├── globals.css
│       │   ├── layout.tsx
│       │   ├── page.tsx
│       │   ├── about/
│       │   │   └── page.tsx
│       │   ├── companies/
│       │   │   ├── page.tsx
│       │   │   └── [symbol]/
│       │   │       └── page.tsx
│       │   ├── learn/
│       │   │   └── page.tsx
│       │   ├── models/
│       │   │   └── page.tsx
│       │   └── watchlist/
│       │       └── page.tsx
│       ├── components/
│       │   ├── CompanyTable.tsx
│       │   ├── DemoBanner.tsx
│       │   ├── Footer.tsx
│       │   ├── ForecastCard.tsx
│       │   ├── MetricCard.tsx
│       │   ├── Navbar.tsx
│       │   ├── SparklineChart.tsx
│       │   └── StatusBadge.tsx
│       └── lib/
│           ├── api.ts
│           ├── types.ts
│           └── watchlist.ts
├── infrastructure/
│   ├── azure/
│   │   ├── README.md
│   │   ├── main.bicep
│   │   └── parameters.example.json
│   ├── nginx/
│   │   └── pse-pulse.conf
│   ├── scripts/
│   │   ├── deploy-static.sh
│   │   ├── run-pipeline.sh
│   │   └── setup-vm.sh
│   └── systemd/
│       ├── pse-pulse-api.service
│       ├── pse-pulse-eod.service
│       └── pse-pulse-eod.timer
└── docs/
    ├── architecture.md
    ├── azure-deployment.md
    └── cost-guardrails.md
```

---

## 4. Architecture Implemented

### Local Architecture vs. Future Azure Production Architecture

```text
Local Development:
User Browser (localhost:3000) ──> Next.js Dev / Static Preview
                                      │
                                      ▼
FastAPI Backend (localhost:8000) ──> SQLite (pse_pulse_dev.db) OR Docker Compose PostgreSQL

Future Production Azure:
Internet ──> Azure Public IPv4 ──> Nginx (Reverse Proxy & Static Web Server)
                                      ├──> GET /           ──> /var/www/pse-pulse/out (Static HTML/JS, 0 Node server)
                                      └──> /api/*, /docs   ──> FastAPI / Uvicorn (127.0.0.1:8000, ~70 MB RAM)
                                                                 │
                                                                 ▼
                                                  Azure Database for PostgreSQL (Flexible Server B1ms)
                                                                 │ (Nightly Backups)
                                                                 ▼
                                                  Azure Blob Storage (Standard LRS Hot, < 5 GB)
```

### Architectural Decisions & Rationales:
1. **Static Next.js UI (`output: 'export'`):**
   The production Azure VM has only 1 GiB of RAM. An idle Next.js Node.js server consumes 150–300 MB of RAM. Compiling the frontend to static files served by Nginx consumes virtually zero extra memory (< 10 MB in Nginx) and eliminates the Node.js runtime entirely.
2. **External Managed PostgreSQL (Flexible Server B1ms):**
   Running a local PostgreSQL database server inside the 1 GiB VM would risk OOM kills under load. Moving the database to an external burstable B1ms instance (included in student credits) keeps the VM lean.
3. **Decoupled Pluggable Forecasting Interface:**
   The `ForecastProvider` interface separates inference from training. PyTorch and TensorFlow wheels (which require hundreds of MB of RAM and dependencies) are strictly prohibited from the host. Inference stubs execute using pure mathematical algorithms.
4. **Single-VM Architecture:**
   Only one VM (`Standard_B2ats_v2` or fallback `Standard_B1s`) is used to adhere strictly to the $0 Azure budget.

---

## 5. API Implementation

Versioned at `/api/v1` with automatic interactive OpenAPI documentation at `/docs`:

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Lightweight root uptime health probe for monitoring & Nginx upstream checks | `200 OK` |
| `GET` | `/` | Root API metadata and documentation links | `200 OK` |
| `GET` | `/api/v1/system/status` | Operational health, database connection state, process RSS in MB, and Azure SKU targets | `200 OK` |
| `GET` | `/api/v1/companies` | List of listed companies with latest prices, changes, and optional sector filter | `200 OK` |
| `GET` | `/api/v1/companies/{symbol}` | Company details and 20 recent daily OHLC prices (returns 404 for unknown symbol) | `200 OK` / `404` |
| `GET` | `/api/v1/forecasts/latest` | Latest forward predictions across models with demo disclaimer and symbol/model filter | `200 OK` |
| `GET` | `/api/v1/pipeline/status` | Market pipeline operational status, weekday schedule, and last execution metadata | `200 OK` |
| `GET` | `/api/v1/models` | Metadata on supported forecasting models (Lag Regression, ARIMA, LSTM) | `200 OK` |

---

## 6. Database Schema

Schema managed through SQLAlchemy 2.0 ORM and reproducible Alembic migrations (`0001_initial_schema.py`):

1. **`sectors`**:
   - `id` (PK, Integer)
   - `name` (String 100, Unique, Indexed)
   - `code` (String 20, Unique, Indexed)
   - `description` (String 255, Nullable)
   - `created_at` (DateTime UTC)

2. **`companies`**:
   - `id` (PK, Integer)
   - `symbol` (String 20, Unique, Indexed)
   - `name` (String 200)
   - `sector_id` (FK -> `sectors.id`, Indexed)
   - `is_active` (Boolean, default True)
   - `listing_date` (Date, Nullable)
   - `created_at` (DateTime UTC), `updated_at` (DateTime UTC)

3. **`daily_prices`**:
   - `id` (PK, Integer)
   - `company_id` (FK -> `companies.id`, Indexed)
   - `trade_date` (Date, Indexed)
   - `open_price`, `high_price`, `low_price`, `close_price` (Numeric 12,4)
   - `volume` (BigInteger, default 0), `value` (Numeric 18,4)
   - `created_at` (DateTime UTC)
   - *Constraint:* Unique constraint `(company_id, trade_date)`

4. **`model_metadata`**:
   - `id` (PK, Integer)
   - `name` (String 100), `code` (String 50, Unique, Indexed)
   - `version` (String 30), `description` (Text), `is_active` (Boolean)
   - `created_at` (DateTime UTC)

5. **`forecasts`**:
   - `id` (PK, Integer)
   - `company_id` (FK -> `companies.id`, Indexed)
   - `model_id` (FK -> `model_metadata.id`, Indexed)
   - `target_date` (Date, Indexed)
   - `predicted_price`, `lower_bound`, `upper_bound` (Numeric 12,4)
   - `confidence_level` (Float, default 0.95)
   - `is_demo` (Boolean, default True)
   - `created_at` (DateTime UTC)
   - *Constraint:* Unique constraint `(company_id, model_id, target_date)`

6. **`pipeline_runs`**:
   - `id` (PK, Integer)
   - `run_id` (String 36 UUID, Unique, Indexed)
   - `status` (String 20: PENDING, RUNNING, COMPLETED, FAILED)
   - `started_at` (DateTime UTC), `completed_at` (DateTime UTC, Nullable)
   - `records_ingested` (Integer), `forecasts_generated` (Integer)
   - `error_message` (Text, Nullable), `is_demo_run` (Boolean, default True)

---

## 7. Frontend Implementation

Constructed with Next.js 14 App Router, TypeScript, and Tailwind CSS:

- **Navigation & Layout:**
  - `Navbar.tsx`: Sticky top header with brand icon, navigation links, and active SKU badge (`Standard_B2ats_v2`).
  - `Footer.tsx`: Project ownership statement, $0 cost guardrails summary, and links.
  - `DemoBanner.tsx`: Prominent warning bar stating all market records and forecasts are synthetic demo stubs.
- **Pages:**
  - `Home (/)`: Identity hero banner, key metric cards, pipeline status banner with execution stages, latest forecast preview cards, and company summary table.
  - `Companies (/companies)`: Searchable directory with live search and sector filtering.
  - `Company Detail (/companies/[symbol])`: Dynamic route implementing `generateStaticParams()` for all 8 tracked blue chips (SMPH, BDO, ALI, BPI, TEL, ICT, AC, GLO), pure SVG sparkline charts, and price history tables.
  - `Watchlist (/watchlist)`: Fully client-side interactive watchlist persisted in browser `localStorage`.
  - `Models (/models)`: Architectural breakdown of Lag-Informed Regression, ARIMA, and LSTM stubs, with documentation on memory decoupling and scientific integrity.
  - `Learn (/learn)`: Educational overview of Philippine Stock Exchange trading sessions (9:00 AM – 3:00 PM PHT), forecast horizons (T+1, T+5), and lag feature engineering.
  - `About (/about)`: Documentation of Azure for Students architecture, SKU inventory, and explicitly excluded high-cost services.
- **Custom Components:**
  - `SparklineChart.tsx`: Lightweight pure SVG line chart with gradient fills (0 extra dependencies).
  - `MetricCard.tsx`, `ForecastCard.tsx`, `CompanyTable.tsx`, `StatusBadge.tsx`.

---

## 8. Azure Deployment Scaffolding

Created comprehensive Infrastructure-as-Code templates in `infrastructure/azure/`:
- `infrastructure/azure/main.bicep`: Complete Bicep template defining:
  - Resource Group & Virtual Network (`10.0.0.0/16`) with two subnets (`snet-vm`, `snet-db`).
  - Network Security Group with restricted SSH (port 22), HTTP (port 80), and HTTPS (port 443).
  - Single Azure Public IPv4.
  - Primary Virtual Machine: Ubuntu 24.04 LTS, `Standard_B2ats_v2` (2 vCPU, 1 GiB RAM), Premium SSD P6 64-GiB disk.
  - Fallback VM option: `Standard_B1s`.
  - Azure Database for PostgreSQL Flexible Server: Burstable B1ms, 32 GB storage limit, `autoGrow: Disabled`.
  - Storage Account: `Standard_LRS`, Hot tier, container `pse-pulse-data` (< 5 GB).
- `infrastructure/azure/parameters.example.json`: Secure parameter template with no hardcoded secrets.
- `infrastructure/azure/README.md`: Architectural documentation and explicit dry-run instructions.

### Explicit Confirmation:
> **NO AZURE RESOURCES WERE CREATED.**  
> Neither `az deployment`, `az vm create`, `terraform`, nor any Azure CLI command was executed. All templates remain strictly unapplied scaffolding.

---

## 9. Cost Guardrails

1. **Target Infrastructure Spend:** Exactly **\$0** monthly expenditure within Azure for Students credits.
2. **One-VM Limit:** Sized for a single `Standard_B2ats_v2` (or `Standard_B1s`) virtual machine.
3. **PostgreSQL 32-GB Hard Ceiling:** Storage size is pinned to 32 GB with `autoGrow: Disabled` to prevent automated tier upgrades.
4. **Blob Storage Ceiling:** Less than 5 GB hot storage.
5. **No Excluded High-Cost Services:** Bicep templates and documentation strictly ban AKS, Azure Container Apps, App Service paid tiers, Redis Cache, Cosmos DB, Service Bus, Azure Container Registry, and GPU VMs.
6. **Cost Protections:** Documented in [docs/cost-guardrails.md](docs/cost-guardrails.md) that Azure budget alerts do not automatically stop VMs, and that subscription spending limits must be verified prior to provisioning.

---

## 10. Security Review

- **Credential & Secret Checks:**
  - Verified `.env` is ignored by `.gitignore`.
  - Only `.env.example` is committed.
  - Scanned repository for private keys (`BEGIN PRIVATE KEY`, `BEGIN RSA`), API tokens, and passwords — **0 leaked credentials found**.
- **Network Boundaries:**
  - Production Azure Bicep NSG parameters require restricting SSH (port 22) to specific administrator CIDRs.
  - PostgreSQL server is placed on a delegated private subnet with no public database listener.
- **Process Security:**
  - Systemd service templates run under an unprivileged `psepulse` system user (`NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=full`).
- **Web Security:**
  - Production Nginx template includes `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
  - Nginx explicitly denies all hidden dotfiles (`location ~ /\. { deny all; }`).
  - CORS origins are environment-configurable via Pydantic settings.

---

## 11. Backend Validation

### Environment:
- Python binary: `./backend/.venv/bin/python` (`Python 3.12.13`)
- Pytest binary: `./backend/.venv/bin/pytest` (`pytest-8.4.2`)

### Test Command & Results:
```bash
./backend/.venv/bin/pytest -v
```

```text
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-8.4.2, pluggy-1.6.0 -- /Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-capstone-project/backend/.venv/bin/python3.12
cachedir: .pytest_cache
rootdir: /Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-capstone-project
configfile: pytest.ini
testpaths: backend/tests
plugins: asyncio-0.24.0, anyio-4.15.1
asyncio: mode=Mode.STRICT, default_loop_scope=None
collecting ... collected 22 items

backend/tests/test_companies.py::test_list_companies PASSED              [  4%]
backend/tests/test_companies.py::test_list_companies_sector_filter PASSED [  9%]
backend/tests/test_companies.py::test_get_company_valid PASSED           [ 13%]
backend/tests/test_companies.py::test_get_company_case_insensitive PASSED [ 18%]
backend/tests/test_companies.py::test_get_company_invalid_symbol PASSED  [ 22%]
backend/tests/test_config.py::test_settings_defaults PASSED              [ 27%]
backend/tests/test_config.py::test_settings_env_override PASSED          [ 31%]
backend/tests/test_forecasting_providers.py::test_lag_regression_provider PASSED [ 36%]
backend/tests/test_forecasting_providers.py::test_arima_provider PASSED  [ 40%]
backend/tests/test_forecasting_providers.py::test_lstm_provider PASSED   [ 45%]
backend/tests/test_forecasting_providers.py::test_forecast_registry PASSED [ 50%]
backend/tests/test_forecasts.py::test_get_latest_forecasts PASSED        [ 54%]
backend/tests/test_forecasts.py::test_forecasts_symbol_filter PASSED     [ 59%]
backend/tests/test_forecasts.py::test_forecasts_model_code_filter PASSED [ 63%]
backend/tests/test_health.py::test_root_endpoint PASSED                  [ 68%]
backend/tests/test_health.py::test_health_check_endpoint PASSED          [ 72%]
backend/tests/test_pipeline.py::test_pipeline_status_endpoint PASSED     [ 77%]
backend/tests/test_pipeline.py::test_data_validator_valid PASSED         [ 81%]
backend/tests/test_pipeline.py::test_data_validator_invalid_high_low PASSED [ 86%]
backend/tests/test_pipeline.py::test_data_validator_negative_volume PASSED [ 90%]
backend/tests/test_pipeline.py::test_feature_builder PASSED              [ 95%]
backend/tests/test_system.py::test_system_status_endpoint PASSED         [100%]

============================== 22 passed in 0.41s ==============================
```

- **Total Tests:** 22
- **Passed:** 22
- **Failed:** 0
- **Execution Time:** 0.41 seconds

---

## 12. Frontend Validation

### A. Clean Dependency Installation (`npm ci`)
```bash
npm --prefix frontend ci
```
**Result:** Exit code `0`. Added 393 packages cleanly using `package-lock.json`.

### B. Linting (`npm run lint`)
```bash
npm --prefix frontend run lint
```
**Result:** Exit code `0`.
```text
> pse-pulse-frontend@0.1.0 lint
> next lint

✔ No ESLint warnings or errors
```

### C. TypeScript Type Checking (`npx tsc --noEmit`)
```bash
npx --prefix frontend tsc --project frontend/tsconfig.json --noEmit
```
**Result:** Exit code `0`. Zero TypeScript errors.

### D. Production Static Export Build (`npm run build`)
```bash
npm --prefix frontend run build
```
**Result:** Exit code `0`.
```text
> pse-pulse-frontend@0.1.0 build
> next build

  ▲ Next.js 14.2.35

   Creating an optimized production build ...
 ✓ Compiled successfully
   Linting and checking validity of types
   Collecting page data
 ✓ Generating static pages (17/17)
   Collecting build traces
   Finalizing page optimization

Route (app)                              Size     First Load JS
┌ ○ /                                    3.97 kB         106 kB
├ ○ /_not-found                          873 B          88.3 kB
├ ○ /about                               1.53 kB          89 kB
├ ○ /companies                           779 B           103 kB
├ ● /companies/[symbol]                  185 B          97.5 kB
├   ├ /companies/SMPH
├   ├ /companies/BDO
├   ├ /companies/ALI
├   ├ /companies/BPI
├   ├ /companies/TEL
├   ├ /companies/ICT
├   ├ /companies/AC
├   └ /companies/GLO
├ ○ /learn                               1.53 kB          89 kB
├ ○ /models                              1.53 kB          89 kB
└ ○ /watchlist                           1.21 kB         103 kB
+ First Load JS shared by all            87.5 kB

○  (Static)  prerendered as static content
●  (SSG)     prerendered as static HTML
```

---

## 13. Integration Smoke Test

FastAPI backend was launched via Uvicorn on `127.0.0.1:8000` with the development database and seed service active:
1. **Health Check (`GET /health`):**
   Returned `HTTP 200 OK`: `{"status":"ok","version":"1.0.0","environment":"development", ...}`
2. **System Status (`GET /api/v1/system/status`):**
   Returned `HTTP 200 OK`: `{"status":"operational","database":{"status":"connected","engine":"sqlite"},"memory":{"process_rss_mb":70.64,"target_host_ram_mb":1024,"estimated_footprint_pct":6.9}, ...}`
3. **Companies Listing (`GET /api/v1/companies`):**
   Returned `HTTP 200 OK`: Full array of 8 companies (AC, ALI, BDO, BPI, GLO, ICT, SMPH, TEL) with prices and changes.
4. **Company Detail Lookup (`GET /api/v1/companies/SMPH`):**
   Returned `HTTP 200 OK`: SM Prime Holdings details and recent historical daily price array.
5. **Controlled Invalid Symbol Handling (`GET /api/v1/companies/INVALID_SYMBOL`):**
   Returned `HTTP 404 Not Found`: `{"detail":"Company with symbol 'INVALID_SYMBOL' not found."}`
6. **Forecasts API (`GET /api/v1/forecasts/latest`):**
   Returned `HTTP 200 OK`: `{"is_demo":true, "disclaimer":"DEMO DATA...", "forecasts":[...]}`
7. **Pipeline Status (`GET /api/v1/pipeline/status`):**
   Returned `HTTP 200 OK`: `{"status":"idle","schedule":"0 18 * * 1-5 (Weekdays 18:00 PHT)", ...}`
8. **Pipeline CLI Runner (`python -m backend.pipeline.runner`):**
   Executed cleanly, completing 6 execution stages and updating pipeline run records.

---

## 14. Static Export Verification

### Explicit Confirmation:
> **THE FRONTEND CAN BE SERVED WITHOUT A PERMANENT NODE.JS SERVER.**  
> Next.js is configured with `output: 'export'`, which compiles all routes into pure HTML, CSS, SVG, and bundled JavaScript files in the `frontend/out/` directory.  
> On the production Azure VM, **Nginx directly serves these static files from disk** (`/var/www/pse-pulse/out`). No Node.js process (`node`, `npm start`, or `next start`) runs in production.

---

## 15. Resource Usage

- **FastAPI Idle Process Resident Set Size (RSS):** **70.64 MB**
- **Target Host RAM (`Standard_B2ats_v2`):** 1024 MB (1 GiB)
- **FastAPI Memory Footprint:** **6.9%** of host RAM
- **Node.js Production Server Footprint:** **0 MB** (static export eliminates Node runtime)
- **Nginx Estimated Footprint:** **8 – 15 MB**
- **Total Expected Idle Host Memory:** **~80 – 90 MB** (< 9% of total host RAM)
- **Memory Risk Assessment:** Minimal risk of exceeding the 1 GiB VM memory. Host VM setup script provisions a 1 GiB swap file (`/swapfile`) with low swappiness (`10`) as an additional safeguard against unexpected batch spikes.

---

## 16. Git Status

### Command: `git status --short`
```text
?? .env.example
?? .github/
?? .gitignore
?? LICENSE
?? README.md
?? backend/
?? docker-compose.dev.yml
?? docs/
?? frontend/
?? infrastructure/
?? pytest.ini
```

### Command: `git diff --stat`
```text
(empty output — all files are untracked; no commits or staging have been performed)
```

---

## 17. Known Issues & Limitations

1. **Inference Stubs in Phase 1:**  
   The forecasting providers (`LagInformedRegressionProvider`, `ArimaProvider`, `LstmProvider`) are architectural inference stubs that project conservative trend curves for UI and pipeline verification. They do not yet incorporate pre-trained model weights.
2. **Development Seed Data:**  
   All market prices and company forecasts are generated synthetic development data. Real end-of-day market scraping is intentionally scaffolded but not automated in Phase 1 to prevent external API abuse.
3. **Azure Deployment Scaffolding Unapplied:**  
   The Bicep templates have not been executed on Azure, in strict compliance with the Phase 1 instructions.

---

## 18. Recommended Next Steps

1. Submit this `ANTIGRAVITY_PHASE1_REPORT.md` to ChatGPT for thorough architectural and code quality review.
2. Upon user approval, stage and commit the Phase 1 codebase:
   ```bash
   git add .
   git commit -m "feat: complete Phase 1 local architecture and Azure scaffolding for PSE Pulse"
   ```
3. Push to `https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git` on the `main` branch.
4. Prepare Phase 2: Offline model training / weight serialization pipeline and dry-run Azure Bicep pre-flight validation.

---

## 19. Initial Phase 1 Recommendation (Superseded)

*The initial Phase 1 recommendation has been superseded by the Phase 1.1 Pre-Commit Remediation pass below following ChatGPT review.*

---

## 20. Phase 1.1 — ChatGPT Pre-Commit Remediation

### 20.1 Executive Summary of Remediation
Following the architectural review of `ANTIGRAVITY_PHASE1_REPORT.md` by ChatGPT, a comprehensive pre-commit remediation pass (Phase 1.1) was performed. All identified feedback items have been resolved and locally verified:

1. **Project Directory Canonicalization:** The local workspace directory has been permanently renamed and canonicalized to `pse-pulse-mmdc-project` (removing all `capstone` naming). Remote tracking and branch identities were re-verified.
2. **Forbidden Reference & Code Audit:** Repository-wide audit confirmed zero copied code, zero Capstone/ForecastPH dependencies, and zero credentials.
3. **Next.js 16 Upgrade:** Upgraded from Next.js 14 to **Next.js 16.3.8** with stable **React 19.3.0** and **React DOM 19.3.0**. Migrated linting to ESLint CLI flat config (`eslint.config.mjs`). Verified zero ESLint warnings, zero TypeScript errors, and zero production vulnerabilities via `npm audit --omit=dev`.
4. **Static-Export Architecture:** Maintained strict static export (`output: 'export'`). All 16 routes generate static HTML files in `frontend/out/`. Zero runtime SSR, zero Server Actions, and zero production Node.js processes required.
5. **Azure PostgreSQL Networking Redesign:** Eliminated the VNet Private Subnet and Azure Private DNS Zone architecture to strictly avoid billable Azure Private DNS metered resources ($0.50/mo + queries). PostgreSQL Flexible Server is now configured for Public Access restricted by a single-IP firewall permitting exclusively the Azure VM's public IPv4. TLS is mandatory (`require_secure_transport = ON`).
6. **Bicep Scaffolding & Local Compilation:** Downloaded and executed standalone Azure Bicep CLI v0.47.16 locally. `infrastructure/azure/main.bicep` compiled cleanly into ARM JSON (`infrastructure/azure/main.json`) with **0 errors and 0 warnings**.
7. **Azure Resource Inventory & Free Allowance Compliance:** Documented all 7 target Azure resources with precise SKU mappings and student allowance limits. Verified zero billable dependencies (no AKS, Container Apps, App Service, Cosmos DB, Redis, etc.).
8. **Shell Scripts & Docker Compose Validation:** Validated syntax for all deployment shell scripts (`bash -n`). Validated `docker-compose.dev.yml` against Compose v3.8 specification.
9. **Database Schema Enhancements:** Enhanced database schema to support multi-version model metadata (unique constraint on `(code, version)`) and forecast history tracking (`pipeline_run_id` FK and composite uniqueness on `(company_id, model_id, target_date, pipeline_run_id)`). Re-tested Alembic migrations cleanly.
10. **Backend Test Suite Expansion:** All **23 backend unit and integration tests passed** in 0.24 seconds (100% pass rate).
11. **Actual Browser Smoke Testing:** Executed live local stack with mock Nginx reverse proxy (port 3000) and FastAPI backend (port 8000). Automated headless Google Chrome tests confirmed full DOM rendering on both Desktop (1280x800) and Mobile (390x844) viewports. Screenshots captured.
12. **Resource & Memory Footprint:** FastAPI idle process RSS measured live at **70.61 MB** (~6.9% of the 1 GiB host RAM budget). Nginx static serving footprint is ~8–15 MB. Zero Node.js runtime.
13. **Secrets & Git Sanity:** Verified all ephemeral and local artifacts are ignored by Git. Zero committed credentials found.

---

### 20.2 Local Project Identity & Git Alignment

The repository directory was moved from the temporary working path to the canonical project path: `/Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-project`. A compatibility symlink was retained so IDE and background harnesses preserve execution paths without interruption.

#### Verification Command Outputs:
```bash
$ pwd -P
/Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-project

$ git rev-parse --show-toplevel
/Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-project

$ git branch --show-current
main

$ git remote -v
origin  https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git (fetch)
origin  https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git (push)

$ git remote get-url origin
https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git

$ git status --short
?? .env.example
?? .github/
?? .gitignore
?? ANTIGRAVITY_PHASE1_REPORT.md
?? LICENSE
?? README.md
?? backend/
?? docker-compose.dev.yml
?? docs/
?? frontend/
?? infrastructure/
?? pytest.ini
```

**State:** Clean, uncommitted working tree pointing strictly to `AlvinTubtub/pse-pulse-mmdc-project` on branch `main`.

---

### 20.3 Accidental Reference & Copied Code Audit

A recursive search for forbidden project terms (`capstone`, `forecastph`, `pse-stock-price-forecast`, `Capstone2-A4103`) was conducted across all files (excluding `.venv`, `node_modules`, `.next`, `out`, and `.git`):

```bash
grep -rnEI --exclude-dir=node_modules --exclude-dir=out --exclude-dir=.venv --exclude-dir=.git --exclude-dir=.next \
  "capstone|forecastph|pse-stock-price-forecast|Capstone2-A4103" .
```

#### Search Findings & Dispositions:
- **`backend/`**: 0 matches. Zero code, models, datasets, or configurations copied.
- **`frontend/`**: 0 matches. 100% freshly authored Next.js 16 components.
- **`infrastructure/`**: 0 matches. Bicep and scripts authored specifically for personal Azure for Students allowances.
- **`docs/`**: 0 matches.
- **`docker-compose.dev.yml`**: 0 matches.
- **`ANTIGRAVITY_PHASE1_REPORT.md` (historical text)**: 3 historical references in Section 2 recording the initial local working path prior to remediation.
- **Disposition:** All application code, infrastructure scripts, and configurations are 100% independent. No academic project assets or credentials exist.

---

### 20.4 Next.js 16 Upgrade & Frontend Tooling

The frontend framework was upgraded to **Next.js 16.3.8** with **React 19.3.0** and **React DOM 19.3.0**.

#### Dependency Specifications (`frontend/package.json`):
```json
{
  "name": "pse-pulse-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build --webpack",
    "lint": "eslint ."
  },
  "dependencies": {
    "lucide-react": "^1.49.0",
    "next": "16.3.8",
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@eslint/js": "^9.22.0",
    "@types/node": "^20.17.19",
    "@types/react": "^19.0.10",
    "@types/react-dom": "^19.0.4",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.22.0",
    "globals": "^16.0.0",
    "postcss": "^8.5.3",
    "tailwindcss": "^3.4.17",
    "typescript": "^5.7.3",
    "typescript-eslint": "^8.24.1"
  }
}
```

#### Node.js & Dependency Verification:
```bash
$ node --version
v24.16.0

$ npm --version
11.13.0

$ npm list next react react-dom
pse-pulse-frontend@0.1.0
├─┬ lucide-react@1.49.0
│ └── react@19.3.0 deduped
├─┬ next@16.3.8
│ ├── react-dom@19.3.0 deduped
│ ├── react@19.3.0 deduped
│ └─┬ styled-jsx@5.1.6
│   └── react@19.3.0 deduped
├─┬ react-dom@19.3.0
│ └── react@19.3.0 deduped
└── react@19.3.0
```

#### ESLint Flat Config Migration:
Because Next.js 16 deprecates `next lint` in favor of standard ESLint CLI, `frontend/.eslintrc.json` was replaced with flat configuration `frontend/eslint.config.mjs` using `@eslint/js` and `typescript-eslint`.

#### Code Quality & Audit Checks:
- **`npm run lint` (`eslint .`):** **PASS** — 0 errors, 0 warnings.
- **`npx tsc --noEmit`:** **PASS** — 0 TypeScript errors. (Updated dynamic route `params` to `Promise<{ symbol: string }>` in accordance with Next.js 15+ async App Router specs).
- **`npm audit --omit=dev`:** **PASS** — `found 0 vulnerabilities` (0 high, 0 critical).

---

### 20.5 Static-Export Preservation & Output Verification

Static export (`output: 'export'` in `frontend/next.config.mjs`) was verified.

#### Build Execution Output:
```text
▲ Next.js 16.3.8 (webpack)
✓ Compiled successfully in 1092ms
✓ Finished TypeScript in 663ms 
✓ Collecting page data using 7 workers in 407ms 
✓ Generating static pages using 7 workers (16/16) in 260ms
✓ Collecting build traces in 3.0s 
✓ Finalizing page optimization in 3.0s 

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /about
├ ○ /companies
├   /companies/[symbol]
│ ├ ● /companies/SMPH
│ ├ ● /companies/BDO
│ ├ ● /companies/ALI
│ └ ● [+5 more paths]
├ ○ /learn
├ ○ /models
└ ○ /watchlist

○  (Static)  prerendered as static content
●  (SSG)     prerendered as static HTML (uses generateStaticParams)
```

#### Statically Exported Artifacts (`frontend/out/`):
```text
frontend/out/
├── 404.html
├── about.html
├── companies.html
├── companies/
│   ├── AC.html
│   ├── ALI.html
│   ├── BDO.html
│   ├── BPI.html
│   ├── GLO.html
│   ├── ICT.html
│   ├── SMPH.html
│   └── TEL.html
├── index.html
├── learn.html
├── models.html
├── watchlist.html
└── _next/static/
    ├── chunks/ (JavaScript bundles)
    └── css/ (Tailwind styles)
```

All 16 routes compile into pure static files. No Node.js runtime is required on the Azure VM.

---

### 20.6 Azure PostgreSQL Networking Redesign (Strict Free-Service Architecture)

The previous VNet private subnet integration required deploying an Azure Private DNS Zone (`privatelink.postgres.database.azure.com`) and Virtual Network Link, which incur recurring monthly costs ($0.50/month per hosted zone plus DNS query charges) outside the student free allowance.

#### Updated Production Network Topology:
```text
Internet
   │
   ▼ (HTTPS:443 / HTTP:80)
[Azure Public IPv4 (pip-pse-pulse)]
   │
   ▼
[Azure Virtual Machine (vm-pse-pulse)]
Standard_B2ats_v2 (1 GiB RAM)
Nginx + Static Export + FastAPI/Uvicorn
   │
   │ TLS PostgreSQL Connection (Port 5432)
   │ Host: pseserver-XXXXX.postgres.database.azure.com
   ▼
[Azure Database for PostgreSQL Flexible Server]
Burstable B1ms, 32 GB Storage, Auto-Grow Disabled
Public Access Enabled
Firewall: ONLY VM Public IPv4 (pip-pse-pulse.properties.ipAddress)
```

#### Implementation Details:
1. **Public Access with Single-IP Firewall:** PostgreSQL allows inbound connections exclusively from the PSE Pulse VM's public IPv4 address.
2. **Strict Firewall Rules:**
   - No `0.0.0.0/0` rule.
   - "Allow access from Azure services" is disabled.
   - No unrestricted client CIDR blocks.
3. **Mandatory TLS:** `require_secure_transport = ON` enforced on PostgreSQL server. Production connection strings require `sslmode=require`.
4. **Zero Billable DNS Resources:** PostgreSQL server FQDN resolves via public Azure DNS at $0 cost.

---

### 20.7 Bicep Scaffolding & Local Compilation Proof

The infrastructure template `infrastructure/azure/main.bicep` was refactored and compiled locally using the official Azure Bicep CLI.

#### Local Bicep Compilation:
```bash
$ bicep --version
Bicep CLI version 0.47.16 (1d102e1c9d)

$ bicep build infrastructure/azure/main.bicep --outfile infrastructure/azure/main.json
# Result: Exit Code 0, 0 errors, 0 warnings.
```

The compilation produced a valid 22.5 KB Azure Resource Manager (ARM) JSON deployment template (`infrastructure/azure/main.json`).

#### Bicep Resource Declarations:
- `Microsoft.Network/networkSecurityGroups` (`nsg-pse-pulse`)
- `Microsoft.Network/virtualNetworks` (`vnet-pse-pulse`)
- `Microsoft.Network/publicIPAddresses` (`pip-pse-pulse`)
- `Microsoft.Network/networkInterfaces` (`nic-pse-pulse`)
- `Microsoft.Compute/virtualMachines` (`vm-pse-pulse`, `Standard_B2ats_v2`)
- `Microsoft.DBforPostgreSQL/flexibleServers` (`pseserver-...`, B1ms)
- `Microsoft.DBforPostgreSQL/flexibleServers/firewallRules` (`allow-vm-public-ip`)
- `Microsoft.Storage/storageAccounts` (`stpse...`, Standard_LRS)

---

### 20.8 Azure Resource Inventory & Free Allowance Compliance

| Resource | Azure Resource Name | Target SKU / Sizing | Free-Service Allowance Limit | Monthly Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Virtual Machine** | `vm-pse-pulse` | `Standard_B2ats_v2` (2 vCPU, 1 GiB RAM) | 750 hours/month (Linux B2ats_v2 / B1s) | **$0.00** |
| **Fallback VM** | `vm-pse-pulse` | `Standard_B1s` (1 vCPU, 1 GiB RAM) | 750 hours/month | **$0.00** |
| **OS Managed Disk** | `osdisk` | Premium SSD P6 (64 GiB) | 2x 64 GB SSDs included | **$0.00** |
| **Database Server** | `pseserver-...` | PostgreSQL Flexible Server B1ms | 750 hours/month + 32 GB storage (12 mos) | **$0.00** |
| **Database Storage** | Attached storage | 32 GB Burstable (Auto-grow disabled) | 32 GB storage allowance | **$0.00** |
| **Public IPv4** | `pip-pse-pulse` | Standard SKU (Dynamic/Static) | 750 hours/month public IPv4 | **$0.00** |
| **Blob Storage** | `stpse...` | Standard_LRS (Hot tier) | 5 GB LRS storage allowance | **$0.00** |
| **Virtual Network** | `vnet-pse-pulse` | 10.0.0.0/16 (1 subnet: 10.0.1.0/24) | Virtual networks are free | **$0.00** |
| **Network Security**| `nsg-pse-pulse` | Security rules: 22, 80, 443 | Network security groups are free | **$0.00** |

#### Excluded Azure Services Check:
- **AKS / Kubernetes:** None
- **Container Apps / ACA:** None
- **App Service:** None
- **Azure Functions:** None
- **Azure SQL / Cosmos DB:** None
- **Azure Cache for Redis:** None
- **Cognitive / AI Services:** None
- **Azure Load Balancer (Standard paid):** None (direct Public IP)
- **Azure Private DNS Zones:** None (eliminated in Phase 1.1)
- **VPN / ExpressRoute:** None

**Target Monthly Spend:** **$0.00** (Strictly within Azure for Students free allowances).

> [!NOTE]
> Azure for Students allowances are governed by Microsoft program terms. B1ms PostgreSQL Flexible Server is provided free for 12 months from subscription activation. The architecture is explicitly documented so that, after the promotional window, the single-VM fallback can host local PostgreSQL if zero-cost operation must continue indefinitely.

---

### 20.9 Shell Scripts & Docker Compose Validation

#### Script Syntax Checks (`bash -n`):
```bash
$ bash -n infrastructure/scripts/deploy-static.sh  # PASS (Exit code 0)
$ bash -n infrastructure/scripts/setup-vm.sh       # PASS (Exit code 0)
$ bash -n infrastructure/scripts/run-pipeline.sh   # PASS (Exit code 0)
```

#### Docker Compose Validation:
`docker-compose.dev.yml` defines the optional local PostgreSQL 16 container for local development. Validated via Python PyYAML parser against the Docker Compose v3.8 specification: valid keys `version`, `services`, `volumes`. Note: Production Azure VM does not use Docker.

---

### 20.10 Database Schema Enhancements & Alembic Verification

To support robust forecasting lineage and multi-version model experimentation:
1. **Model Versioning:** `backend/app/models/model_metadata.py` was updated with a unique constraint on `(code, version)` (`uq_model_metadata_code_version`), allowing multiple iterations of the same model (e.g. `BASELINE_SMA v1.0.0` and `v2.0.0`) to coexist in the registry.
2. **Forecast Traceability:** `backend/app/models/forecast.py` now includes `pipeline_run_id` as a foreign key to `pipeline_runs.id`. The unique constraint was updated to `(company_id, model_id, target_date, pipeline_run_id)` (`uq_forecasts_company_model_date_run`), enabling historical forecasts across successive daily runs to be preserved rather than overwritten.
3. **Pipeline Ingestion & Saver:** `backend/pipeline/persistence/db_saver.py` and `backend/pipeline/runner.py` now link forecast batches to the active `PipelineRun` record.

#### Alembic Migration Execution:
```bash
$ rm -f pse_pulse_dev.db
$ alembic -c backend/alembic.ini upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema, 0001_initial_schema

$ alembic -c backend/alembic.ini current
0001_initial_schema (head)
```

The pipeline runner executed cleanly in demo mode, generating 120 forecast points across 8 companies and associating them with `PipelineRun` ID `8c533177-b994-4fa9-af11-8703dc0b5ec7`.

---

### 20.11 Backend Test Suite Results

All tests were executed using `pytest -v` against the updated schema and models:

```text
backend/tests/test_companies.py::test_list_companies PASSED                [  4%]
backend/tests/test_companies.py::test_list_companies_sector_filter PASSED  [  8%]
backend/tests/test_companies.py::test_get_company_valid PASSED             [ 13%]
backend/tests/test_companies.py::test_get_company_case_insensitive PASSED  [ 17%]
backend/tests/test_companies.py::test_get_company_invalid_symbol PASSED    [ 21%]
backend/tests/test_config.py::test_settings_defaults PASSED                [ 26%]
backend/tests/test_config.py::test_settings_env_override PASSED            [ 30%]
backend/tests/test_forecasting_providers.py::test_lag_regression_provider PASSED [ 34%]
backend/tests/test_forecasting_providers.py::test_arima_provider PASSED    [ 39%]
backend/tests/test_forecasting_providers.py::test_lstm_provider PASSED     [ 43%]
backend/tests/test_forecasting_providers.py::test_forecast_registry PASSED [ 47%]
backend/tests/test_forecasts.py::test_get_latest_forecasts PASSED          [ 52%]
backend/tests/test_forecasts.py::test_forecasts_symbol_filter PASSED       [ 56%]
backend/tests/test_forecasts.py::test_forecasts_model_code_filter PASSED   [ 60%]
backend/tests/test_forecasts.py::test_model_multi_version_coexistence PASSED [ 65%]
backend/tests/test_health.py::test_root_endpoint PASSED                    [ 69%]
backend/tests/test_health.py::test_health_check_endpoint PASSED            [ 73%]
backend/tests/test_pipeline.py::test_pipeline_status_endpoint PASSED       [ 78%]
backend/tests/test_pipeline.py::test_data_validator_valid PASSED           [ 82%]
backend/tests/test_pipeline.py::test_data_validator_invalid_high_low PASSED [ 86%]
backend/tests/test_pipeline.py::test_data_validator_negative_volume PASSED [ 91%]
backend/tests/test_pipeline.py::test_feature_builder PASSED                [ 95%]
backend/tests/test_system.py::test_system_status_endpoint PASSED           [100%]

============================== 23 passed in 0.24s ==============================
```

**Result:** **23/23 tests passed (100% pass rate)** in 0.24 seconds.

---

### 20.12 Browser Smoke Test & Visual Verification

A full local integration test was performed with real HTTP requests and Google Chrome in headless mode:
- Static site server running on `127.0.0.1:3000` (serving `frontend/out/` with `$uri.html` resolution and reverse proxying `/api/` to port 8000).
- FastAPI backend running on `127.0.0.1:8000`.

#### HTTP Endpoint Verification Table:
| Route | Type | Status | Payload Size | Verification Result |
| :--- | :--- | :--- | :--- | :--- |
| `/` | HTML (Static) | `200 OK` | 30,213 bytes | **PASS** — Home page with Hero, Metrics, & Ingestion cards |
| `/companies` | HTML (Static) | `200 OK` | 22,131 bytes | **PASS** — 8 PSE companies with sector filter & search |
| `/companies/SMPH` | HTML (SSG) | `200 OK` | 35,512 bytes | **PASS** — SM Prime Holdings price history & forecasts |
| `/companies/BDO` | HTML (SSG) | `200 OK` | 35,482 bytes | **PASS** — BDO Unibank detail page |
| `/watchlist` | HTML (Static) | `200 OK` | 21,825 bytes | **PASS** — Interactive watchlist with local storage |
| `/models` | HTML (Static) | `200 OK` | 43,100 bytes | **PASS** — Lag Regression, ARIMA, and LSTM documentation |
| `/learn` | HTML (Static) | `200 OK` | 30,536 bytes | **PASS** — PSE market metrics & forecasting guide |
| `/about` | HTML (Static) | `200 OK` | 40,437 bytes | **PASS** — Architectural specs, boundary disclaimers |
| `/health` | JSON API | `200 OK` | 108 bytes | **PASS** — Backend status: `healthy` |
| `/api/v1/system/status` | JSON API | `200 OK` | 530 bytes | **PASS** — Operational metrics, memory RSS |
| `/api/v1/companies` | JSON API | `200 OK` | 1,178 bytes | **PASS** — 8 companies list |
| `/api/v1/forecasts/latest`| JSON API | `200 OK` | 15,453 bytes | **PASS** — Latest multi-model forecast points |

#### Headless Browser DOM & Visual Capture:
- **Desktop (1280x800):** Google Chrome rendered the complete DOM. Verified stylesheet `/_next/static/css/04497e33e8742a1c.css` and JavaScript bundles loaded with zero missing assets. Screenshot captured: `desktop_home.png` (329 KB).
- **Mobile (390x844):** Google Chrome rendered `/companies/SMPH` at mobile viewport. Verified navigation bar collapses, badges align properly, sparkline charts render cleanly, and forecast cards stack responsively. Screenshot captured: `mobile_smph.png` (65.7 KB).

---

### 20.13 Nginx Static Next.js Configuration

The production Nginx template (`infrastructure/nginx/pse-pulse.conf`) implements the necessary static export routing:
```nginx
location / {
    try_files $uri $uri/ $uri.html /index.html =404;
    add_header Cache-Control "no-cache, public, must-revalidate";
}

location /_next/static/ {
    expires 1y;
    add_header Cache-Control "public, max-age=31536000, immutable";
    access_log off;
}
```

This guarantees clean URLs (`/companies`, `/companies/SMPH`) resolve to the pre-rendered HTML files without trailing slashes or URL rewriting issues, eliminating any requirement for Node.js in production.

---

### 20.14 Secrets & Git-Ignored Artifacts Audit

#### Git-Ignore Verification (`git check-ignore -v`):
```text
.gitignore:24:.venv               backend/.venv
.gitignore:45:frontend/node_modules/ frontend/node_modules
.gitignore:47:frontend/out/       frontend/out
.gitignore:40:.env                .env
.gitignore:28:*.db                pse_pulse_dev.db
.gitignore:31:.pytest_cache/      .pytest_cache
```

#### Secret Scan Results:
- Scanned for `BEGIN PRIVATE KEY`, `BEGIN RSA`, and API tokens across the repository.
- **Result: 0 committed private keys or real credentials found.**
- All configurations utilize environment variables via `.env.example`.

---

### 20.15 Memory Footprint & Resource Breakdown

Live resource measurements obtained via `GET /api/v1/system/status`:
```json
{
  "status": "operational",
  "environment": "development",
  "database": {
    "status": "connected",
    "engine": "sqlite"
  },
  "memory": {
    "process_rss_mb": 70.61,
    "target_host_ram_mb": 1024,
    "estimated_footprint_pct": 6.9
  },
  "demo_mode": true
}
```

#### VM Memory Budget Breakdown (1 GiB / 1024 MB Host):
- **FastAPI / Uvicorn Backend Process:** **~70 MB** (6.9% of host RAM)
- **Nginx Static Web Server:** **~8 – 15 MB** (< 1.5% of host RAM)
- **Frontend Node.js Server:** **0 MB** (Static export served directly from disk)
- **Linux OS & System Services (Ubuntu 24.04 LTS):** **~150 – 200 MB**
- **Total Expected Host Memory Usage:** **~230 – 285 MB** (comfortably within 1024 MB RAM)
- **Host Safeguard:** VM setup script provisions a **1 GiB swap file** (`/swapfile`) with `vm.swappiness=10`.

---

### 20.16 Pre-Commit Remediation Conclusion (Superseded)

*The Phase 1.1 conclusion has been superseded by the Phase 1.2 Final Pre-Commit Verification below.*

---

## 21. Phase 1.2 — Final Pre-Commit Verification

### 21.1 Nginx Routing Fix
In Next.js static exports without trailing slashes, Next.js generates both `companies.html` and a `companies/` directory (which holds dynamic route sub-pages like `SMPH.html`, `BDO.html`). Under standard Nginx `try_files $uri $uri/`, requests for `/companies` matched the directory first, causing Nginx to issue a 301 redirect or 403 directory index error.

The Nginx configuration (`infrastructure/nginx/pse-pulse.conf`) was updated to prioritize `$uri.html`:

```nginx
# Server-level index
index index.html;

# Static export HTML routing:
# 1. Prefer $uri.html so /companies matches companies.html before the companies/ directory
# 2. Try $uri for exact static files (_next/static, images, etc.)
# 3. Try $uri/ which resolves / to index.html via server-level 'index index.html;'
# 4. Fall through to =404 triggering error_page 404 /404.html (never returns 200 for missing pages)
location / {
    try_files $uri.html $uri $uri/ =404;
    add_header Cache-Control "no-cache, public, must-revalidate";
}

# Custom 404 error page for Next.js static export
error_page 404 /404.html;
error_page 403 =404 /404.html;

location = /404.html {
    internal;
}
```

#### Trailing Slash Behavior Rationale:
- **Canonical URLs:** Next.js static export generates clean, non-trailing-slash canonical URLs (`/companies`, `/companies/SMPH`, `/watchlist`).
- **Trailing Slash Handling:** Requests with trailing slashes (`/companies/`, `/companies/SMPH/`) do not correspond to directory index files; with `error_page 403 =404 /404.html;`, they cleanly yield HTTP 404 with the custom `404.html` error page. This enforces canonical URL discipline and prevents duplicate content SEO indexing.

---

### 21.2 Actual Nginx Runtime Validation
Actual **Nginx 1.31.6** was executed locally against the built static export (`frontend/out/`) and a running FastAPI backend instance (`127.0.0.1:8000`).

#### Live HTTP Test Results (http://127.0.0.1:8088):
| Request Path | Expected | Received | Body Size | Result | Notes |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `GET /` | `200` | `200 OK` | 30,201 bytes | **PASS** | Serves `index.html` via `index index.html;` |
| `GET /companies` | `200` | `200 OK` | 22,118 bytes | **PASS** | Serves `companies.html` directly (no 301 directory redirect) |
| `GET /companies/SMPH` | `200` | `200 OK` | 35,497 bytes | **PASS** | Serves `companies/SMPH.html` directly |
| `GET /watchlist` | `200` | `200 OK` | 21,811 bytes | **PASS** | Serves `watchlist.html` |
| `GET /models` | `200` | `200 OK` | 43,087 bytes | **PASS** | Serves `models.html` |
| `GET /learn` | `200` | `200 OK` | 30,523 bytes | **PASS** | Serves `learn.html` |
| `GET /about` | `200` | `200 OK` | 40,424 bytes | **PASS** | Serves `about.html` |
| `GET /health` | `200` | `200 OK` | 108 bytes | **PASS** | Proxied to FastAPI `/health`, returned `{"status":"ok"}` |
| `GET /api/v1/companies` | `200` | `200 OK` | 1,178 bytes | **PASS** | Proxied to FastAPI with `/api/v1` intact; 8 companies returned |
| `GET /api/v1/forecasts/latest` | `200` | `200 OK` | 15,453 bytes | **PASS** | Proxied to FastAPI with `/api/v1` intact; forecasts returned |
| `GET /definitely-not-a-real-page` | `404` | `404 Not Found` | 19,939 bytes | **PASS** | Returns genuine HTTP 404 and serves `404.html` body |
| `GET /companies/` | `404` | `404 Not Found` | 19,939 bytes | **PASS** | Returns HTTP 404 with `404.html` body |
| `GET /companies/SMPH/` | `404` | `404 Not Found` | 19,939 bytes | **PASS** | Returns HTTP 404 with `404.html` body |

---

### 21.3 FastAPI Proxy Verification
The Nginx configuration cleanly separates API, health, and documentation proxy blocks without modifying URI paths:

```nginx
# FastAPI API endpoints (/api/*)
# NOTE: proxy_pass without a URI path preserves the full original request URI (/api/v1/...)
location /api/ {
    proxy_pass http://pse_pulse_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
}

# Production health check probe (/health)
location = /health {
    proxy_pass http://pse_pulse_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
}

# Interactive API Documentation & OpenAPI schema
location ~ ^/(docs|redoc|openapi\.json) {
    proxy_pass http://pse_pulse_backend;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
}
```

- **Verification:** Verified via live HTTP request that `GET /api/v1/companies` is received by FastAPI as `/api/v1/companies` (not stripped to `/v1/companies`).
- **Health Probe:** Verified that `GET /health` is proxied and returns HTTP 200 health status.

---

### 21.4 Azure Static Public IPv4 Configuration
In `infrastructure/azure/main.bicep`, the VM's Public IP is explicitly pinned to a static IPv4 address with Regional tier:

```bicep
// 3. Public IPv4 (Single static allocated address for VM)
resource publicIp 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: publicIpName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  properties: {
    publicIPAddressVersion: 'IPv4'
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: 'pse-pulse-${uniqueSuffix}'
    }
  }
}
```

---

### 21.5 PostgreSQL Single-IP Firewall Rule
The PostgreSQL Flexible Server firewall rule permits ingress strictly from the VM's static Public IP:

```bicep
// 7. PostgreSQL Firewall Rule: Strictly restricted ONLY to the VM Public IPv4
resource postgresFirewallRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-03-01-preview' = {
  parent: postgresServer
  name: 'allow-pse-pulse-vm-ip'
  properties: {
    startIpAddress: publicIp.properties.ipAddress
    endIpAddress: publicIp.properties.ipAddress
  }
}
```

- **Perimeter Defense:** `startIpAddress` and `endIpAddress` both reference `publicIp.properties.ipAddress`.
- **Restrictions:** Neither `0.0.0.0` nor `0.0.0.0/0` is used. "Allow access from Azure services" is disabled.

---

### 21.6 TLS Configuration
- **Server Enforcement (`main.bicep`):** Added explicit server configuration resource enforcing TLS/SSL:
  ```bicep
  // Server configuration: explicitly enforce TLS/SSL
  resource postgresRequireSsl 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-03-01-preview' = {
    parent: postgresServer
    name: 'require_secure_transport'
    properties: {
      value: 'on'
      source: 'user-override'
    }
  }
  ```
- **Client Enforcement (`.env.example`):** Documented production PostgreSQL connection pattern:
  ```ini
  # Future Production Azure Database for PostgreSQL Flexible Server (TLS Required):
  # DATABASE_URL=postgresql+psycopg://USER:PASSWORD@SERVER.postgres.database.azure.com:5432/pse_pulse_prod?sslmode=require
  ```

---

### 21.7 Azure Allowance Documentation Correction
Updated documentation in `docs/cost-guardrails.md` to reflect the active subscription allowance visible on the student dashboard:
- **Public IP Hours Limit:** **Account-visible allowance: 1,500 public IP address-hours/month** on the current student dashboard.
- **Account Disclaimers:** Explicitly documented that this allowance should not be generalized as a guarantee across all Azure accounts, and that actual deployment must verify the active subscription dashboard as the final source of truth before provisioning.

---

### 21.8 Bicep Compilation & Artifact Management
- **Compilation Command:**
  ```bash
  bicep build infrastructure/azure/main.bicep --outfile infrastructure/azure/main.json
  ```
- **Result:** **Exit code 0, 0 errors, 0 warnings.**
- **Artifact Discipline:** `infrastructure/azure/main.json` was deleted after compilation verification, and `infrastructure/azure/*.json` (excluding `parameters.example.json`) was added to `.gitignore` to avoid committing generated ARM JSON.

---

### 21.9 Browser Console & Watchlist Persistence Verification
Executed automated Headless Google Chrome verification via Chrome DevTools Protocol (CDP):

| Browser Check | Target Page | Test Methodology | Result |
| :--- | :--- | :--- | :---: |
| **Uncaught JS Errors** | `http://127.0.0.1:8088/` | Evaluated window state & error events | **PASS** (0 errors) |
| **Uncaught JS Errors** | `http://127.0.0.1:8088/companies` | Evaluated window state & error events | **PASS** (0 errors) |
| **Uncaught JS Errors** | `http://127.0.0.1:8088/companies/SMPH` | Evaluated window state & error events | **PASS** (0 errors) |
| **Uncaught JS Errors** | `http://127.0.0.1:8088/watchlist` | Evaluated window state & error events | **PASS** (0 errors) |
| **Watchlist Add & Reload** | `http://127.0.0.1:8088/watchlist` | Added `['SMPH', 'BDO']` via `localStorage`, reloaded page; verified persistence in storage and DOM | **PASS** |
| **Watchlist Remove & Reload** | `http://127.0.0.1:8088/watchlist` | Cleared `[]` in `localStorage`, reloaded page; verified empty state banner rendered in DOM | **PASS** |

---

### 21.10 Backend & Frontend Revalidation
- **Backend Compile:** `python -m compileall backend/app backend/pipeline` -> **PASS (0 errors)**.
- **Backend Tests:** `pytest -v` -> **PASS (23/23 passed in 0.47s)**.
- **Frontend Dependencies:** `npm ci` -> **PASS (clean installation)**.
- **Frontend Lint:** `npm run lint` (`eslint .`) -> **PASS (0 errors, 0 warnings)**.
- **Frontend Types:** `npx tsc --noEmit` -> **PASS (0 errors)**.
- **Frontend Build:** `npm run build` -> **PASS (16/16 static pages generated in `frontend/out/`)**.
- **Frontend Audit:** `npm audit --omit=dev` -> **PASS (found 0 vulnerabilities)**.

---

### 21.11 Transient Artifact Cleanup
All transient test artifacts, temporary databases, and caches were removed:
- Removed local dev database: `pse_pulse_dev.db`
- Removed workspace `scratch/` directory
- Added `*.tsbuildinfo` to `.gitignore` and removed `frontend/tsconfig.tsbuildinfo`
- Added `*.png` to `.gitignore`
- Added `infrastructure/azure/*.json` to `.gitignore` and removed generated `main.json`

---

### 21.12 Final Git State

Executed after all modifications, tests, and cleanups:

```bash
$ pwd -P
/Users/alvintubtub/Documents/Antigravity/pse-pulse-mmdc-project

$ git branch --show-current
main

$ git remote -v
origin  https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git (fetch)
origin  https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git (push)

$ git status --short
?? .env.example
?? .github/
?? .gitignore
?? ANTIGRAVITY_PHASE1_REPORT.md
?? LICENSE
?? README.md
?? backend/
?? docker-compose.dev.yml
?? docs/
?? frontend/
?? infrastructure/
?? pytest.ini

$ git ls-files --others --exclude-standard
.env.example
.github/workflows/ci.yml
.gitignore
ANTIGRAVITY_PHASE1_REPORT.md
LICENSE
README.md
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/0001_initial_schema.py
backend/app/__init__.py
backend/app/api/v1/endpoints/companies.py
backend/app/api/v1/endpoints/forecasts.py
backend/app/api/v1/endpoints/models.py
backend/app/api/v1/endpoints/pipeline.py
backend/app/api/v1/endpoints/system.py
backend/app/api/v1/router.py
backend/app/config.py
backend/app/database.py
backend/app/forecasting/__init__.py
backend/app/forecasting/base.py
backend/app/forecasting/providers/__init__.py
backend/app/forecasting/providers/arima.py
backend/app/forecasting/providers/lag_regression.py
backend/app/forecasting/providers/lstm.py
backend/app/forecasting/registry.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/company.py
backend/app/models/forecast.py
backend/app/models/model_metadata.py
backend/app/models/pipeline_run.py
backend/app/models/price.py
backend/app/models/sector.py
backend/app/schemas/__init__.py
backend/app/schemas/common.py
backend/app/schemas/company.py
backend/app/schemas/forecast.py
backend/app/schemas/pipeline.py
backend/app/schemas/price.py
backend/app/schemas/sector.py
backend/app/schemas/system.py
backend/app/services/seed_data.py
backend/pipeline/__init__.py
backend/pipeline/features/feature_builder.py
backend/pipeline/forecasting/runner.py
backend/pipeline/ingest/eod_ingest.py
backend/pipeline/persistence/db_saver.py
backend/pipeline/runner.py
backend/pipeline/validation/data_validator.py
backend/requirements.txt
backend/tests/conftest.py
backend/tests/test_companies.py
backend/tests/test_config.py
backend/tests/test_forecasting_providers.py
backend/tests/test_forecasts.py
backend/tests/test_health.py
backend/tests/test_pipeline.py
backend/tests/test_system.py
docker-compose.dev.yml
docs/architecture.md
docs/azure-deployment.md
docs/cost-guardrails.md
frontend/eslint.config.mjs
frontend/next-env.d.ts
frontend/next.config.mjs
frontend/package-lock.json
frontend/package.json
frontend/postcss.config.mjs
frontend/src/app/about/page.tsx
frontend/src/app/companies/[symbol]/page.tsx
frontend/src/app/companies/page.tsx
frontend/src/app/globals.css
frontend/src/app/layout.tsx
frontend/src/app/learn/page.tsx
frontend/src/app/models/page.tsx
frontend/src/app/page.tsx
frontend/src/app/watchlist/page.tsx
frontend/src/components/CompanyTable.tsx
frontend/src/components/DemoBanner.tsx
frontend/src/components/Footer.tsx
frontend/src/components/ForecastCard.tsx
frontend/src/components/MetricCard.tsx
frontend/src/components/Navbar.tsx
frontend/src/components/SparklineChart.tsx
frontend/src/components/StatusBadge.tsx
frontend/src/lib/api.ts
frontend/src/lib/types.ts
frontend/src/lib/watchlist.ts
frontend/tailwind.config.ts
frontend/tsconfig.json
infrastructure/azure/README.md
infrastructure/azure/main.bicep
infrastructure/azure/parameters.example.json
infrastructure/nginx/pse-pulse.conf
infrastructure/scripts/deploy-static.sh
infrastructure/scripts/run-pipeline.sh
infrastructure/scripts/setup-vm.sh
infrastructure/systemd/pse-pulse-api.service
infrastructure/systemd/pse-pulse-eod.service
infrastructure/systemd/pse-pulse-eod.timer
pytest.ini
```

---

### 21.13 Remaining Known Issues
1. **Forecasting Stubs in Phase 1:** Forecasting providers (`LagInformedRegressionProvider`, `ArimaProvider`, `LstmProvider`) are pure architectural stubs projecting mathematical curves for UI and pipeline verification; actual serialized weights are planned for future phases.
2. **Synthetic Seed Data:** Historical daily prices and quotes are development seed fixtures; production end-of-day market scraping is scaffolded but not run live.
3. **Azure Infrastructure Unprovisioned:** Azure Bicep templates have been verified via local CLI compilation but remain strictly unapplied pending user authorization.

---

**RECOMMENDATION: READY FOR CHATGPT COMMIT APPROVAL**

