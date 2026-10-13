# Azure Production Deployment — Phase 4D

The owner reports that the approved infrastructure already exists. This runbook concerns application runtime deployment to those resources only. It does not authorize infrastructure deployment, billing changes, SSH exposure, database migrations, model activation, or inference.

## Existing target

- Resource group: `rg-pse-pulse-student-prod`
- Region: `eastasia`
- VM: `vm-psepulse-aui7qjkkdw4ye`, Ubuntu 24.04 LTS, `Standard_B2als_v2`
- PostgreSQL: `pg-psepulse-aui7qjkkdw4ye`, PostgreSQL 16, `Standard_B1ms`, private access
- Owner-reported student credit: USD 100 at the last report; recheck current balance and spending protection before any Azure operation.
- Maximum personal out-of-pocket spending: USD 0.

Use only the existing resources. Do not upgrade to Pay-As-You-Go, attach a payment method, buy a domain, add a paid service, or create Azure resources. Preserve public SSH disabled; do not open TCP 22. Keep PostgreSQL private and TLS-verified.

## Application topology

Nginx serves the built Next.js export and proxies same-origin API requests to FastAPI on `127.0.0.1:8000`. PostgreSQL is reached by its owner-verified private DNS name over TLS with hostname verification. The API and inference job run as the unprivileged `psepulse` account in separate Python 3.12 environments. Node.js is needed only on the artifact build host.

The API is a systemd service. The market close job is a dedicated strict production runner and its timer is disabled until separate schedule approval. The certificate renewal timer is also disabled until ACME staging and external trust checks pass. The service units use journald and local failure reporting.

## Offline artifact preparation

1. Review and commit the source separately before producing a release. The release scripts require a clean checkout at the exact full commit SHA.
2. Build a backend package with `infrastructure/scripts/build-backend-release.sh <commit-sha> <new-output-file>`. The resulting archive has a SHA-256 manifest; transfer it only through an independently reviewed authenticated route.
3. Build the frontend with `infrastructure/scripts/build-static.sh <commit-sha>`. It runs `npm ci`, lint, typecheck, and static build with demo mode disabled. Review the exported files and manifest before transfer.
4. Before deployment, replace the broad Python dependency ranges with a reviewed hash-pinned lock and test it on Ubuntu 24.04 x86-64. The current `requirements-production-*.txt` files are not yet reproducible locks.
5. Verify official data, the calendar, source approval index, and model bundle using the approved provenance manifests. Data and model assets stay outside Git.

## Existing VM operation sequence

These steps require a separate deployment authorization. They were not performed during Phase 4D.1 preparation.

1. Read-only checks: verify subscription/spend limit, current VM and PostgreSQL identity, VM Agent health, 443-only inbound path, private DB DNS/TLS, free disk, and existing migration revision. Do not print full account identifiers or credentials.
2. Use Azure VM Run Command against the existing VM to run the reviewed `infrastructure/scripts/setup-vm.sh`. It installs base packages and creates local service directories; it does not alter Azure networking or start the application.
3. Transfer the reviewed backend archive and frontend artifact. Verify SHA-256 before extraction. Stage the release under `/opt/pse-pulse/releases/<commit-sha>` and set root-owned, non-writable release permissions.
4. Run `stage-backend-release.sh <commit-sha>` for the inactive release. This creates the API and inference environments, installs production dependencies, and verifies the release again. Confirm disk headroom and package source before this step.
5. Install production environment files through a separately reviewed secret route. Templates under `infrastructure/config/` contain placeholders only. Keep database credentials out of Run Command output, shell arguments, terminal history, and logs.
6. Before migration, verify private DNS and PostgreSQL TLS with hostname verification, confirm DB identity and current revision, review generated migration SQL, and take/verify an available backup. Migration approval is separate. Bootstrap does not migrate automatically.
7. Install reviewed units and configuration, but do not start units before acceptance:

   ```bash
   sudo install -o root -g root -m 0644 infrastructure/systemd/pse-pulse-api.service /etc/systemd/system/
   sudo install -o root -g root -m 0644 infrastructure/systemd/pse-pulse-migration.service /etc/systemd/system/
   sudo install -o root -g root -m 0644 infrastructure/systemd/pse-pulse-eod.service /etc/systemd/system/
   sudo install -o root -g root -m 0644 infrastructure/systemd/pse-pulse-eod.timer /etc/systemd/system/
   sudo install -o root -g root -m 0644 infrastructure/systemd/pse-pulse-cert-renew.service /etc/systemd/system/
   sudo install -o root -g root -m 0644 infrastructure/systemd/pse-pulse-cert-renew.timer /etc/systemd/system/
   sudo install -o root -g root -m 0644 'infrastructure/systemd/pse-pulse-failure-alert@.service' /etc/systemd/system/
   sudo install -d -o root -g root -m 0755 /etc/systemd/journald.conf.d
   sudo install -o root -g root -m 0644 infrastructure/config/90-pse-pulse-journald.conf /etc/systemd/journald.conf.d/90-pse-pulse.conf
   sudo install -o root -g root -m 0750 infrastructure/scripts/renew-ip-certificate.sh /usr/local/sbin/pse-pulse-renew-ip-certificate
   sudo install -o root -g root -m 0644 infrastructure/nginx/pse-pulse.conf /etc/nginx/sites-available/pse-pulse.conf
   sudo ln -sfn /etc/nginx/sites-available/pse-pulse.conf /etc/nginx/sites-enabled/pse-pulse.conf
   sudo systemctl daemon-reload
   ```

   Run `nginx -t` only after the accepted certificate exists at the configured path. The Nginx site, API service, migration service, EOD timer, and certificate timer remain inactive until their separate acceptance steps.
8. Only after migration authorization, invoke the dedicated service with `sudo systemctl start pse-pulse-migration.service`. Then verify the revision and readiness before starting or enabling the API.
9. Deploy the static export using `deploy-static.sh <verified-artifact-directory> <commit-sha>`. It switches the static release atomically and does not start/reload Nginx.
10. Activate the verified backend release using `activate-backend-release.sh <commit-sha>`. It does not restart services. Review the unit files and start/restart the API only under separate approval.
11. Validate `/health/live`, `/health/ready`, frontend static routes, same-origin API, database TLS, bounded logs, and reboot behavior. Keep inference disabled.

## Production data and inference gates

Historical import must use owner-approved official PSE source files, exact source hashes, an approved date calendar, and a separate production bootstrap role. The production EOD runner requires complete tracked-symbol data and matching approved source evidence; missing files remain pending or fail closed.

Model installation verifies the accepted bundle and hashes but does not register or activate models. Activation, a dry-run inference, the first persistent inference, and scheduled inference each require separate independent review and approval. Keep `REAL_MODELS_ENABLED=false` and `MODEL_ARTIFACT_ACTIVATION_ENABLED=false` until their respective gates pass. The timer unit is not enabled by default.

## HTTPS acceptance gate

Nginx serves HTTPS only on the existing 443 ingress and requires an IP Subject Alternative Name certificate. No domain purchase is necessary in principle because Let’s Encrypt supports short-lived IP certificates, but the current renewal approach has not been proven on the VM. The ACME renewal service is disabled by default and does not implement initial issuance. Before public service, pin and review the ACME client, prove staging issuance and renewal on port 443, verify the certificate chain externally, and test failure recovery. Do not expose the app through HTTP or a self-signed production certificate.

## Stop conditions

Stop before a VM operation if current credit/spend protections are unknown, the private DB route or TLS verification fails, disk capacity is insufficient, the Python lock is not approved, source/model provenance is incomplete, DB state/backup is unknown, certificate trust has not passed, or a deployment artifact hash differs. Never auto-repair the database, create resources, or change network/billing settings.

For the implementation status, tests, blockers, and operation counts, see [Phase 4D.1 implementation report](../PHASE4D_IMPLEMENTATION_PREPARATION.md).
