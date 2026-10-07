# Phase 4B Azure Infrastructure as Code

Phase 4B is a non-deploying IaC and validation phase. The templates model one future resource group and its infrastructure, but they must not be deployed in this phase. No command that creates Azure resources belongs in this runbook.

**East Asia is the selected Phase 4B validation target for this subscription.** `infra/parameters/phase4b.eastasia.bicepparam` is the current validation baseline. The root template requires an explicit `location`; it has no region default. Southeast Asia remains in the repository because it was the original Phase 4A candidate and is now proven policy-denied for this subscription. The Phase 4A recommendation was conditional and was not incorrect; Phase 4B established the account-specific policy restriction.

## Scope and deployment model

`main.bicep` targets subscription scope. It models the future resource group and invokes resource-group-scoped modules for network, compute, and PostgreSQL. Optional Blob Storage is in a conditional module and remains disabled in the East Asia baseline parameter file. Subscription-scope validation and What-If can preview the resource group and child resources without pre-creating the group.

Expected baseline inventory:

- One future resource group.
- One VNet with app and PostgreSQL delegated subnets, and one application NSG.
- One Standard static public IPv4, attached to one NIC.
- One Ubuntu 24.04 x86-64 VM with system-assigned identity and Standard SSD OS disk.
- One PostgreSQL Flexible Server B1ms candidate, private network access, PostgreSQL 16, 32 GiB storage target, HA and geo-redundant backup disabled.
- One required Azure Private DNS zone ending in `.postgres.database.azure.com`, plus one VNet link.
- No baseline storage account or Blob role assignment; optional Blob is enabled only by a future reviewed parameter change.

The VM public IP is the baseline's explicit inbound/outbound path. SSH is disabled by default; if a future authorized review enables it, an administrator CIDR is required. The NSG does not expose FastAPI port 8000 or PostgreSQL port 5432 to the Internet.

The VM administrative SSH identity is `psepulseops`. The separate `psepulse` identity is reserved for Phase 4D, which must create it as a dedicated non-root application/systemd service user without interactive administrative privileges. Phase 4B remains infrastructure-only and does not create or configure that service account.

## Parameters and secrets

The checked-in `.bicepparam` contains design values only. The administrator password is a secure Bicep parameter, and the SSH public key is supplied only by the local What-If script. That script generates an ephemeral keypair and dummy password under `/tmp/pse-pulse-phase4b`, writes a mode-0600 runtime parameter file, and removes key/password/parameter material on exit. Never add a production password, SSH key, connection string, subscription or tenant ID, SAS, storage key, or token to this repository.

## Local validation

Use the Phase 4B preflight script for read-only subscription, provider, location, VM SKU/quota, image, PostgreSQL SKU, and resource-group collision checks. Use `scripts/azure_phase4b_whatif.sh` only for Bicep lint/build, East Asia subscription validation, and East Asia subscription What-If. This is the accepted Phase 4B validation path. Its raw command output belongs in `/tmp/pse-pulse-phase4b/`, never in Git. The script stops if validation fails and does not continue into What-If.

The root Bicep compiles to an ARM template under `/tmp/pse-pulse-phase4b/`; generated JSON must not be stored in the repository.

## Approval boundary

The successful East Asia ARM validation and What-If are previews only. **No deployment is authorized.** This phase does not authorize resource creation, provider registration, role assignment execution, deployment, DNS changes, application installation, database migration, artifact upload/registration/activation, real inference, or EOD scheduling. In particular, do not run:

```text
az group create
az deployment sub create
az deployment group create
az provider register
```

Do not use `--confirm-with-what-if`, Terraform apply, or any Portal create action. A successful What-If is not a cost approval or deployment authorization. Phase 4C requires separate authorization and account-specific credit, quota, provider, price, and budget gates.
