# Azure Production Architecture — Phase 4A Proposal

This document describes the Phase 4A target only. It is not deployed infrastructure. Subscription, quota, region, and billing assumptions remain gates; see [the readiness report](../PHASE4A_READINESS_REPORT.md).

## Recommended topology

```text
Internet
  └─ Standard static IPv4 :443
       └─ NSG (HTTPS open; administrative ingress restricted)
            └─ Ubuntu 24.04 x86-64 VM (Standard_B2als_v2, 2 vCPU / 4 GiB)
                 ├─ Nginx: Next.js static export; /api reverse proxy
                 ├─ FastAPI + Uvicorn: loopback only, systemd service
                 ├─ Verified immutable model bundle in local cache
                 └─ systemd EOD timer (Asia/Manila; no training/refit)
                      └─ PostgreSQL Flexible Server B1ms, private VNet access, TLS

Optional release distribution:
VM managed identity ── Storage Blob Data Reader ── GPv2 LRS Hot artifact container
```

Use one VNet, separate app and delegated PostgreSQL subnets, and a required Azure Private DNS zone linked for PostgreSQL private access. The zone and DNS queries are metered; include them in the Phase 4B cost estimate. This zone is distinct from an optional public domain/DNS service. Keep HA off for the student deployment unless separately approved. The application connects to PostgreSQL over the private path with TLS. Do not add a Private Endpoint for this topology unless a later design demonstrates a need. A static public IPv4 is required by the selected straightforward public HTTPS design and will consume credit.

## Compute and memory decision

Primary candidate: `Standard_B2als_v2`, 2 vCPU, 4 GiB, x86-64. The local full-service dry run peaked at 570.5 MiB across API parent and inference child. Adding planning reserves of 512 MiB OS + 32 MiB Nginx + 128 MiB Uvicorn/service gives 1,243 MiB expected occupied and 2,853 MiB remaining on a 4 GiB machine. This leaves 69.7% of physical memory in the estimate. The profile ran on macOS ARM64 and must be followed by Linux target validation in a later authorized phase.

Fallback: `Standard_B2as_v2`, 2 vCPU, 8 GiB, x86-64. The 1 GiB B1s, B2ats_v2, and B2pts_v2 fail the project memory rule. B2pts_v2's CPython 3.12 ARM64 wheels exist for the checked dependency set, but no Azure/Linux runtime was tested and it still has only 1 GiB; it is not a suitable fallback.

## Application layout

- `/opt/pse-pulse/app`: application release, deployed from a reviewed immutable Git revision.
- `/opt/pse-pulse/venv`: Python 3.12 virtual environment.
- `/var/lib/pse-pulse/artifacts/2026.10.01-authoritative-v1`: verified immutable model cache.
- `/etc/pse-pulse/pse-pulse-api.env`: root-owned, mode 0640, service-readable; secrets excluded from Git.
- `psepulse` non-root service account; Nginx serves the static export and proxies `/api` to `127.0.0.1:8000`.
- systemd API service and one EOD timer in `Asia/Manila`; no model-training or refit schedule.

Use systemd sandboxing (`NoNewPrivileges`, `PrivateTmp`, read-only system paths, narrow writable state directory) and journald with bounded retention. Configure the timer only after market-data completion checks and idempotency are verified. A missed market-data day must not produce duplicate forecasts.

## Database and artifact handling

Candidate database: Azure Database for PostgreSQL Flexible Server Burstable B1ms, 32 GiB data storage, up to the published 32 GiB backup allowance if the exact subscription offers it, TLS required, private access, HA off. Confirm current PostgreSQL version, region, quota, backup behavior and free meter before IaC approval.

The current 51 MiB immutable bundle can live on the VM's managed disk after manifest, SHA-256, metadata, and provenance verification. Blob is optional, not required for inference. If used for distribution, prefer GPv2 Standard LRS Hot and VM system-assigned managed identity with `Storage Blob Data Reader` scoped to the artifact container. Verify the manifest and every artifact hash before moving a bundle into the active cache. Never use storage account keys in app configuration.

The later production sequence has independent approval gates for infrastructure creation, artifact activation, first persistent inference, and scheduled inference:

1. Deploy infrastructure with both repository safety switches false; verify VM, network and PostgreSQL.
2. Migrate only the specifically approved production database, seed canonical company/model metadata, bootstrap/import historical OHLCV, then reconcile dates and counts.
3. Place/copy the accepted immutable bundle into the production cache. Verify bundle version, manifest SHA-256, every artifact SHA-256, metadata/provenance and exactly 45 artifacts.
4. Register exactly 45 candidate `ModelArtifact` rows **INACTIVE**.
5. Obtain separate production activation authorization. Set `MODEL_ARTIFACT_ACTIVATION_ENABLED=true` only in the dedicated activation process; atomically activate exactly 45 candidates.
6. Verify 45 candidate rows, 45 active, 0 inactive, exactly one active lineage per company × model family, and zero `Forecast` rows created by activation. Return `MODEL_ARTIFACT_ACTIVATION_ENABLED=false`.
7. Run controlled production dry-run inference with `REAL_MODELS_ENABLED=true` only in that inference process. It runs after active artifact lineage exists. Require 15 companies, 45 predictions, exact active lineage, Forecast delta 0, no training/refit, and activation flag false.
8. After dry-run acceptance, separately authorize first persistent production inference; validate persisted forecasts, lineage, dates, idempotency and API visibility.
9. Only after production acceptance, separately authorize scheduled EOD inference.

Repository defaults remain `REAL_MODELS_ENABLED=false` and `MODEL_ARTIFACT_ACTIVATION_ENABLED=false`. Infrastructure approval does not imply activation approval, and activation approval does not imply permission for persistent or scheduled inference. None of these production actions is part of Phase 4A.

## Public exposure and security

Selected gate: accept a Standard static public IPv4 meter for public HTTPS. Permit TCP 443 to Nginx. Restrict SSH to a confirmed administrator source or use an independently reviewed access pattern; do not open SSH to all addresses. Disable password authentication, use managed identity for Azure data access, store DB credentials outside Git, enforce database TLS/private networking, and disable directory listing/debug endpoints as applicable. Expose no model activation or administration route publicly without a separate review.

The selected application VM has the Standard static public IPv4 attached to its NIC. That address is the selected explicit inbound/outbound path for HTTPS and normal VM Internet connectivity; no NAT Gateway is included in the baseline. NAT Gateway, Azure Firewall, Load Balancer outbound rules, Bastion, VPN Gateway and similar services remain excluded unless later evidence establishes a need and their cost is approved. If a later design removes the public IP or makes the VM effectively private without another explicit egress path, outbound access must be redesigned and costed separately. Static Web Apps Free serves a static frontend only and does not eliminate API compute or API ingress.

## Runtime switches

Production baseline stays guarded: `ENVIRONMENT=production`, `DEBUG=false`, `DEMO_MODE=false`, `AUTO_CREATE_SCHEMA=false`, `REAL_MODELS_ENABLED=false`, `MODEL_ARTIFACT_ACTIVATION_ENABLED=false`. Do not alter repository defaults in Phase 4A. Keep both model switches off during infrastructure deployment and verification. Register 45 inactive candidate rows only after database and bundle checks; separately authorize and atomically activate them using the activation flag only in the dedicated activation process. Return that flag to false, then run a controlled dry run with real inference enabled only in its dedicated process. First persistent inference and scheduled EOD inference each require separate later approval after their preceding acceptance gates pass.

## Region and costs

Prefer Southeast Asia only after confirming B2als_v2/B2as_v2, Ubuntu image, PostgreSQL B1ms, storage, quota and capacity. East Asia is a candidate fallback, not an availability guarantee. The B2als_v2 observed retail compute reference is ~$34.46 per 730-hour month; B2as_v2 is ~$68.91; Standard IPv4 is ~$3.65. These are only a partial subtotal and exclude the required OS disk and PostgreSQL Private DNS zone, any PostgreSQL overage, optional Blob, egress, telemetry, public domain/DNS and taxes. The architecture is zero out-of-pocket only temporarily under verified student credit/spending protection; strict zero-consumption is not met.

References: [Azure size Bv1](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bv1-series), [Basv2](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/basv2-series), [Bpsv2](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bpsv2-series), [Azure default outbound access](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access), [Azure Public IP](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/virtual-network-public-ip-address).
