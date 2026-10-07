# Azure Deployment Runbook — Phase 4A Design

This is a future runbook outline. Phase 4A performed no Azure login, resource operation, deployment, migration, upload, or activation. Do not execute resource-creation steps until a later phase explicitly approves them. See the [readiness report](../PHASE4A_READINESS_REPORT.md) for unresolved subscription and region gates.

## Read-only account gate

Before authoring deploy parameters, confirm in Azure Portal:

1. Education Hub → Overview: Azure for Students offer, remaining credit, expiry, and spend protection.
2. Subscription → Properties: selected subscription, offer, state, and tenant. Keep IDs partially masked in shared records.
3. Cost Management + Billing: available credit, current usage, and no Pay-As-You-Go upgrade.
4. Subscription → Usage + quotas: B-family quota and region; confirm B2als_v2 and Ubuntu 24.04 x86-64. Confirm PostgreSQL B1ms quota and provider state. Provider registration is a later mutation; if absent, record `REGISTRATION REQUIRED IN LATER PHASE`.
5. Confirm Southeast Asia first, then East Asia fallback, for compute, image, PostgreSQL, storage, capacity, student meters, and every required quota. A price listing is not proof of capacity or eligibility.

Azure CLI was unavailable during Phase 4A. It was not installed. A later explicitly authorized read-only account preflight may use `az account show`, `az account list`, `az account list-locations`, `az vm list-skus`, `az vm list-usage`, `az provider show`, and `az resource list`. Never print tokens, secrets, connection strings, or unmasked account identifiers. Do not run deployment, create, delete, update, or provider-registration commands during a read-only check.

## Phase 4B IaC design

Use Bicep with parameters for region, approved SKU, app/database subnet ranges, image, OS disk, and optional artifact Storage. Keep secrets out of parameters, source control, terminal history, and deployment outputs. Use Key Vault only after its own cost/identity design is approved; do not add it automatically.

Draft this exact inventory for review:

- Resource group.
- One VNet with app subnet and delegated PostgreSQL subnet, NSG, and a **required metered Azure Private DNS zone** linked for PostgreSQL private access. Include hosted-zone and query charges in the Phase 4B monthly estimate; this is separate from optional public DNS/domain.
- One Linux VM (primary `Standard_B2als_v2`, fallback `Standard_B2as_v2`), NIC, smallest suitable managed OS disk, and Standard static public IPv4 for HTTPS.
- PostgreSQL Flexible Server B1ms candidate, private VNet access, TLS, 32 GiB data and 32 GiB backup allowance if confirmed, HA disabled.
- Optional GPv2 Standard LRS Hot Storage Account/container for artifact distribution.
- System-assigned managed identity on VM; container-scoped `Storage Blob Data Reader` role only if Blob is approved.
- Nginx and app/systemd configuration as separate, reviewed guest configuration; no Azure resource extension unless explicitly included and priced.

The VM's attached Standard static public IPv4 is the selected explicit inbound/outbound path for HTTPS and normal VM Internet connectivity. No NAT Gateway is included in the approved baseline. Keep NAT Gateway, Azure Firewall, Load Balancer outbound rules, Bastion, Private Endpoint, VPN Gateway, budget/action groups, additional snapshots, and paid log workspace excluded unless later evidence proves they are needed and a separate costed design is approved. If a future design removes the VM public IP or makes it effectively private without another explicit egress path, redesign and price outbound connectivity separately. The required PostgreSQL Private DNS zone is part of the baseline and must be costed.

Phase 4B must create draft IaC and deployment scripts only. Run formatting/static checks and `az deployment group what-if` with the approved target scope before any creation request. A `what-if` is a preview, not authorization to deploy. Do not run a deployment command until a separate approval identifies the exact subscription, resource group, region, resource inventory, and cost limit.

## Later production sequence (not executed)

Four independent approvals are required: infrastructure creation, production artifact activation, first persistent production inference, and scheduled production inference.

1. Approve exact subscription, region, full cost estimate (including OS disk and PostgreSQL Private DNS), quota and resource inventory.
2. Review Bicep and `what-if`; ensure no unapproved resource changes. Create infrastructure only under a later explicit authorization.
3. Deploy infrastructure with repository safety switches false; verify VM, network and PostgreSQL.
4. Migrate only the specifically approved production database.
5. Seed canonical company/model metadata.
6. Bootstrap/import historical OHLCV and reconcile dates/counts.
7. Place/copy the accepted `2026.10.01-authoritative-v1` immutable bundle into the production artifact cache. Verify bundle version, manifest SHA-256, every artifact SHA-256, metadata/provenance, and exactly 45 artifacts.
8. Register exactly 45 candidate `ModelArtifact` rows **INACTIVE**.
9. Obtain separate authorization for controlled production activation.
10. Set `MODEL_ARTIFACT_ACTIVATION_ENABLED=true` only in the dedicated activation process.
11. Atomically activate exactly 45 candidate rows.
12. Verify 45 candidate rows, 45 active, 0 inactive, one active lineage per company × model family, and no `Forecast` rows created by activation.
13. Return `MODEL_ARTIFACT_ACTIVATION_ENABLED=false`.
14. Run controlled production dry-run inference with `REAL_MODELS_ENABLED=true` only in that inference process; active artifact lineage must already exist. Require 15 companies, 45 predictions, exact active lineage, Forecast delta 0, no training/refit, and activation flag false.
15. After dry-run acceptance, separately authorize first persistent production inference.
16. Validate persisted forecasts, lineage, dates, idempotency and API visibility.
17. Only after production acceptance, separately authorize scheduled EOD inference.

Repository defaults remain `REAL_MODELS_ENABLED=false` and `MODEL_ARTIFACT_ACTIVATION_ENABLED=false` throughout. Approval to create infrastructure does not grant permission to activate artifacts, and activation approval does not grant permission for persistent or scheduled inference.

## Environment and secret classification

| Variable / value | Type | Handling |
|---|---|---|
| `DATABASE_URL` | Sensitive secret | Protected root-owned environment file or later approved managed-identity auth. Never Git/logs. |
| `ENVIRONMENT=production` | Public configuration | Production service setting. |
| `DEBUG=false` | Public configuration | Must remain false. |
| `DEMO_MODE=false` | Public configuration | No demo seed in production. |
| `AUTO_CREATE_SCHEMA=false` | Public configuration | Migrations remain explicit/Alembic-controlled. |
| `REAL_MODELS_ENABLED=false` | Runtime safety switch | Do not enable until acceptance and explicit authorization. |
| `MODEL_ARTIFACT_ACTIVATION_ENABLED=false` | Runtime safety switch | Keep repository default false; set true only in the dedicated activation process after separate approval, then return it to false. |
| `MODEL_ARTIFACTS_DIR`, bundle version, manifest SHA | Public configuration/integrity metadata | Point only at verified, immutable cache. |
| Storage endpoint/container | Public configuration/deployment-generated identifiers | Use VM managed identity; no credential value. |
| SAS or PostgreSQL password | Sensitive secret | Avoid SAS; if needed use short expiry/read-only. Never store in Git. |
| Subscription/resource/tenant/principal/server IDs | Deployment-generated identifiers | Keep in protected deployment records; mask when shared. |

## Future stop conditions

Stop before any deployment if the student offer/credit/spend limit is not confirmed, the B2als_v2 or B2as_v2 quota/region is unavailable, the VM plus public IP exceeds the accepted credit budget, PostgreSQL free entitlement/private networking/required Private DNS cost is unavailable, the required OS disk or another meter is unpriced, the exact artifact hashes do not match, or any reviewed `what-if` shows an unapproved resource. The VM-attached public IP is the current explicit egress path; if it is removed or the VM becomes effectively private, stop and cost an alternate route. Ask for a new architecture/cost decision instead of switching silently to a 1 GiB VM or a paid networking option.

**Phase 4A resource/deployment counts:** created 0; modified 0; deleted 0; deployment commands 0; artifact uploads 0; production migrations 0; remote activations 0.

**NO AZURE RESOURCES WERE CREATED, MODIFIED, OR DEPLOYED.**
