# Production Runtime Architecture — Phase 4D

The owner reports that the infrastructure is deployed. A read-only Azure account-context check was attempted during this review but failed because the CLI session was unauthenticated; no resource state was queried. The VM power state remains unverified.

```mermaid
flowchart TD
    Browser -->|HTTPS :443| Nginx
    subgraph Existing Ubuntu 24.04 VM — Standard_B2als_v2
        Nginx -->|static export| Frontend[Next.js static files]
        Nginx -->|/api and health| API[FastAPI on 127.0.0.1:8000]
        Timer[Disabled systemd EOD timer] --> Runner[Strict production runner]
    end
    API -->|TLS, hostname verification, private route| PG[Existing PostgreSQL 16 — Standard_B1ms]
    Runner -->|validated source and model evidence| PG
```

## Network and process boundaries

- Nginx is the only intended public app listener and uses the existing HTTPS port 443. No port 80 or SSH listener is configured by the application scripts.
- FastAPI listens on loopback port 8000. Public docs and OpenAPI routes are denied. Production liveness does not depend on PostgreSQL; readiness returns a generic unavailable response when the DB probe fails.
- The API, bootstrap/migration role, and EOD inference runner use the existing PostgreSQL service over the private route with `sslmode=verify-full` and the system trust bundle. Production configuration rejects non-private DNS resolution.
- The API and inference workloads have separate Python environments. The Next.js app is statically exported on a separate build host; Node.js is not a runtime dependency on the VM.
- systemd runs workloads as `psepulse`, applies filesystem and network sandboxing, logs to journald, and uses a local failure notification unit. The EOD and certificate-renewal timers are disabled by default.

## Release and state layout

- `/opt/pse-pulse/releases/<commit-sha>` contains an immutable backend release and hash manifest; `/opt/pse-pulse/current` points to the active release.
- `backend/.venv-api` and `backend/.venv-inference` are generated for the release and excluded from source hashing. Release activation requires both environments, executable interpreters, root:`psepulse` ownership, and no group/other write access.
- `/var/www/pse-pulse/releases/<commit-sha>` stores a verified static frontend; `/var/www/pse-pulse/current` is switched atomically.
- `/etc/pse-pulse` contains root-controlled runtime configuration. Example files have placeholders and must never be used with placeholder secrets.
- `/var/lib/pse-pulse` contains owner-reviewed calendar/source records and model bundles. All data/model file use is hash and provenance checked. No binary model or market data is committed to Git.

## Production data flow

The production runner uses a reviewed PSE trading calendar to select the session. It verifies an official source file and its date-specific approval record, validates complete active-symbol coverage, imports idempotently, invokes only previously activated real artifacts, validates every company/model output, and records source and pipeline lineage. Missing source files remain pending; absent or inconsistent models fail. No demo forecast path is available in this runner.

Historical bootstrap and Alembic migration use a separate process role. The VM bootstrap and application startup do not migrate or create schema. Model bundle installation verifies contents but does not register or activate model rows. These actions remain separately gated.

## TLS and cost boundary

Nginx requires a trusted IP certificate for the existing public IP and does not offer HTTP. Let’s Encrypt currently supports short-lived IP certificates, but the proposed TLS-ALPN renewal handoff has not passed staging or external validation. The renewal unit remains disabled, and no public release should proceed until initial issuance, renewal, expiry monitoring, and failure recovery are proven.

The historical student-credit allocation was USD 100; remaining balance and expiry were not checked. The owner-provided October 2026 cost screenshot is reported as USD 4.88 accrued (VM USD 4.14, public IP USD 0.40, managed disk USD 0.30, private DNS USD 0.05, PostgreSQL USD 0.00) and a USD 75 budget alert. These are not live billing readings, and the budget is not a hard cap. The personal out-of-pocket maximum is USD 0. Do not upgrade to Pay-As-You-Go, add a payment method, buy a domain, or add billable Azure infrastructure.

For the step-by-step gated procedure and current implementation blockers, see [deployment runbook](azure-deployment.md) and [Phase 4D.1 report](../PHASE4D_IMPLEMENTATION_PREPARATION.md).
