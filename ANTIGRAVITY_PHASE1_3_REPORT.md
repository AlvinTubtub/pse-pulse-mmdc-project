# PSE Pulse — Personal Azure Edition
# Phase 1.3 Implementation & Hardening Report

**Project:** PSE Pulse — Personal Azure Edition  
**Repository:** `AlvinTubtub/pse-pulse-mmdc-project`  
**Branch:** `main`  
**Base Commit:** `a5bfaf0f4df770185e4c77e2f477cd5fda5bd4cd`  
**Execution Date:** October 2, 2026  
**Phase:** Phase 1.3 — Post-Push CI and Runtime Hardening  
**Status:** Complete — Ready for Review (Pre-Commit State)

---

## 1. Executive Summary

Following the initial Phase 1/1.1/1.2 commit and push (`a5bfaf0`), ChatGPT identified a CI workflow parsing failure (GitHub Actions run `36949443164`) and several runtime/configuration hardening requirements.

During **Phase 1.3**, the repository was systematically hardened without introducing Phase 2 features, without touching real PSE market ingestion, and without provisioning any Azure resources:
1. **GitHub Actions CI Workflow Fixed:** Resolved YAML parser failure caused by an unquoted scalar with a trailing colon (`DATABASE_URL: "sqlite:///:memory:"`), added top-level `permissions: contents: read`, added Python bytecode compilation (`compileall`), and added production dependency vulnerability auditing (`npm audit --omit=dev`).
2. **Frontend Same-Origin Relative API Base:** Configured `frontend/src/lib/api.ts` to default `API_BASE` to empty string `""` so that client requests resolve to `/api/v1/...` relative to the current origin behind Nginx, eliminating hardcoded ports, local development leakage, and cross-origin complexity in production.
3. **Company Detail Dynamic Runtime Fetch:** Refactored `frontend/src/app/companies/[symbol]/page.tsx` and introduced `frontend/src/components/CompanyDetailClient.tsx`. Retained `generateStaticParams()` for deterministic static shell generation while delegating client hydration to asynchronously fetch fresh quotes, 20-day price histories, and model forecasts from FastAPI at browser runtime.
4. **Client-Side Cache Standardization:** Replaced Next-specific server fetch options (`next: { revalidate: ... }`) with standard browser-compatible `{ cache: "no-store" }` across all client API utilities.
5. **FastAPI Lifespan Production Safety:** Guarded `Base.metadata.create_all` and `seed_database_if_empty` in `backend/app/main.py`. In production (`ENVIRONMENT=production`), automatic schema creation is bypassed, delegating schema management to Alembic migrations. When `DEMO_MODE=false`, demo data seeding is skipped.
6. **Alembic Production Documentation:** Updated `docs/azure-deployment.md` to document Alembic migration (`alembic -c backend/alembic.ini upgrade head`) as the mandatory production schema migration step before starting systemd services.
7. **CORS Parsing Flexibility:** Implemented a Pydantic field validator on `CORS_ORIGINS` in `backend/app/config.py` supporting comma-separated environment strings, JSON arrays, and native lists.
8. **Config & Lifespan Test Suite:** Added 5 new unit tests to `backend/tests/test_config.py` (totaling 28 passed backend tests, well exceeding the 23-test baseline).
9. **Infrastructure Security Hardening:** Hardened `allowedSshSourceIp` in `infrastructure/azure/main.bicep` (mandatory parameter without `0.0.0.0/0` default), updated `infrastructure/azure/parameters.example.json` with an example `/32` CIDR, and hardened `infrastructure/scripts/setup-vm.sh` to enforce `SSH_ALLOWED_CIDR` on UFW. Validated clean Bicep compilation (exit code 0) and removed transient artifacts.
10. **Full Runtime Smoke Verification:** Validated live reverse proxying via actual local Nginx (`127.0.0.1:8088`) and FastAPI (`127.0.0.1:8000`), confirming same-origin API routing, 404 behavior, and headless Google Chrome DevTools Protocol (CDP) execution with zero console errors and verified watchlist persistence.

---

## 2. Root Cause Analysis: GitHub Actions Run 36949443164

### Problem
GitHub Actions workflow run `36949443164` failed immediately upon push without executing any jobs.

### Cause
In `.github/workflows/ci.yml`, the environment variable for the backend test job was defined as:
```yaml
DATABASE_URL: sqlite:///:memory:
```
In YAML 1.2 specifications, a colon followed immediately by nothing or a space inside an unquoted scalar (`:memory:`) is interpreted as an invalid mapping key indicator rather than a literal string value. This caused GitHub Actions' YAML parser to reject the workflow file prior to step scheduling.

### Resolution
Enclosed the connection string in double quotes:
```yaml
DATABASE_URL: "sqlite:///:memory:"
```
Added top-level read-only permissions:
```yaml
permissions:
  contents: read
```
Verified valid YAML syntax locally using Python's `yaml.safe_load`.

---

## 3. GitHub Actions Hardening Details

File: `.github/workflows/ci.yml`

Key improvements implemented:
1. **Explicit Permissions:** Added `permissions: contents: read` at workflow root to adhere to the principle of least privilege.
2. **Quoted YAML Environment Variables:** Quoted `"sqlite:///:memory:"`.
3. **Job Renaming:** Renamed job from `backend-test` / `Backend Tests & Lint` to `Backend Tests` for clarity.
4. **Bytecode Compilation Step:** Added `python -m compileall backend/app backend/pipeline` to catch syntax or import regression errors before test execution.
5. **Dependency Security Audit:** Added `npm audit --omit=dev` to the frontend build job to ensure no high/critical vulnerabilities exist in production client packages.

---

## 4. Frontend API Base & Same-Origin Delivery

Files:
- `frontend/src/lib/api.ts`
- `frontend/.env.example`
- `.gitignore`

### Architectural Rationale
In Phase 1, `API_BASE` fell back to `"http://localhost:8000"`. In a production environment where static pages are served on port 80/443 and Nginx reverse proxies `/api/` to internal Uvicorn on `127.0.0.1:8000`, client browsers requesting `http://localhost:8000` would attempt to connect to the client user's local machine rather than the server, triggering connection errors and CORS failures.

### Implementation
Updated `frontend/src/lib/api.ts`:
```typescript
// Base API URL; defaults to empty string for same-origin production routing (/api/v1/...)
// Set NEXT_PUBLIC_API_URL in local development (e.g., http://localhost:8000)
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
```
When `NEXT_PUBLIC_API_URL` is unset (production build):
- Requests resolve to `/api/v1/...` relative to the current origin.
- Nginx receives `/api/v1/...` and transparently proxies it to `127.0.0.1:8000/api/v1/...`.
- No CORS configuration or exposed backend ports required in production.

For local frontend development outside Nginx, `frontend/.env.example` was created:
```env
# PSE Pulse Frontend — Local Development Configuration
# In production behind Nginx, leave unset so API requests resolve to same-origin (/api/v1/...)
NEXT_PUBLIC_API_URL=http://localhost:8000
```
Updated `.gitignore` to explicitly ignore `frontend/.env*` while preserving `!frontend/.env.example`.

---

## 5. Company Detail Live-Data Refactor

Files:
- `frontend/src/components/CompanyDetailClient.tsx` (New Client Component)
- `frontend/src/app/companies/[symbol]/page.tsx` (Refactored)

### Problem in Previous Implementation
In Next.js static export (`output: 'export'`), `async` Server Components are evaluated exclusively at `next build` time. As a result, market quotes, sparklines, and forecast cards were baked into static HTML files (`companies/SMPH.html`, etc.) during compilation, freezing the data indefinitely and failing to reflect live database updates.

### Solution
1. **Preserved Static Shells with `generateStaticParams()`:**
   `frontend/src/app/companies/[symbol]/page.tsx` continues to export `generateStaticParams()` returning `FALLBACK_COMPANIES`, allowing Next.js to pre-render the static HTML entrypoints for all 8 tracked blue-chip equities (`/companies/SMPH`, `/companies/BDO`, etc.).
2. **Extracted Dynamic Client Component (`CompanyDetailClient`):**
   Delegated page rendering to `"use client"` component `CompanyDetailClient`, which:
   - Maintains `loading`, `error`, `company`, and `forecasts` state.
   - Asynchronously queries `fetchCompany(symbol)` and `fetchLatestForecasts(symbol)` in `useEffect`.
   - Renders an accessible loading skeleton with spinner during initial fetch.
   - Renders an error recovery card with a "Retry" button upon network/data failures.
   - Dynamically displays live quotes, percentage change badges, 20-day sparklines, forecast projection cards, and historical price tables.
   - Provides a "Refresh Live" action button allowing users to re-poll quotes on demand.

### Browser CDP Verification
Verified in headless Google Chrome that navigating to `http://127.0.0.1:8088/companies/SMPH`:
- Loaded the static shell.
- Executed browser fetch to `/api/v1/companies/SMPH` and `/api/v1/forecasts/latest?symbol=SMPH`.
- Hydrated DOM with live company name "SM Prime Holdings, Inc.", latest close price, forward forecasts, and historical price table with zero uncaught JavaScript errors.

---

## 6. Audit of Other Frontend Pages

| Route | Page File | Component Type | Data Fetching Strategy | Dynamic Status |
| :--- | :--- | :--- | :--- | :--- |
| `/` | `src/app/page.tsx` | `"use client"` | `useEffect` (`fetchCompanies`, `fetchLatestForecasts`, `fetchPipelineStatus`) | **Live Browser Runtime** |
| `/companies` | `src/app/companies/page.tsx` | `"use client"` | `useEffect` (`fetchCompanies`) | **Live Browser Runtime** |
| `/companies/[symbol]` | `src/app/companies/[symbol]/page.tsx` | Static Shell + `"use client"` | `useEffect` (`fetchCompany`, `fetchLatestForecasts`) via `CompanyDetailClient` | **Live Browser Runtime** |
| `/watchlist` | `src/app/watchlist/page.tsx` | `"use client"` | `useEffect` (`fetchCompanies` + `localStorage` watchlist state) | **Live Browser Runtime** |
| `/models` | `src/app/models/page.tsx` | Static Component | Pure informative architectural documentation & specifications | **Static Documentation** |
| `/learn` | `src/app/learn/page.tsx` | Static Component | Pure educational documentation & glossary | **Static Documentation** |
| `/about` | `src/app/about/page.tsx` | Static Component | Pure project boundaries & Azure architecture documentation | **Static Documentation** |

All dynamic data-dependent pages now fetch data exclusively at browser runtime.

---

## 7. Client-Side Cache Optimization

File: `frontend/src/lib/api.ts`

### Changes Made
Removed Next.js server-specific cache options (`{ next: { revalidate: 60 } }` / `{ next: { revalidate: 30 } }`) across all API fetch helper functions:
- `fetchCompanies`
- `fetchCompany`
- `fetchLatestForecasts`
- `fetchPipelineStatus`
- `fetchSystemStatus`

Replaced with standard web API option `{ cache: "no-store" }`. This prevents browsers from caching stale market quotes or pipeline runs while remaining fully compliant with standard fetch specifications.

---

## 8. Backend Lifespan & Production Database Safety

File: `backend/app/main.py`

### Startup Safety Guard
To prevent accidental schema overwrites, table recreation, or demo data injection in production:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database tables and seed baseline data."""
    if settings.ENVIRONMENT != "production":
        logger.info("Non-production environment (%s): initializing schema via create_all...", settings.ENVIRONMENT)
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("Production environment: schema management delegated to Alembic migrations.")

    if settings.DEMO_MODE:
        logger.info("DEMO_MODE is True: seeding baseline demo data if database is empty...")
        db = SessionLocal()
        try:
            seed_database_if_empty(db)
        except Exception as e:
            logger.error("Error during initial data seed: %s", e)
        finally:
            db.close()
    else:
        logger.info("DEMO_MODE is False: skipping demo data seeding.")

    logger.info("Application startup complete. Environment: %s", settings.ENVIRONMENT)
    yield
    logger.info("Application shutting down...")
```

### Safety Guarantees
1. In `ENVIRONMENT=production`, `Base.metadata.create_all` is **never** executed. Schema must be provisioned and updated using Alembic.
2. When `DEMO_MODE=false`, demo data seeding is **never** executed.
3. In `ENVIRONMENT=development` / `ENVIRONMENT=test`, developers retain instant zero-setup SQLite/Docker initialization.

---

## 9. Production Schema Documentation

File: `docs/azure-deployment.md`

Enriched Section 3 (Phase B Step 5) to document Alembic as the mandatory production schema migration step:
```markdown
### Step 5: Run Database Migrations (Mandatory in Production)
> [!IMPORTANT]
> **Production Schema Governance:**
> In production (`ENVIRONMENT=production`), FastAPI startup intentionally skips `Base.metadata.create_all` and skips demo data seeding when `DEMO_MODE=false`. Alembic is the authoritative and required mechanism for creating and migrating database tables before starting the backend service.

```bash
sudo -u psepulse /opt/pse-pulse/backend/.venv/bin/alembic -c /opt/pse-pulse/backend/alembic.ini upgrade head
```
Verify that migration completed to `head`:
```bash
sudo -u psepulse /opt/pse-pulse/backend/.venv/bin/alembic -c /opt/pse-pulse/backend/alembic.ini current
```
```

---

## 10. CORS Configuration Hardening

File: `backend/app/config.py`

### Problem
Pydantic Settings parses complex types (such as `List[str]`) as JSON strings before custom field validators execute. Setting `CORS_ORIGINS=http://a,http://b` in `.env` resulted in a JSON parsing error.

### Solution
Updated field definition and added an `@field_validator("CORS_ORIGINS")`:
```python
    CORS_ORIGINS: Union[List[str], str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    @field_validator("CORS_ORIGINS")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS origins from comma-separated string, JSON array, or list."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return v
```
Supports comma-separated strings (`"http://a,http://b"`), JSON arrays (`'["http://a","http://b"]'`), single URLs, and empty strings (`""` -> `[]`).

---

## 11. Backend Configuration & Lifespan Test Suite

File: `backend/tests/test_config.py`

Expanded test coverage with 7 thorough test cases:
1. `test_settings_defaults`: Validates project name, version, default CORS origins, demo mode.
2. `test_settings_env_override`: Validates environment variable overrides (`ENVIRONMENT=production`, `DEBUG=false`, `DEMO_MODE=false`).
3. `test_settings_cors_comma_separated_env`: Validates comma-separated parsing from env, asserting exactly 2 parsed origins.
4. `test_settings_cors_json_array_env`: Validates JSON array string parsing from env.
5. `test_settings_cors_empty_env`: Validates empty string parsing (`""` -> `[]`).
6. `test_lifespan_production_guards_create_all_and_seed`: Asserts that under `ENVIRONMENT=production` and `DEMO_MODE=false`, neither `create_all` nor `seed_database_if_empty` is called.
7. `test_lifespan_development_invokes_create_all_and_seed`: Asserts that under `ENVIRONMENT=development` and `DEMO_MODE=true`, both `create_all` and `seed_database_if_empty` are called.

All 7 tests passed in 0.07s.

---

## 12. Azure Infrastructure & Network Hardening

Files:
- `infrastructure/azure/main.bicep`
- `infrastructure/azure/parameters.example.json`
- `infrastructure/scripts/setup-vm.sh`

### Changes Made
1. **Removed Permissive Default SSH CIDR:**
   In `main.bicep`, removed `param allowedSshSourceIp string = '0.0.0.0/0'` and made `allowedSshSourceIp` a mandatory string parameter with no default.
2. **Updated Example Parameters:**
   In `parameters.example.json`, updated `allowedSshSourceIp` to `"203.0.113.10/32"` (RFC 5737 documentation prefix) to model correct single-IP CIDR notation.
3. **Hardened UFW SSH Firewall Rule:**
   In `setup-vm.sh`, replaced generic `ufw allow 22/tcp` with:
   ```bash
   : "${SSH_ALLOWED_CIDR:?Error: Set SSH_ALLOWED_CIDR to your administrator public IP CIDR before running (e.g. export SSH_ALLOWED_CIDR='203.0.113.10/32')}"
   sudo ufw allow from "${SSH_ALLOWED_CIDR}" to any port 22 proto tcp comment 'SSH'
   ```
4. **Bicep Build Validation:**
   Validated compilation via Bicep CLI:
   ```bash
   bicep build infrastructure/azure/main.bicep --outfile infrastructure/azure/main.json
   ```
   Output: Exit code 0, 0 warnings, 0 errors.  
   Deleted temporary `infrastructure/azure/main.json` immediately after validation.

---

## 13. Actual Nginx & FastAPI Integration Smoke Test Results

Tested actual Nginx reverse proxy (`127.0.0.1:8088`) serving static files from `frontend/out` and proxying API traffic to live FastAPI Uvicorn (`127.0.0.1:8000`):

| HTTP Method & Path | Expected Status | Actual Status | Response Size | Verification Detail | Result |
| :--- | :---: | :---: | :---: | :--- | :---: |
| `GET /` | 200 | 200 | 30,201 B | Home Page (`index.html`) served | **PASS** |
| `GET /companies` | 200 | 200 | 22,118 B | Prefers `companies.html` over `companies/` dir | **PASS** |
| `GET /companies/SMPH` | 200 | 200 | 21,053 B | Serves pre-rendered static shell (`SMPH.html`) | **PASS** |
| `GET /watchlist` | 200 | 200 | 21,811 B | Watchlist Page (`watchlist.html`) served | **PASS** |
| `GET /models` | 200 | 200 | 43,087 B | Model explanations (`models.html`) served | **PASS** |
| `GET /learn` | 200 | 200 | 30,523 B | Learning center (`learn.html`) served | **PASS** |
| `GET /about` | 200 | 200 | 40,424 B | About page (`about.html`) served | **PASS** |
| `GET /health` | 200 | 200 | 108 B | Proxied to FastAPI `/health`, status `"ok"` | **PASS** |
| `GET /api/v1/companies` | 200 | 200 | 1,178 B | Path `/api/v1` preserved; returns 8 companies | **PASS** |
| `GET /api/v1/forecasts/latest` | 200 | 200 | 15,438 B | Path `/api/v1` preserved; returns forecasts | **PASS** |
| `GET /definitely-not-a-real-page` | 404 | 404 | 19,939 B | Returns genuine HTTP 404 and serves `404.html` | **PASS** |
| `GET /companies/` | 404 | 404 | 19,939 B | Trailing slash returns genuine 404 | **PASS** |
| `GET /companies/SMPH/` | 404 | 404 | 19,939 B | Trailing slash returns genuine 404 | **PASS** |

**Summary:** 13/13 routes passed with exact status codes and expected proxy behavior.

---

## 14. Headless Chrome DevTools Protocol (CDP) Verification

Executed end-to-end browser runtime validation using Google Chrome in headless mode connected to Nginx (`http://127.0.0.1:8088`):

1. **Console Error Inspection:**
   - `/`: 0 uncaught errors (DOM length: 2,973 chars)
   - `/companies`: 0 uncaught errors (DOM length: 1,210 chars)
   - `/companies/SMPH`: 0 uncaught errors (DOM length: 3,555 chars)
   - `/watchlist`: 0 uncaught errors (DOM length: 858 chars)
2. **Company Detail Dynamic Render Assertion:**
   On `/companies/SMPH`, verified via Chrome Runtime DOM evaluation:
   - `hasSMPHName`: `True` ("SM Prime Holdings, Inc.")
   - `hasForecasts`: `True` ("Model Forecasts for SMPH")
   - `hasHistory`: `True` ("Historical Daily Prices")
   - `hasRefresh`: `True` ("Refresh Live")
   Confirmed `CompanyDetailClient` successfully fetched and hydrated live data from `/api/v1` via Nginx.
3. **Watchlist Persistence Across Browser Reload:**
   - Populated `localStorage` with `['SMPH', 'BDO']`.
   - Reloaded page: verified both equities render in DOM table.
   - Cleared `localStorage` to `[]`.
   - Reloaded page: verified "Your Watchlist is Currently Empty" empty state banner renders.

---

## 15. Full Validation Test Summary

### Backend
- **Bytecode Compilation:** `python -m compileall backend/app backend/pipeline backend/alembic backend/tests` — Clean (0 errors).
- **Pytest Suite:** `pytest -v` — **28 passed in 0.54s** (exceeds requirement of > 23 passed tests).

### Frontend
- **Lint:** `npm run lint` — Clean (0 errors, 0 warnings).
- **Typecheck:** `npx tsc --noEmit` — Clean (0 errors).
- **Static Export Build:** `npm run build` — Clean (16 static/SSG pages generated).
- **Dependency Audit:** `npm audit --omit=dev` — **0 vulnerabilities**.

### Security Scan
- Scanned repository for private keys, tokens, and credentials — **Clean**.
- Confirmed `.gitignore` protects `.env`, `.env.*`, `frontend/.env`, `frontend/.env.*`, `*.db`, `out/`, `node_modules/`, `.venv/`.

---

## 16. Git Working Tree State

```text
 M .github/workflows/ci.yml
 M .gitignore
 M backend/app/config.py
 M backend/app/main.py
 M backend/tests/test_config.py
 M docs/azure-deployment.md
 M frontend/src/app/companies/[symbol]/page.tsx
 M frontend/src/lib/api.ts
 M infrastructure/azure/main.bicep
 M infrastructure/azure/parameters.example.json
 M infrastructure/scripts/setup-vm.sh
?? frontend/.env.example
?? frontend/src/components/CompanyDetailClient.tsx
?? ANTIGRAVITY_PHASE1_3_REPORT.md
```

No commits, pushes, pull requests, or Azure deployments have been made.

---

## Phase 1.3A — Production Demo-Data Safety

### 1. Production Backend Safety
Implemented defense-in-depth safety ensuring synthetic data is never generated or seeded into the production database:
1. **Pydantic Configuration Model Validator (`backend/app/config.py`):**
   Added `@model_validator(mode="after")` `validate_production_demo_mode`:
   - `ENVIRONMENT=production + DEMO_MODE=true` -> **Hard validation failure (`ValueError`)**. Fails fast on application startup/instantiation.
   - `ENVIRONMENT=production + DEMO_MODE=false` -> **Valid**.
   - `ENVIRONMENT=development + DEMO_MODE=true` -> **Valid**.
   - `ENVIRONMENT=development + DEMO_MODE=false` -> **Valid**.
2. **Explicit Lifespan Startup Branching (`backend/app/main.py`):**
   `lifespan` explicitly checks `is_production = settings.ENVIRONMENT.lower() == "production"`:
   - When `is_production` is true:
     Logs clearly:
     ```text
     Production environment detected.
     Automatic schema creation disabled.
     Demo database seeding disabled.
     Schema must be managed through Alembic.
     ```
     Bypasses `Base.metadata.create_all` and bypasses `seed_database_if_empty`.
   - When `is_production` is false:
     Executes `Base.metadata.create_all(bind=engine)` and seeds demo data only if `DEMO_MODE=true`.

### 2. Frontend Fallback Safety
Restricted synthetic fallback data in `frontend/src/lib/api.ts`:
1. Introduced `export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";`.
2. When `NEXT_PUBLIC_DEMO_MODE=false` (default for production builds):
   - `fetchCompanies()` throws `Error("Market data is temporarily unavailable...")` upon API failure.
   - `fetchCompany()` throws `Error("Market data is temporarily unavailable...")` upon API failure (or returns `null` for 404).
   - `fetchLatestForecasts()` throws `Error("Forecast projections are temporarily unavailable...")` upon API failure.
   - `fetchPipelineStatus()` returns `null` upon API failure.
   - **Zero synthetic records, fake prices, or mock forecasts are substituted in production.**
3. When `NEXT_PUBLIC_DEMO_MODE=true` (development only):
   - Caught network errors return labelled `FALLBACK_COMPANIES` or demo forecasts so offline frontend prototyping remains functional.

### 3. Error UI & Outage States
All runtime data-dependent pages now handle backend outages and loading states gracefully:
- **Home Page (`/`):**
  - Loading state: "Loading market data…" with spinner.
  - Outage state: Renders a dedicated "Market Data Unavailable" error card with explanation and "Retry Connection" button. Zero fake cards or prices rendered.
  - Demo state: Displays prominent `DEMO ENVIRONMENT ACTIVE` banner when `NEXT_PUBLIC_DEMO_MODE=true`.
- **Companies Directory (`/companies`):**
  - Loading state: "Loading market data…" with spinner.
  - Outage state: Renders "Market Data Unavailable" card with retry button. Table with fake equities is not rendered.
  - Demo state: Displays `DEMO ENVIRONMENT ACTIVE` banner.
- **Company Detail (`/companies/[symbol]`):**
  - Loading state: "Loading market data…" with spinner.
  - Outage state: Renders "Market Data Unavailable" card with retry button and link to directory.
  - Demo state: Displays `DEMO ENVIRONMENT ACTIVE` banner.
- **Watchlist Page (`/watchlist`):**
  - Loading state: "Loading market data…" with spinner.
  - Outage state: Renders "Market Data Unavailable" card with retry button.
  - Empty state: Clean "Your Watchlist is Currently Empty" banner.

### 4. Environment Variables Configuration
Documented configurations in `frontend/.env.example` and `docs/azure-deployment.md`:
- **Local Development:**
  ```env
  NEXT_PUBLIC_API_URL=http://localhost:8000
  NEXT_PUBLIC_DEMO_MODE=true
  ```
- **Azure Production:**
  ```env
  NEXT_PUBLIC_API_URL=
  NEXT_PUBLIC_DEMO_MODE=false
  ```
  ```env
  ENVIRONMENT=production
  DEMO_MODE=false
  ```
- **Database Migrations:**
  Production schema must be migrated explicitly:
  ```bash
  alembic -c backend/alembic.ini upgrade head
  ```

### 5. Backend & Frontend Test Suite Results
- **Backend Bytecode Compilation:** `compileall backend/app backend/pipeline` — 0 errors.
- **Backend Pytest Suite:** **33 passed in 0.48s** (increased from 28; adds tests for production rejection, development allowances, and defense-in-depth lifespan behavior).
- **Frontend Lint:** `npm run lint` — **0 errors, 0 warnings**.
- **Frontend Typecheck:** `npx tsc --noEmit` — **0 errors**.
- **Frontend Static Export Build:** `npm run build` (`NEXT_PUBLIC_DEMO_MODE=false`) — **16 static/SSG pages successfully generated**.
- **Frontend Security Audit:** `npm audit --omit=dev` — **0 vulnerabilities**.

### 6. Browser Runtime CDP Verification
Executed end-to-end Chrome DevTools Protocol verification against live Nginx (`127.0.0.1:8088`):
1. **Backend OFFLINE (Outage Simulation):**
   - `/`: Rendered "Market Data Unavailable", `hasFakeQuotes: False`, 0 synthetic figures.
   - `/companies`: Rendered "Market Data Unavailable", `hasTable: False`, 0 synthetic records.
   - `/companies/SMPH`: Rendered "Market Data Unavailable", `hasFakeHistory: False`, 0 synthetic prices.
2. **Backend ONLINE (Recovery Simulation):**
   - Brought FastAPI Uvicorn online on `127.0.0.1:8000`.
   - Navigated to `/companies/SMPH`: Successfully recovered and rendered live data (`hasSMPH: True`, `hasForecasts: True`, `hasHistory: True`).
   - Uncaught JavaScript Errors: **0 across all pages**.

### 7. Deployment Script Coherence Check (Report Only)
Inspected:
- `infrastructure/scripts/setup-vm.sh`
- `infrastructure/scripts/deploy-static.sh`

**Known Remaining Issues (Identified for Pre-Azure Deployment Phase):**
1. **Missing Tooling in `setup-vm.sh`:**
   - `deploy-static.sh` invokes `npm ci`, `npm run build`, and `rsync`.
   - `setup-vm.sh` currently installs base packages (`nginx`, `python3.12`, `python3.12-venv`, `python3-pip`, `git`, `curl`, `ufw`, `fail2ban`), but does **not** install `nodejs`, `npm`, or `rsync`.
2. **Host VM Memory Architecture:**
   - Sizing target is `Standard_B2ats_v2` (1 GiB RAM). Building Next.js static export (`npm run build`) on the host VM directly can cause significant memory pressure during webpack/swc compilation.
   - The recommended production workflow documented in `docs/azure-deployment.md` Phase D is to compile the static export off-host (in CI or on local developer machine) and sync the resulting `out/` directory to `/var/www/pse-pulse/out` via SSH/rsync.
   - In a future pre-deployment pass, `deploy-static.sh` and `setup-vm.sh` should be aligned with this off-host build pattern.

### 8. Files Modified in Phase 1.3A
- `backend/app/config.py`: Added `model_validator` rejecting `DEMO_MODE=true` when `ENVIRONMENT=production`.
- `backend/app/main.py`: Explicitly branched `is_production` to disable `create_all` and demo seeding, with production logging.
- `backend/tests/test_config.py`: Added 5 new tests validating production demo rejection, development demo allowance, and lifespan defense-in-depth.
- `frontend/src/lib/api.ts`: Added `NEXT_PUBLIC_DEMO_MODE` gate preventing silent synthetic data substitution in production.
- `frontend/src/app/page.tsx`: Added explicit loading, outage error UI, and demo banner.
- `frontend/src/app/companies/page.tsx`: Added loading, outage error UI, and demo banner.
- `frontend/src/app/companies/[symbol]/page.tsx` + `frontend/src/components/CompanyDetailClient.tsx`: Added loading, outage error UI, and demo banner.
- `frontend/src/app/watchlist/page.tsx`: Added loading, outage error UI, and demo banner.
- `frontend/.env.example`: Documented `NEXT_PUBLIC_DEMO_MODE` settings for dev and prod.
- `docs/azure-deployment.md`: Documented production backend `DEMO_MODE=false` enforcement and frontend build flags `NEXT_PUBLIC_DEMO_MODE=false`.

### 9. Git Status Summary
```text
 M .github/workflows/ci.yml
 M .gitignore
 M backend/app/config.py
 M backend/app/main.py
 M backend/tests/test_config.py
 M docs/azure-deployment.md
 M frontend/src/app/companies/[symbol]/page.tsx
 M frontend/src/app/companies/page.tsx
 M frontend/src/app/page.tsx
 M frontend/src/app/watchlist/page.tsx
 M frontend/src/lib/api.ts
 M infrastructure/azure/main.bicep
 M infrastructure/azure/parameters.example.json
 M infrastructure/scripts/setup-vm.sh
?? ANTIGRAVITY_PHASE1_3_REPORT.md
?? frontend/.env.example
?? frontend/src/components/CompanyDetailClient.tsx
```

---

RECOMMENDATION: READY FOR CHATGPT REVIEW BEFORE CORRECTIVE COMMIT
