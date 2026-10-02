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
