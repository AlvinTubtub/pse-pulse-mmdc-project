# PSE Pulse — Personal Azure Edition

An independent personal market analytics and forecasting engine tailored specifically for Philippine Stock Exchange (PSE) equities, designed to run within the free-tier allowances of an **Azure for Students** subscription.

> [!IMPORTANT]
> **Project Boundary & Independence:**
> This repository is a completely separate personal project created by Alvin Tubtub. It is **NOT** part of any Capstone or academic submission, and maintains complete separation from institutional repositories, infrastructure, and datasets.

---

## Architecture Overview

PSE Pulse achieves high efficiency and predictable zero-cost hosting by decoupling dynamic API services from static UI delivery:

- **Frontend:** Next.js (App Router, TypeScript, Tailwind CSS) compiled via `output: 'export'` into static HTML/CSS/JS. Served directly by Nginx from disk with zero running Node.js server.
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic, SQLAlchemy 2.0, Alembic. Lightweight process footprint (< 60 MB RSS).
- **Forecasting:** Pluggable `ForecastProvider` interface supporting baseline models (Lag-Informed Regression, ARIMA, LSTM). In Phase 1, providers operate as lightweight inference stubs; heavy model training runtimes (PyTorch/TensorFlow) are strictly excluded from the production VM.
- **Database:** PostgreSQL (local `docker-compose.dev.yml` for development; Azure Database for PostgreSQL Flexible Server B1ms in production with a 32 GB storage limit).
- **Target Host:** Ubuntu 24.04 LTS VM on Azure `Standard_B2ats_v2` (2 vCPU, 1 GiB RAM) or `Standard_B1s` fallback.

---

## Directory Structure

```text
pse-pulse-mmdc-project/
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI (Backend & Frontend)
├── backend/
│   ├── alembic/               # Database migration scripts
│   ├── alembic.ini            # Alembic migration configuration
│   ├── app/
│   │   ├── api/v1/            # Versioned API endpoints (/system, /companies, /forecasts, /pipeline)
│   │   ├── forecasting/       # Pluggable ForecastProvider interfaces & stubs
│   │   ├── models/            # SQLAlchemy database models
│   │   ├── schemas/           # Pydantic validation schemas
│   │   ├── services/          # Development seed data generators
│   │   ├── config.py          # Centralized pydantic-settings
│   │   ├── database.py        # Database connection engine & session
│   │   └── main.py            # FastAPI application entrypoint
│   ├── pipeline/              # Data pipeline scaffolding (ingest, validation, features, persistence)
│   ├── tests/                 # Pytest backend test suite
│   └── requirements.txt       # Lightweight Python dependencies
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js App Router pages (Home, Companies, Watchlist, Models, Learn, About)
│   │   ├── components/        # Reusable UI components (Table, Navbar, Footer, Banners, SVG Sparklines)
│   │   └── lib/               # API clients, TypeScript types, and localStorage watchlist
│   ├── next.config.mjs        # Next.js static export configuration (output: 'export')
│   ├── package.json           # Frontend dependencies
│   ├── tailwind.config.ts     # Tailwind CSS styling configuration
│   └── tsconfig.json          # TypeScript compiler configuration
├── infrastructure/
│   ├── azure/                 # Bicep IaC scaffolding & parameters (NOT deployed)
│   ├── nginx/                 # Nginx virtual host configuration template
│   ├── scripts/               # VM setup, deployment, and pipeline shell scripts
│   └── systemd/               # Systemd services and timer units
├── docs/
│   ├── architecture.md        # Technical architecture & design rationale
│   ├── azure-deployment.md    # Future Azure deployment runbook
│   └── cost-guardrails.md     # Free-tier constraints & spending protections
├── docker-compose.dev.yml     # Local development PostgreSQL container only
├── .env.example               # Environment variables template
├── .gitignore                 # Source control ignore rules
├── LICENSE                    # MIT License
└── README.md                  # Project documentation
```

---

## Prerequisites

- **Python:** 3.12+
- **Node.js:** 20+ (Node 24 supported)
- **Docker & Docker Compose:** Optional for local PostgreSQL development.

---

## Local Development Setup

### 1. Database (Optional Local Docker PostgreSQL)

To start an isolated PostgreSQL database for local development:
```bash
docker compose -f docker-compose.dev.yml up -d
```
*Note: SQLite (`sqlite:///./pse_pulse_dev.db`) is used automatically as a frictionless default if Docker is not running.*

### 2. Backend Setup & Run

```bash
# 1. Create Python 3.12 virtual environment
python3.12 -m venv backend/.venv
source backend/.venv/bin/activate

# 2. Install lightweight dependencies
pip install -r backend/requirements.txt

# 3. Copy environment configuration
cp .env.example .env

# 4. Run database migrations
alembic -c backend/alembic.ini upgrade head

# 5. Start development API server
uvicorn backend.app.main:app --reload --port 8000
```
- API will be accessible at: `http://localhost:8000`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`
- Health Probe: `http://localhost:8000/health`

### 3. Frontend Setup & Run

```bash
cd frontend

# 1. Install dependencies
npm ci

# 2. Run local development server
npm run dev
```
- Frontend UI accessible at: `http://localhost:3000`

---

## Validation & Testing Commands

### Backend Validation
```bash
# Run backend test suite
pytest -v

# Run in quiet mode
pytest -q
```

### Frontend Validation & Static Export Build
```bash
cd frontend

# Verify clean dependency tree
npm ci

# Run linting check
npm run lint

# Run TypeScript type check
npx tsc --noEmit

# Compile static HTML/JS export to frontend/out/
npm run build
```

---

## API Endpoints (v1)

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Lightweight uptime health check probe |
| `GET` | `/api/v1/system/status` | Process memory RSS, DB connectivity, and cloud target details |
| `GET` | `/api/v1/companies` | List of listed companies with latest prices and changes |
| `GET` | `/api/v1/companies/{symbol}` | Company profile with recent historical daily prices |
| `GET` | `/api/v1/forecasts/latest` | Forward forecasts across active model stubs with demo disclaimer |
| `GET` | `/api/v1/pipeline/status` | EOD market pipeline status, cron schedule, and last run metadata |
| `GET` | `/api/v1/models` | List of supported forecasting model architectures |

---

## Cost & Azure Guardrails

- **Zero-Cost Goal:** Intended to run entirely within Azure for Students free allowances ($0/mo).
- **Target VM:** `Standard_B2ats_v2` (2 vCPU, 1 GiB RAM) with a single Premium SSD P6 64-GiB OS disk. Fallback VM: `Standard_B1s`.
- **Database:** Azure Database for PostgreSQL Flexible Server (Burstable B1ms, 32 GB max storage, auto-grow disabled, public access with single-IP firewall to avoid metered Azure Private DNS zones).
- **No Heavy Runtimes:** No PyTorch, TensorFlow, Redis, Celery, or Node.js runtime on production VM.
- Refer to [docs/cost-guardrails.md](docs/cost-guardrails.md) for detailed budget safeguards.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
