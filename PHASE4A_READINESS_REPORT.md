# Phase 4A — Azure Deployment Readiness

**Repository:** `AlvinTubtub/pse-pulse-mmdc-project`
**Review date:** 2026-10-07 (Asia/Manila)
**Branch / HEAD:** `main` / `c02e7461dc104dc2a16d09b296e8e8288ce4cd8d`
**Outcome:** `PHASE 4A AZURE READINESS: CONDITIONAL_GO`

## Executive decision

The application can be represented by a small, single-VM design with PostgreSQL Flexible Server, but the full LIR + ARIMA + LSTM workload does **not** fit safely within the published 1 GiB Azure for Students VM sizes. The recommended starting compute is the credit-backed `Standard_B2als_v2` (2 vCPU, 4 GiB, x86-64), subject to account, regional SKU, quota, and Ubuntu-image confirmation. `Standard_B2as_v2` (2 vCPU, 8 GiB, x86-64) is the fallback when available and affordable.

An Azure Standard public IPv4 address is the simplest reviewed ingress for the single VM and is billed. The Student offer does not list it as an included allowance. The design can be **zero out-of-pocket temporarily** only if the exact subscription is an active Azure for Students subscription with sufficient remaining credit and its spending protection remains enabled. It is not strict zero-consumption, and the one-time credit does not support a year of continuous operation at the estimated rate. These subscription facts and all operational SKU/quota facts remain **REQUIRES PORTAL CONFIRMATION** because Azure CLI is unavailable and no subscription identity was obtained.

`CONDITIONAL_GO` means Phase 4B may draft Bicep and run read-only validation/`what-if` after its own authorization. It does not authorize resource creation. Do not proceed to a deployment until every condition in [Readiness gates](#readiness-gates) is resolved and a later phase explicitly authorizes creation.

## Required architecture summary

| Layer | Phase 4A target |
|---|---|
| Frontend | Existing Next.js static export served by Nginx on the VM; same-origin `/api` proxy avoids a separate frontend ingress and CORS path. |
| Ingress | **Gate A:** accept the cost of one Standard static public IPv4 address, with TCP 443 public and SSH restricted to a verified administrator source or disabled except for a separately approved access method. |
| Compute | Ubuntu 24.04 x86-64 on `Standard_B2als_v2`, 2 vCPU/4 GiB, credit-backed. Fallback `Standard_B2as_v2`, 2 vCPU/8 GiB. Availability and quota unverified. |
| API | FastAPI + Uvicorn managed by systemd; bind only to loopback behind Nginx. |
| Model runtime | Accepted immutable `2026.10.01-authoritative-v1` bundle; verified local cache; LIR, ARIMA, and CPU PyTorch LSTM inference sequentially; no training, refit, or TensorFlow. |
| Database | Azure Database for PostgreSQL Flexible Server, Burstable B1ms, 32 GiB data storage and at most 32 GiB backup allowance, private VNet access, required Azure Private DNS zone, TLS required, HA disabled. Entitlement/region/quota unverified. |
| Artifact storage | Local verified artifact cache is required at runtime. GPv2 Standard LRS Hot Blob is optional for versioned distribution; its small stored volume does not make VM delivery free, and transactions/egress can be billed. |
| Identity | System-assigned managed identity for Blob read access, scoped to the artifact container; no storage account key in app settings. |
| Scheduling | systemd EOD timer in `Asia/Manila`, enabled only after pipeline and market-data readiness are validated. No training/refit timer. |
| Monitoring | Journald with bounded retention and local health checks first; avoid paid Log Analytics/Application Insights until the free grant and cost are confirmed. |
| Security | Non-root service account, Nginx TLS, database private networking and TLS, restricted NSG, root-owned environment file, managed identity, no secrets in Git, deployment and activation switches default off. |
| Cost class | **ZERO OUT-OF-POCKET USING STUDENT CREDIT**, conditional on current offer, balance, and spend cap; never strict zero-consumption. |

This retains the intended single Linux VM, static frontend, API, all three model families, systemd scheduling, and managed PostgreSQL. It changes the prior small/free-VM assumption: full LSTM serving needs a credit-backed 4 GiB minimum. Blob is optional and public IPv4 is budgeted as a paid meter. This is an architecture recommendation only, not an implementation or resource deployment.

## Baseline and trust evidence

- Required local commit: `c02e7461dc104dc2a16d09b296e8e8288ce4cd8d` on `main`; working tree was clean at start.
- `az version` could not run because Azure CLI is not installed. It was not installed, and no login or token retrieval was attempted.
- No account/subscription metadata was available; there is no verified tenant, subscription state, selected subscription, credit balance, remaining-credit expiry, offer, or spending-limit state in this report.
- Accepted bundle: `2026.10.01-authoritative-v1`; manifest SHA-256 `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`.
- Phase 3B.2 bundle-validation SHA-256: `3ab0ca422605379c011374c0be8d5cb765c0d74ceb3a5e859d2efc98fca95129`.
- Phase 3B.3 activation-plan SHA-256: `26da93fe8da52cfca4cd026b8a4245c96d745d74eb46cce056680c062390f472`.
- Phase 3B.3 evaluation-receipt SHA-256: `aa3a6f63cd3ede5c831147d45245f91b2d956416582c9d9bff2b8794fdf1905c`.
- Phase 3B.4 receipt SHA-256: `d544d03ea90bb26afd06a08f14944917ecbe6735c5df7f569ea4a89a9de62295`.
- Accepted validation database SHA-256: `d65935ac9d865008ced7e49688446e44fe21750a0b1beec006c9c149aaafddbe`. Profiling ran against a temporary copy; the accepted external DB was not modified.

The current artifact directory measured approximately 51 MiB (the manifest alone is 106,439 bytes). The local inventory includes ancillary evidence alongside the immutable bundle, so a Phase 4B artifact upload must include only the manifest-listed production bundle files and must re-verify the recorded hashes.

## Subscription and entitlement findings

The public Azure for Students offer currently advertises a one-time $100 credit for 12 months and limited service allowances. Microsoft documents up to 750 hours/month for B1s, B2ats_v2, and B2pts_v2; its published PostgreSQL allowance describes B1ms compute plus 32 GB storage and 32 GB backup. These are **published offer facts, not proof of this user's entitlement**. The current balance, start/expiry, active subscription type, and spend cap are unknown. Consult [Azure for Students](https://azure.microsoft.com/en-us/free/students/), [Azure free-service rules](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/create-free-services), [Education Hub FAQ](https://learn.microsoft.com/en-us/azure/education-hub/faq), and [student cost tracking](https://learn.microsoft.com/en-us/azure/education-hub/navigate-costs).

| Service | Published student offer | This subscription | Cost while allowance applies | After/over allowance | Project decision |
|---|---|---|---|---|---|
| VM `Standard_B1s` | Up to 750 h/month, if the offer is active and meter/SKU eligible. | REQUIRES PORTAL CONFIRMATION; regional SKU and family quota unverified. | Potentially covered compute only; disk, public IP, egress and other meters are separate. SEA catalog compute reference: $0.0132/h, ~$9.64/730 h. | Retail compute applies; actual offer/billing unknown. | 1 vCPU/1 GiB does not pass measured all-family memory budget. Not suitable. |
| VM `Standard_B2ats_v2` | Up to 750 h/month, if eligible. | REQUIRES PORTAL CONFIRMATION; region and quota unverified. | Potentially covered compute only; additional resources billed separately. SEA catalog reference: $0.0118/h, ~$8.61/730 h. | Retail compute applies. | 2 vCPU/1 GiB x86-64; fails memory budget. Not suitable. |
| VM `Standard_B2pts_v2` | Up to 750 h/month, if eligible. | REQUIRES PORTAL CONFIRMATION; region and quota unverified. | Potentially covered compute only; additional resources billed separately. SEA catalog reference: $0.0106/h, ~$7.74/730 h. | Retail compute applies. | 2 vCPU/1 GiB ARM64; fails memory budget regardless of wheel availability. Not suitable. |
| VM `Standard_B2als_v2` | Not in the three published free VM sizes above. | Region, entitlement, quota and capacity unverified. | No included allowance established. SEA retail reference $0.0472/h, ~$34.46/730 h. | Student credit or other billing applies. | Primary candidate; 2 vCPU/4 GiB x86-64 meets estimated memory margin. Requires later approval. |
| VM `Standard_B2as_v2` | No published free allowance established. | Region, entitlement, quota and capacity unverified. | SEA retail reference $0.0944/h, ~$68.91/730 h. | Student credit or other billing applies. | 2 vCPU/8 GiB x86-64 fallback with more headroom. Requires later approval. |
| PostgreSQL Flexible Server B1ms | Published student allowance: up to 750 h/month plus 32 GB storage and 32 GB backup, subject to offer/region. | REQUIRES PORTAL CONFIRMATION; provider registration, region, quota and entitlement not checked. | May be covered only within exact offer limits. | SEA catalog references: compute ~$0.026/h; 32 GB data storage at ~$0.138/GB-month (~$4.42); backup beyond included quota may be billed. | Candidate for compact workload; private access, TLS, HA off. Validate version and limits before Phase 4B. |
| Blob GPv2 Standard LRS Hot | No student Blob allowance established in the offer reviewed. | Account/region/entitlement unverified. | No included free allowance assumed. A 50.7 MiB bundle is a tiny data-at-rest footprint, but still metered. | Storage, operations and transfer apply. | Optional; use only if versioned remote distribution is needed. |
| Standard static Public IPv4 | No included allowance established in the offer reviewed. | Region/SKU availability unverified. | No free amount assumed. SEA catalog reference $0.005/h (~$3.65/730 h). | Continues to consume credit/paid usage. | Chosen ingress gate; this is an explicit credit-consuming resource. |
| Azure Monitor / Log Analytics | Some services have free grants, but account-specific logs/retention and ingestion are not established here. | REQUIRES PORTAL CONFIRMATION. | No monthly bill assumed only if exact meter is within allowance. | Ingestion, retention, queries or alert integrations may bill. | Journald first; defer workspace until measured and budgeted. |

Prices are public Retail Prices API/catalog observations for Southeast Asia, Linux compute, on-demand, queried during this preflight and rounded for planning. They are not a quote, not a subscription price, exclude taxes/discounts and related resource meters, and do not establish SKU availability/capacity/quota. A 730-hour month is used only for comparison. East Asia catalog checks show B1s ~$0.0146/h, B2ats_v2 ~$0.0131/h, B2pts_v2 ~$0.0116/h, and B2as_v2 ~$0.105/h; exact B2als_v2/PG capacity still needs portal or CLI confirmation. Use the [Azure pricing calculator](https://azure.microsoft.com/en-us/pricing/calculator/) after the account/region is verified.

### Exact portal checks required

1. **Offer and balance:** Azure Portal → **Education Hub** → **Overview** (offer and credit balance/expiry); then **Subscriptions** → select the intended subscription → **Properties** (offer/name/state/tenant). Verify the subscription is still Azure for Students and its spending limit is on. Do not paste subscription secrets or tokens into Git or the report.
2. **Cost protection:** **Cost Management + Billing** → **Credits** / **Cost analysis** / **Budgets** as available; verify current credit and free-meter usage. The documented student spending limit can stop services after credits expire/exhaust, but budgets are alerts rather than hard caps. See [spending limits](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit).
3. **VM availability and quota:** subscription → **Usage + quotas** for the selected Southeast Asia region and the relevant B-family vCPU family; Azure **Help + support** → **Usage + quotas** if needed. Confirm B2als_v2, B2as_v2 and candidate Ubuntu 24.04 image. `az vm list-skus` and `az vm list-usage` are read-only checks for a later authorized preflight.
4. **PostgreSQL:** check the target region in the Flexible Server creation planning flow without submitting; verify B1ms, version, storage minimum, backup allowance, private networking mode, and quota. Do not create a server. Confirm `Microsoft.DBforPostgreSQL` registration state read-only; if unregistered, record **REGISTRATION REQUIRED IN LATER PHASE**.
5. **Storage and monitoring:** verify Storage account kind/replication and Azure Monitor/Log Analytics grants in the chosen region/subscription. Do not register providers or create test resources.

## Region and SKU assessment

Southeast Asia is the primary region candidate for Manila proximity and lower observed candidate compute prices. East Asia is a fallback only if all required resources and quotas are confirmed there and not in Southeast Asia. Public pricing/catalog entries show the VM meters exist in both regions; this does not prove regional allocation, capacity, student entitlement, quota, or server creation eligibility. Azure CLI is absent; no live account SKU, location, usage/quota, or provider registration query was performed. **Region decision: REQUIRES PORTAL CONFIRMATION.**

| Candidate | Published size facts | OS/architecture | Temporary storage / disk notes | Readiness |
|---|---|---|---|---|
| B1s | 1 vCPU, 1 GiB; up to 2 data disks; 320 uncached IOPS / 10 MB/s in published Bv1 table. | Linux x86-64 | 4 GiB temporary disk; do not put durable state there. | Free allowance may apply, but fails memory gate. |
| B2ats_v2 | 2 vCPU, 1 GiB. | Linux x86-64, AMD | No local temp disk; remote disk limits depend on size. | Free allowance may apply, but fails memory gate. |
| B2pts_v2 | 2 vCPU, 1 GiB. | Linux ARM64 | No local temp disk; remote disk limits depend on size. | Free allowance may apply, but fails memory gate. CPython 3.12 Linux ARM64 wheels were found for the checked dependency versions, including PyTorch CPU, but no Ubuntu ARM runtime was exercised; therefore it remains **NOT PREFERRED / UNPROVEN** for deployment. |
| B2als_v2 | 2 vCPU, 4 GiB. | Linux x86-64, AMD | No local temp disk; use managed OS disk for durable files. | Primary memory fit; availability/credit/quota unverified. |
| B2as_v2 | 2 vCPU, 8 GiB. | Linux x86-64, AMD | No local temp disk; use managed OS disk. | Fallback; availability/credit/quota unverified. |

Microsoft size references: [Bv1](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bv1-series), [Basv2](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/basv2-series), [Bpsv2](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bpsv2-series). For package wheels, see PyPI release files for [NumPy](https://pypi.org/project/numpy/2.5.3/), [pandas](https://pypi.org/project/pandas/3.0.6/), [scikit-learn](https://pypi.org/project/scikit-learn/1.9.1/), [statsmodels](https://pypi.org/project/statsmodels/0.15.0/), [joblib](https://pypi.org/project/joblib/1.6.0/), and [PyTorch](https://pypi.org/project/torch/2.14.1/). The reviewed CPython 3.12 Linux ARM64 wheels exist; this is not proof that the whole project installs and runs correctly on Azure ARM.

## Local production-runtime profile

The bounded profile loaded the accepted external bundle and performed actual inference without training. It used a temporary copy of the accepted validation DB; the accepted DB hash remained unchanged. The host was macOS Darwin ARM64, Python 3.12.13 ARM64, Torch 2.14.1, with 16 GiB physical memory. This is real application/model code on the developer host, but it is **not an Azure Ubuntu x86-64 or ARM64 target calibration**. All 15 LSTM models were processed sequentially, and the 45 model artifacts were not loaded simultaneously.

| Stage | Peak RSS | Steady RSS | Work time | Notes |
|---|---:|---:|---:|---|
| Python baseline | 14.2 MiB | 14.2 MiB | near 0 s | Measurement process. |
| FastAPI application import without Torch | 60.8 MiB | 60.8 MiB | 0.334 s | Torch remained unimported. |
| LIR artifact load + inference | 193.0 MiB | 193.0 MiB | 1.546 s | One representative symbol. |
| ARIMA artifact load + inference | 198.9 MiB | 198.9 MiB | 1.335 s | One representative symbol. |
| Torch import | 201.5 MiB | 201.5 MiB | 0.741 s | Torch 2.14.1. |
| One LSTM artifact load + inference | 353.4 MiB | 353.4 MiB | 2.001 s | One representative symbol. |
| Sequential all-15 LSTM inference | 352.9 MiB | 351.2 MiB | 3.127 s | Fifteen symbols in sequence. |
| Representative full service + dry-run child | 570.5 MiB process-tree peak | 193.9 MiB after child exit | ~7 s including bundle verification | 45 forecasts; DB forecast/artifact/pipeline-run counts each changed by 0. CPU averaged 78.3% of one core during the measured process interval. |

Planning memory budget for a 4 GiB VM: OS reserve 512 MiB + Nginx 32 MiB + Uvicorn/service reserve 128 MiB + measured representative peak 571 MiB = **1,243 MiB** estimated occupied; remaining **2,853 MiB (69.7%)**, above the 25% safety-margin floor and 30% preference. This is a planning estimate, not target-VM measurement. A 1 GiB VM would exceed its 768 MiB maximum occupied budget under the 25% rule even with the estimate before additional variance; B1s/B2ats_v2/B2pts_v2 therefore fail. `Standard_B2als_v2` is the minimum proposed all-family candidate, not yet authorized or deployed.

## Model, database, storage, and ingress gates

### VM and LSTM

**Decision:** `B. LSTM REQUIRES CREDIT-BACKED LARGER VM`. The total model-serving service tree peaked at ~571 MiB on the local host; even though LSTM is sequential, the OS and service reserves make 1 GiB candidates unsafe. Keep all three model families in scope on 4 GiB. If the account cannot support a B2als_v2 or B2as_v2 under its student credit, stop and ask for a separate LSTM-deferred architecture decision; do not silently switch to the 1 GiB free VM.

### PostgreSQL

Use Flexible Server B1ms as a candidate, with 32 GiB data and no more than the included 32 GiB backup amount if the offer applies. Require TLS. Prefer private VNet access using a delegated database subnet and private DNS, with the application VM in the same VNet; this avoids an internet-reachable database and does not require a Private Endpoint for this design. Keep HA off. Confirm B1ms availability, version, storage minimum, backup accounting, private access support, quota and entitlement in the portal. The public endpoint + VM-address firewall is simpler to configure but allows internet-routed connectivity and depends on a stable VM address; it is a fallback only if private access is unavailable and security review approves it. Microsoft references: [PostgreSQL free-account deployment](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/how-to-deploy-on-azure-free-account), [limits](https://learn.microsoft.com/en-us/azure/postgresql/configure-maintain/concepts-limits).

### Blob Storage

Keep the immutable verified bundle in a local read-only/controlled cache for serving; the 51 MiB bundle does not justify creating Blob solely to save meaningful disk space. Blob is optional for release distribution/rollback and should be GPv2 Standard LRS Hot if later approved. Use managed identity with container-scoped `Storage Blob Data Reader`. No account keys or long-lived SAS in environment files. Blob charge depends on capacity, operations, redundancy and transfer; check the [Blob pricing page](https://azure.microsoft.com/en-us/pricing/details/storage/blobs/) and calculator for current region meters. No exact subscription allowance or bill was verified, so classify all use as credit-consuming/potentially billable.

### Public ingress

**Decision:** `A. accept student-credit cost for Standard Public IPv4`. The selected Standard static public IPv4 is attached to the application VM/NIC and is the explicit inbound/outbound path for HTTPS and normal VM Internet connectivity. No NAT Gateway or other paid egress resource is included in the baseline. The public IP consumes credit at an observed SEA catalog reference of ~$0.005/hour (~$3.65 per 730-hour month), even when compute is within its free grant. Add optional public domain/DNS provider cost separately. If a future architecture removes the public IP or makes the VM effectively private without another explicit egress path, redesign and cost outbound connectivity separately. See [default outbound access](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access) and [Public IP addresses](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/virtual-network-public-ip-address).

Static Web Apps Free can serve a static frontend but does not remove the backend API's ingress, compute, memory or CORS/domain requirements. Container Apps has a consumption grant but continuous always-on CPU/memory exceeds its stated free monthly grant at representative minimum allocations; it changes the deployment shape and is not the recommended always-on host. See [Container Apps billing](https://learn.microsoft.com/en-us/azure/container-apps/billing) and [Static Web Apps plans](https://learn.microsoft.com/en-us/azure/static-web-apps/plans).

## Cost categories and zero-spend conclusion

| Resource | Category | Guardrail |
|---|---|---|
| B1s/B2ats_v2/B2pts_v2 compute | A only when exact eligible meter/time is verified | These SKUs are not suitable for all-family production serving. |
| PostgreSQL B1ms, 32 GiB storage and 32 GiB backup | A only within verified offer, region, time, size and backup limits | Growth/retention over allowance uses credit or other billing. HA is off. |
| ACA/SWA grants | A only within exact usage and eligibility limits | Not the chosen full production topology. |
| B2als_v2/B2as_v2 compute | B | ~$34.46 / ~$68.91 per 730 h in SEA retail catalog, respectively. |
| VM OS managed disk | B | Required; Standard SSD managed disks have a separate monthly meter. Choose the smallest supported disk only after checking exact region and price. No disk price is claimed as verified here. |
| Standard Public IPv4 | B | Required by selected ingress; ~$3.65/730 h catalog reference. The VM-attached public IP is the selected explicit inbound/outbound path; no NAT Gateway is included. |
| Azure Private DNS zone for PostgreSQL private access | B | Required for the selected PostgreSQL private-access topology; metered by hosted zone and DNS queries. No account/region price was verified; include it in the reviewed Phase 4B estimate. This is separate from optional public DNS/domain service. |
| Basic VNet, subnets and NSG | Required baseline; no direct charge assumed for basic resources | Associated traffic and networking services may have separate charges. |
| Blob capacity/transactions/egress | B or C if credit/PAYG is unavailable | Optional; count stored bytes, operations, network transfer and retention. |
| PostgreSQL over allowance | B, potentially C | Enforce storage/backup limits; no PAYG upgrade. |
| Public DNS/domain | Optional; B/C depending on provider and exact meter | Separate from required Azure Private DNS for PostgreSQL. Price/renewal must be reviewed. |
| NAT Gateway, Azure Firewall, Bastion, Load Balancer outbound rules, Private Endpoint, VPN Gateway | Excluded unless separately approved; B/C depending on meter | No NAT Gateway or other paid egress resource is included in the selected baseline. Re-design/cost outbound separately if the VM no longer has its attached public IP or becomes effectively private. |
| Paid monitoring workspace, additional snapshots, additional VM, GPU, AKS | Excluded unless separately approved; B/C | Not in the Phase 4A baseline. |
| Monitor/Log Analytics/Application Insights | A only within verified free grant; otherwise B/C | Start with bounded journald; do not enable paid ingestion by default. |
| Snapshots/backups beyond allowance, egress, marketplace images/support | B/C | Explicitly exclude unless costed and approved. |
| Managed identity, VNet, NSG | No direct charge for the basic resource itself | Associated compute, network processing, public IP, logs and data transfer may charge. |

The rough monthly **compute + public IPv4 subtotal** remains about $38.11 for B2als_v2 or $72.56 for B2as_v2. This is only a partial subtotal and excludes at least the OS disk, required PostgreSQL Private DNS zone, any PostgreSQL overage, optional Blob, egress, telemetry, public DNS/domain, and taxes. Do not infer a complete deployment monthly cost from it.

### Two distinct meanings of “$0”

- **STRICT ZERO-CONSUMPTION** means neither paid Azure usage nor student credit is consumed. This project does **not** meet that standard with full LSTM serving and public HTTPS ingress: the viable VM and Standard IPv4 both consume credit, and the complete active deployment cannot be claimed free.
- **ZERO OUT-OF-POCKET USING STUDENT CREDIT** can be temporary if the exact subscription has sufficient active credit and its spend limit remains enabled, and the user does not upgrade to Pay-As-You-Go or enable chargeable marketplace products. Exhaustion can stop the service. The rough monthly compute + public IPv4 subtotal is about $38.11 for B2als_v2 or $72.56 for B2as_v2, before the required OS disk and PostgreSQL Private DNS zone, database overages, optional Blob transactions, public DNS/domain, telemetry, egress and tax. $100 therefore does not support twelve months of continuous operation. Actual credit balance and billing controls require portal confirmation.

Do not write “$0” for any resource whose account-specific allowance has not been proven.

## Readiness gates

Before any Phase 4B creation proposal, verify and record:

1. Active Azure for Students subscription, current remaining credit and expiry, state, and spend limit ON; no PAYG upgrade.
2. Southeast Asia B2als_v2 and Ubuntu 24.04 x86-64 availability, student subscription quota/capacity, and current Linux price. If unavailable, verify the B2as_v2 fallback or stop.
3. PostgreSQL Flexible Server B1ms, region, B1ms quota, 32 GiB storage/backup offer, private networking, version and TLS support; HA off.
4. Standard static Public IPv4 price/availability; domain and DNS cost; confirm user accepts the recurring credit use.
5. Storage account/Blob choice and exact capacity, operations, identity role and egress costs; decide whether optional Blob is needed.
6. Confirm OS disk price, required Private DNS zone/query price, public IPv4 account price, monitoring/log retention, VM-attached outbound path, and every other meter in a reviewed monthly cost estimate.
7. On the selected target architecture, perform clean Linux deployment/package install and smoke tests in a later authorized phase. A local Mac ARM profile and public wheel metadata are not an Azure deployment test.
8. Explicit later approval for Phase 4B resource creation. This report grants none.

## Phase 4B infrastructure inventory (design only)

Preferred IaC is Bicep: native Azure declarations, reviewable parameters, and `az deployment group what-if` before any separately approved deployment. Phase 4B should initially create only draft IaC and safe scripts; the first operational command should be a read-only validation or `what-if`, never a create command.

Exact proposed inventory: one resource group; one VNet with app and PostgreSQL delegated subnets; NSG with public TCP 443 and restricted administrative access; one VM/NIC/managed OS disk; one Standard static public IPv4 on the VM NIC; one Flexible PostgreSQL server (B1ms, 32 GiB storage, 32 GiB backup allowance if applicable, private access, TLS, HA disabled); one required metered Azure Private DNS zone linked for PostgreSQL private access; optional GPv2 Standard LRS Hot Storage Account/container; one system-assigned VM identity and a container-scoped Blob Data Reader role assignment only if Blob is retained. Nginx, app deployment, systemd, and database migrations are later configuration/deployment work. Do not include NAT Gateway, Bastion, Firewall, Load Balancer, Private Endpoint, VPN Gateway, budgets/action groups, snapshots, paid telemetry, additional VMs, GPU, or AKS by default. Budget alerts may be designed later; no budget or action group was created in Phase 4A.

## Configuration and safety switches

| Name | Classification | Planned handling |
|---|---|---|
| `DATABASE_URL` | Sensitive secret | Root-managed environment file or later managed identity integration; never Git or report. |
| `ENVIRONMENT` | Public configuration | `production` only on the production host. |
| `DEBUG` | Public configuration | `false`. |
| `DEMO_MODE` | Public configuration | `false` in production. |
| `AUTO_CREATE_SCHEMA` | Public configuration | `false`; Alembic is authoritative. |
| `REAL_MODELS_ENABLED` | Runtime safety switch | Repository default remains `false`; enable scheduled inference only after acceptance. |
| `MODEL_ARTIFACT_ACTIVATION_ENABLED` | Runtime safety switch | Repository default remains `false`; only a controlled, explicit activation step may temporarily enable it. |
| `MODEL_ARTIFACTS_DIR`, bundle version, manifest hash | Public configuration / integrity identifier | Point at the verified immutable cache and record accepted version/hash. |
| Storage endpoint, container name | Public configuration / deployment-generated identifier | Use managed identity; never put storage credentials here. |
| Storage account key/SAS | Sensitive secret, avoid | Do not use account keys; short-lived read-only SAS only if identity is not available and separately approved. |
| Subscription, tenant, resource IDs, principal ID, server/account names | Deployment-generated identifiers | Keep generated IDs out of public logs; partially mask subscription/tenant in shared reports. |

Future production sequence (separate approvals are required for infrastructure creation, production artifact activation, first persistent inference, and scheduled production inference):

1. Deploy infrastructure with repository safety switches false.
2. Verify VM, network and PostgreSQL infrastructure.
3. Migrate only the specifically approved production database.
4. Seed canonical company and model metadata.
5. Bootstrap/import historical OHLCV and reconcile dates/counts.
6. Place/copy the accepted immutable bundle into the production artifact cache.
7. Verify bundle version, manifest SHA-256, every artifact SHA-256, metadata/provenance, and the expected 45 artifacts.
8. Register exactly 45 candidate `ModelArtifact` rows as **INACTIVE**.
9. Obtain separate authorization for controlled production artifact activation.
10. Set `MODEL_ARTIFACT_ACTIVATION_ENABLED=true` only in the dedicated activation process.
11. Atomically activate exactly the 45 candidate rows.
12. Verify 45 candidate rows, 45 active, 0 inactive, exactly one active lineage per company × model family, and no `Forecast` rows created by activation.
13. Return `MODEL_ARTIFACT_ACTIVATION_ENABLED=false`.
14. Run controlled production dry-run inference with `REAL_MODELS_ENABLED=true` only in that inference process. Active artifact lineage must already exist.
15. Require 15 companies, 45 predictions, exact active artifact lineage, Forecast delta 0, no training/refit, and activation flag false.
16. After dry-run acceptance, separately authorize the first persistent production inference.
17. Validate persisted forecasts, lineage, dates, idempotency and API visibility.
18. Only after production acceptance, separately authorize scheduled EOD inference.

Repository defaults remain `REAL_MODELS_ENABLED=false` and `MODEL_ARTIFACT_ACTIVATION_ENABLED=false` throughout. Permission to create infrastructure does not authorize artifact activation; activation does not authorize first persistent inference or scheduled inference. Phase 4A did none of these remote actions.

## Cost protection proposal (not created)

- Keep student spending protection ON; never upgrade to PAYG without a new explicit approval.
- Proposed email budget alert levels: $25 (25%), $50 (50%), $75 (75%), and $90 (90%) of the published $100 credit. These alerts are not hard caps and can lag.
- Check credit balance weekly and Azure Cost Analysis/service usage at least weekly during setup; inventory all resources daily during any future first deployment and weekly after stabilization.
- Tag planned resources with project, phase, owner and cost-center tags where supported; compare actual inventory to the approved Phase 4B list.
- Deallocate VM when it is not needed if intermittent service is acceptable; compute may stop billing but the managed disk, static public IP and other resources may continue to incur charges. A deallocated VM does not provide live service.
- Set log retention and local rotation before enabling centralized logs. Review PostgreSQL data, backup, and Blob growth monthly; alert/stop before exceeding included limits.
- Reconcile cost analysis and actual credit use against the reviewed estimate. On unexpected resources/meter usage, stop and deallocate/delete only under later explicit authorization; do not assume a budget blocks charges.

## No Azure deployment proof

Azure resources created: **0**
Azure resources modified: **0**
Azure resources deleted: **0**
Deployment commands executed: **0**
Model artifacts uploaded: **0**
Production DB migrations: **0**
Remote model activations: **0**

**NO AZURE RESOURCES WERE CREATED, MODIFIED, OR DEPLOYED.**

## Validation and recommendation

Documentation-only change. No tests, activation, inference, database migration, resource deployment, or Phase 3B.4 receipt regeneration was performed in this documentation turn. Minimum validation is `git diff --check`.

**RECOMMENDATION: READY FOR CHATGPT REVIEW BEFORE PHASE 4A COMMIT**
