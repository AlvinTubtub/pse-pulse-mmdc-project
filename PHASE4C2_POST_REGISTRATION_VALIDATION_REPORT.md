# Phase 4C.2 — Post-Registration Validation Report

## Gate

**PHASE 4C.2 VALIDATION GATE:**
**READY_FOR_SEPARATE_INFRASTRUCTURE_DEPLOYMENT_AUTHORIZATION**
**AZURE_INFRASTRUCTURE_NOT_DEPLOYED**

**DEPLOYMENT_CAPACITY_STATUS:**
**PRECHECK_PASS_CAPACITY_NOT_GUARANTEED**

This is a pre-deployment validation result only. It does **not** authorize infrastructure deployment. A separate owner authorization is required before Phase 4C.3 infrastructure deployment.

## Repository baseline

- Repository: `AlvinTubtub/pse-pulse-mmdc-project`
- Branch: `main`
- HEAD and `origin/main`: `4e8c536d8e191f158189f1d3997411b86648cf16`
- Parent Phase 4B IaC baseline: `c5baf980d9c15a8913e155cbb0769dda70dab017`
- Phase 4B implementation files remain unchanged.
- Final working tree: exactly the two requested Phase 4C.2 files are untracked; no staged or tracked changes.

## Accepted prior phases and subscription

- Phase 4C.0: closed; owner-confirmed billing evidence is carried forward.
- Phase 4C.1: `REQUIRED_PROVIDERS_REGISTERED / AZURE_INFRASTRUCTURE_NOT_DEPLOYED`.
- Subscription: `Azure for Students`, state `Enabled`, masked ID `2982c1f8-****-****-****-b4d8`.

The final successful validation used the owner's existing authenticated Azure CLI context. No Azure CLI token cache, authentication profile, or credential material was copied into the Phase 4C.2 evidence directory.

## Billing and cost guardrails carried forward

These owner-confirmed Phase 4C.0 values were not newly verified by Phase 4C.2:

- Student credit: `$100 / $100` at Phase 4C.0 confirmation; expiry `2027-08-14`.
- PAYG was not upgraded; no payment method was attached at that confirmation.
- Spending limit: `NOT DISPLAYED / NO STATE INFERRED`.
- Owner monthly budget: `APPROVED_AT_USD_75_PER_MONTH`.
- Azure Cost Management budget: `Monthly_ceiling_75_USD`, alert-only and not a hard spending cap.
- Gross fixed public-retail planning reference: `USD 70.63/month`.
- Allowance-adjusted fixed planning proxy: `USD 44.95/month`.
- PostgreSQL allowance evidence carried forward: B1ms compute 750 hours/month, 32 GB storage/month, and 32 GB LRS backup/month. These allowances do not guarantee realized $0 billing.
- `Standard_B2als_v2` is not a verified free VM SKU; its compute is expected to consume student credit.

## Provider states before validation

| Provider | State |
| --- | --- |
| Microsoft.Resources | Registered |
| Microsoft.Authorization | Registered |
| Microsoft.Network | Registered |
| Microsoft.Compute | Registered |
| Microsoft.DBforPostgreSQL | Registered |
| Microsoft.Storage | NotRegistered |

The target resource group `rg-pse-pulse-student-prod` was absent before validation (`false`).

## East Asia policy

The `sys.regionrestriction` assignment (`Allowed resource deployment regions`) explicitly allowed East Asia. The allowed locations were `australiaeast`, `centralindia`, `eastasia`, `japaneast`, and `koreacentral`.

## Authoritative East Asia VM quota

| Quota | Current | Limit | Remaining |
| --- | ---: | ---: | ---: |
| Total Regional vCPUs | 0 | 6 | 6 |
| Standard Basv2 Family vCPUs | 0 | 10 | 10 |
| Virtual Machines | 0 | 25,000 | 25,000 |

The primary VM requires 2 vCPU. Current SKU metadata identifies `Standard_B2als_v2` family as `standardBasv2Family`, mapping it to the `Standard Basv2 Family vCPUs` quota. Classification: `QUOTA_SUFFICIENT`.

## Primary VM

`Standard_B2als_v2` catalog results:

- East Asia supported: yes.
- Restrictions: `[]`.
- vCPU: 2; memory: 4 GiB; architecture: x64.
- Zones: 1, 2, 3.
- Family: `standardBasv2Family`.

Classification: `SKU_CATALOG_AVAILABLE`, `SUBSCRIPTION_RESTRICTIONS_NONE`. These results do not guarantee live physical allocation capacity.

## Fallback VM

`Standard_B2as_v2` catalog results:

- East Asia supported: yes.
- Restrictions: `[]`.
- vCPU: 2; memory: 8 GiB; architecture: x64.
- Zones: 1, 2, 3.
- Family: `standardBasv2Family`.

The fallback remains informational only and was not selected. It is not an automatic substitution.

## Ubuntu image

- Publisher: `Canonical`
- Offer: `ubuntu-24_04-lts`
- SKU: `server`
- Architecture: `x64`
- Latest listed version: `24.04.202609040`
- Committed IaC version selector: `latest`

## PostgreSQL B1ms

The East Asia Flexible Server capability listing reports `Standard_B1ms`, tier `Burstable`, 1 vCore, 2,048 MiB memory per vCore, 640 IOPS, and zones 1, 2, 3. No explicit restriction was reported (`status` and `reason` were null). PostgreSQL 16 is visible in the returned capability catalog and is set in the validated candidate. The response did not expose a B1ms-specific storage range.

## IaC integrity and SHA256 inventory

Static checks confirmed subscription scope, explicit East Asia, primary VM `Standard_B2als_v2`, `deployBlob=false`, `enableSsh=false`, VM administrator `psepulseops`, PostgreSQL administrator `psepulseadmin`, PostgreSQL `Standard_B1ms` version 16, private access, disabled HA and geo-backup, Standard static IPv4, HTTPS 443, no public 8000/5432 rule, and no unapproved baseline services. Optional storage remains conditional and disabled by the approved parameters. No Phase 4B IaC was changed.

| Committed candidate file | SHA256 |
| --- | --- |
| `infra/main.bicep` | `efa8a5e8e4571e4a0f60b50cc06f9444826a148392f297d0b508f893c7500009` |
| `infra/modules/network.bicep` | `f042280227dcc74dcb01d26ce0a5a4962f532c79e8509018916c3f3808242029` |
| `infra/modules/compute.bicep` | `459c7115b7a14f06b84003ad0d6f66871d6c4f80d69fa9b8506ea7beda24eec5` |
| `infra/modules/postgres.bicep` | `3f537ceaf6d4dac37cf091fbecb0daed7e22bc1c871549f04fe03202c178ce42` |
| `infra/modules/storage.bicep` | `b21facba372a409be125eab051d434c90b86a9dc0ea1612e0c54451a201745eb` |
| `infra/parameters/phase4b.eastasia.bicepparam` | `c99b776765938988698a917308fbd448d903afe4a7c961de33ff304fe1d9c29c` |

## Bicep build and temporary validation parameters

`az bicep build --file infra/main.bicep --stdout` succeeded with no warnings on stderr. Temporary validation parameters used an ephemeral SSH key pair and random PostgreSQL password, restricted to `/tmp/pse-pulse-phase4c2/` and removed at completion. The temporary parameter file and credentials were not committed.

## ARM subscription-scope validation

Result: `Succeeded`. The saved validation output contains two `NestedDeploymentShortCircuited` warnings because nested validation could not fully evaluate references. The successful final What-If expanded the expected resource set; no IaC change was made for the warnings.

## Final What-If and exact inventory

Status: `Succeeded`. Non-metadata rows: **9**. The parser excludes only `Microsoft.Resources/deployments` nested deployment metadata and enforces exact per-type counts, all rows `Create`, zero non-Create change types, zero unexpected types, zero Storage Accounts, and zero Role Assignments. Exact inventory negative tests: **13 passed**.

| Change type | Count |
| --- | ---: |
| Create | 9 |
| Modify | 0 |
| Delete | 0 |
| Ignore | 0 |
| NoEffect | 0 |
| NoChange | 0 |

| Predicted resource type | Count |
| --- | ---: |
| `Microsoft.Resources/resourceGroups` | 1 |
| `Microsoft.Network/networkSecurityGroups` | 1 |
| `Microsoft.Network/virtualNetworks` | 1 |
| `Microsoft.Network/publicIPAddresses` | 1 |
| `Microsoft.Network/networkInterfaces` | 1 |
| `Microsoft.Network/privateDnsZones` | 1 |
| `Microsoft.Network/privateDnsZones/virtualNetworkLinks` | 1 |
| `Microsoft.Compute/virtualMachines` | 1 |
| `Microsoft.DBforPostgreSQL/flexibleServers` | 1 |

Unexpected resource types: 0. Storage Accounts: 0. Role Assignments: 0. The resource-group Create is only a prediction; the resource group was not created.

## Security baseline

- Primary VM: `Standard_B2als_v2`.
- Ubuntu: Canonical `ubuntu-24_04-lts` / `server` / `latest`.
- OS disk: 32 GiB; `StandardSSD_LRS` is specified in committed IaC. The What-If payload shows disk size but omits managed storage type.
- Public IPv4: Standard, Static, IPv4.
- Inbound: Internet to TCP 443. No public inbound SSH, 8000, or 5432.
- PostgreSQL: `Standard_B1ms`, version 16, 32 GiB, public access Disabled, HA Disabled, geo-redundant backup Disabled, 7-day retention.
- PostgreSQL subnet delegation is present.
- Private DNS zone `private.postgres.database.azure.com` and VNet link are present; link registration is disabled.
- Blob deployment is disabled. Storage Account and role assignment are absent from What-If.

## Cost-model drift

No additional resource type appeared in What-If. `COST_MODEL_DRIFT: NONE_DETECTED`. The monthly figures above are planning references, not a guaranteed bill.

## Post-What-If state

| Provider / resource group | State |
| --- | --- |
| Microsoft.Network | Registered |
| Microsoft.Compute | Registered |
| Microsoft.DBforPostgreSQL | Registered |
| Microsoft.Storage | NotRegistered |
| `rg-pse-pulse-student-prod` exists | `false` |

## Azure mutation accounting

| Operation | Count |
| --- | ---: |
| Provider registrations | 0 |
| Provider unregistrations | 0 |
| Resource groups created | 0 |
| Infrastructure resources created | 0 |
| Infrastructure resources modified | 0 |
| Infrastructure resources deleted | 0 |
| Policy changes | 0 |
| Role assignments | 0 |
| Deployment create commands | 0 |
| Quota changes | 0 |
| Microsoft.Storage registrations | 0 |
| Budget changes | 0 |
| Application deployments | 0 |
| Artifact uploads | 0 |
| Production DB migrations | 0 |
| Model registrations/activations | 0 |
| Production inference | 0 |
| Scheduling changes | 0 |
| ARM validations | 1 |
| What-If operations | 1 |

**NO AZURE INFRASTRUCTURE RESOURCES WERE CREATED, MODIFIED, OR DEPLOYED.**

## Recommendation

**RECOMMENDATION:** `READY FOR CHATGPT FINAL REVIEW BEFORE PHASE 4C.2 COMMIT`

A separate owner authorization is required before Phase 4C.3 infrastructure deployment.
