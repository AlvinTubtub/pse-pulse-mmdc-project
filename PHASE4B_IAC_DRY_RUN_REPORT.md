# Phase 4B IaC and deployment dry-run report

## Gate

**PHASE 4B IAC GATE:**

```text
IAC_WHATIF_VALIDATED
AZURE_NOT_DEPLOYED
```

The Bicep templates lint and build locally. Southeast Asia is denied by the subscription's allowed-region policy. East Asia is explicitly allowed, meets the requested image and SKU catalog checks, and passed subscription ARM validation and What-If. This is not a deployment authorization. Phase 4C needs separate authorization and its own account, cost, quota, and provider gates.

## Repository baseline and files

- Branch: `main`
- Starting and final HEAD: `4078b6161801a73a5266ee80dcc0470d979a8cb0`
- Expected baseline: confirmed; no tracked application or model files changed.
- Phase 3 trust anchors retained unchanged:
  - Bundle version: `2026.10.01-authoritative-v1`
  - Manifest SHA-256: `4225e60044f000b16147e01f6ff165968523c1efd9647e57d9c7a6f5f5a27454`
  - Phase 3B.2 bundle-validation SHA: `3ab0ca422605379c011374c0be8d5cb765c0d74ceb3a5e859d2efc98fca95129`
  - Phase 3B.3 activation-plan SHA: `26da93fe8da52cfca4cd026b8a4245c96d745d74eb46cce056680c062390f472`
  - Phase 3B.3 evaluation-receipt SHA: `aa3a6f63cd3ede5c831147d45245f91b2d956416582c9d9bff2b8794fdf1905c`
  - Phase 3B.4 receipt SHA: `d544d03ea90bb26afd06a08f14944917ecbe6735c5df7f569ea4a89a9de62295`
  - Validation DB SHA: `d65935ac9d865008ced7e49688446e44fe21750a0b1beec006c9c149aaafddbe`

Phase 4B files (all remain untracked):

- `PHASE4B_IAC_DRY_RUN_REPORT.md`
- `infra/main.bicep`
- `infra/README.md`
- `infra/modules/network.bicep`
- `infra/modules/compute.bicep`
- `infra/modules/postgres.bicep`
- `infra/modules/storage.bicep`
- `infra/parameters/phase4b.southeastasia.bicepparam`
- `infra/parameters/phase4b.eastasia.bicepparam`
- `scripts/azure_phase4b_preflight.sh`
- `scripts/azure_phase4b_whatif.sh`
- `backend/tests/test_phase4b_iac_safety.py`

## Local toolchain and tests

- Azure CLI: `2.91.0`
- Bicep CLI: `0.48.1`
- Root Bicep lint: passed.
- Root Bicep build: passed to `/tmp/pse-pulse-phase4b/main.json`.
- All four module lint/build checks: passed; generated JSON is under `/tmp`.
- Phase 4B safety tests: `7 passed`.
- Backend regression: `288 passed, 1 skipped`; this included the existing CPU LSTM test set.
- Frontend: `npm ci` passed; lint, TypeScript check, and production build passed; `npm audit --omit=dev` reported `0 vulnerabilities`.

## Reproducibility correction

- The checked-in What-If script now targets `eastasia` and reads `infra/parameters/phase4b.eastasia.bicepparam`; the parameter path is passed into runtime parameter generation rather than duplicated.
- Both scripts now require the Phase 4A commit to be an ancestor of `HEAD`, while retaining the `main` branch and clean tracked/staged tree checks. This remains valid after a Phase 4B commit.
- The root Bicep `location` parameter is required and has no default region.
- Safety tests use East Asia as the baseline and check both East Asia and historical Southeast Asia parameter files.
- The corrected What-If script checks the accepted resource inventory, change types, zero deletes/modifies, and absence of Storage/role assignments. Storage provider registration is reported as optional while `deployBlob=false`.

## Azure account and read-only preflight

- Subscription: Azure for Students; state `Enabled`; masked ID `2982c1f8-****-****-****-********b4d8`.
- Azure CLI did not establish remaining credit, credit expiry, spending protection, or no-PAYG-upgrade status. Those deployment gates remain `REQUIRES_PORTAL_CONFIRMATION`.
- `az account list-locations` listed both `southeastasia` and `eastasia`. Policy permission is established separately below; the location list alone is not policy evidence.
- Provider states:

| Provider | State |
| --- | --- |
| Microsoft.Resources | Registered |
| Microsoft.Network | NotRegistered |
| Microsoft.Compute | NotRegistered |
| Microsoft.DBforPostgreSQL | NotRegistered |
| Microsoft.Storage | NotRegistered (optional while `deployBlob=false`) |
| Microsoft.Authorization | Registered |

Required baseline providers are Microsoft.Network, Microsoft.Compute, and Microsoft.DBforPostgreSQL. Microsoft.Storage is optional while `deployBlob=false`. The three required providers are not registered; no provider was registered during Phase 4B.

```text
PROVIDER_REGISTRATION_BLOCKED_FOR_LATER_AUTHORIZATION
```

Provider registration was not a blocker to East Asia ARM validation or What-If in this subscription. It remains a required later deployment prerequisite.

### Azure Policy diagnosis

The failed Southeast Asia ARM validation returned outer `InvalidTemplateDeployment` and inner `RequestDisallowedByAzure` errors for:

- `nsg-psepulse-app` — `Microsoft.Network/networkSecurityGroups`
- the application VNet — `Microsoft.Network/virtualNetworks`
- `pip-psepulse-app` — `Microsoft.Network/publicIPAddresses`
- `nic-psepulse-app` — `Microsoft.Network/networkInterfaces`

The denial message did not include a policy ID or location value. The denied location is `southeastasia`, from the validation parameters; it is absent from the assignment's allowed list.

Read-only `az policy assignment list --disable-scope-strict-match true` returned one applicable assignment at subscription scope and no parent-scope assignment:

- Assignment: `sys.regionrestriction` — **Allowed resource deployment regions**
- Sanitized assignment ID: `/subscriptions/<MASKED>/providers/Microsoft.Authorization/policyAssignments/sys.regionrestriction`
- Definition: **Allowed resource deployment regions**, built-in, Indexed, version `1.0.0`
- Definition ID: `/providers/Microsoft.Authorization/policyDefinitions/b86dabb9-b578-4d7b-b842-3b45e95769a1`
- Effect: `deny` when a resource location is outside `listOfAllowedLocations` (with the definition's global-location and B2C exceptions).
- No policy set/initiative ID was assigned.
- Exact `listOfAllowedLocations`: `koreacentral`, `australiaeast`, `centralindia`, `eastasia`, `japaneast`.

```text
POLICY_ALLOWED_REGIONS:
koreacentral, australiaeast, centralindia, eastasia, japaneast
```

| Region | Policy status | Evidence |
| --- | --- | --- |
| Southeast Asia (`southeastasia`) | `POLICY_DENIED_FOR_THIS_SUBSCRIPTION` | Excluded from the assignment allow-list; validation returned `RequestDisallowedByAzure`. |
| East Asia (`eastasia`) | `POLICY_ALLOWED=true` | Explicitly present in the assignment allow-list. East Asia ARM validation and What-If succeeded. |

### Policy-allowed region shortlist

East Asia was screened first because it is the Phase 4A fallback and is a geographically reasonable choice for the Philippines. It met the policy, VM SKU, image, PostgreSQL SKU, and architecture criteria. Phase 4A's conditional East Asia fallback was not wrong; this Phase 4B policy assignment provided account-specific evidence that was unavailable to the earlier readiness check. The remaining allowed locations are documented candidates, not confirmed alternatives; they were not probed after East Asia met the validation criteria. No current cost comparison was performed.

| Priority | Region | Evidence/status |
| --- | --- | --- |
| 1 | `eastasia` | Policy allowed; both VM SKUs, Ubuntu image, and PostgreSQL B1ms verified; ARM validation and What-If succeeded. Quota unresolved. |
| 2 | `japaneast` | Policy allowed; technical SKUs, image, PostgreSQL, quota, and cost not checked. |
| 3 | `koreacentral` | Policy allowed; technical SKUs, image, PostgreSQL, quota, and cost not checked. |
| 4 | `centralindia` | Policy allowed; technical SKUs, image, PostgreSQL, quota, and cost not checked. |
| 5 | `australiaeast` | Policy allowed; technical SKUs, image, PostgreSQL, quota, and cost not checked. |

No other alternative region is confirmed viable. No architecture or security change was needed for East Asia.

East Asia is the selected Phase 4B validation region. The Southeast Asia parameter file remains and is marked policy-denied by this report; the East Asia parameter file changes only `location` and preserves the accepted baseline settings.

### Compute, image, and database findings

- `az vm list-skus` timed out, so a narrow read-only Compute SKU ARM REST query was used for East Asia. `Standard_B2als_v2` and `Standard_B2as_v2` were both returned with `locations: [eastasia]`, `restrictions: []`, and availability zones 1, 2, and 3. No restriction reason was returned. This establishes catalog support, not allocated capacity.
- `az vm list-usage` returned no rows. With `Microsoft.Compute=NotRegistered`, quota status is `VM_QUOTA_UNRESOLVED_PROVIDER_NOT_REGISTERED`; no quota increase was requested.
- Canonical Ubuntu 24.04 x86-64 image was found in East Asia: publisher `Canonical`, offer `ubuntu-24_04-lts`, SKU `server`, version `24.04.202508010`; image metadata reports architecture `x64`. The East Asia parameter file uses this publisher/offer/SKU contract with version `latest`.
- PostgreSQL Flexible Server `Standard_B1ms` appears in the East Asia Burstable catalog with no status/reason restriction reported, 1 vCore, 2048 MB memory per vCore, and 640 IOPS. Storage limits were not exposed. The SKU response establishes catalog presence, not subscription entitlement or provisioning capacity.
- PostgreSQL major version is pinned to `16`, a currently supported standard major and the repository has no stricter major requirement.
- Future resource group `rg-pse-pulse-student-prod` does not exist (`false`).

### Region and fallback decision

Southeast Asia was not retried after the policy denial. East Asia was selected under the Phase 4A fallback after explicit policy permission, both VM SKU catalogs, the x64 Ubuntu image, PostgreSQL B1ms, and the nonexistence of the target resource group were confirmed. Quota remains an unresolved later gate due to provider state.

## IaC review and expected inventory

The subscription-scope root models one future resource group and resource-group-scoped network, compute, and PostgreSQL modules. PostgreSQL uses private VNet integration, the delegated subnet and linked Private DNS zone, and disabled public access. The VM uses SSH keys only, has password authentication disabled, and the baseline NSG allows TCP 443 while SSH is disabled. No FastAPI or PostgreSQL port is exposed to the Internet.

**Identity separation:** The VM administrative identity is `psepulseops`. `psepulse` is reserved for the future non-root application/systemd service account, preserving the Phase 4A privilege separation requirement. Phase 4B does not create or configure that service user.

Optional Blob Storage is modeled with `deployBlob = false` in the baseline. When enabled in a later reviewed phase, its role assignment is scoped to the artifact container and grants Storage Blob Data Reader.

The East Asia What-If returned these **9 Create predictions**:

- `Microsoft.Resources/resourceGroups` (1)
- `Microsoft.Network/networkSecurityGroups`
- `Microsoft.Network/virtualNetworks`
- `Microsoft.Network/publicIPAddresses`
- `Microsoft.Network/networkInterfaces`
- `Microsoft.Network/privateDnsZones`
- `Microsoft.Network/privateDnsZones/virtualNetworkLinks`
- `Microsoft.Compute/virtualMachines`
- `Microsoft.DBforPostgreSQL/flexibleServers`

The output contained one resource of each type above. Resource deployment bookkeeping was not included in `ResourceIdOnly` output. Baseline Storage and Blob role assignment were absent. Unexpected resource types: `0`; Delete predictions: `0`; existing-resource Modify predictions: `0`.

## ARM validation, What-If, and safety boundary

- Southeast Asia subscription ARM validation: blocked by the policy assignment (`RequestDisallowedByAzure`); Southeast Asia was not retried after diagnosis.
- East Asia subscription ARM validation: succeeded (`provisioningState: Succeeded`) despite provider registration states.
- East Asia subscription What-If: succeeded (`Succeeded`) after validation passed, using `--result-format ResourceIdOnly --no-pretty-print`.
- The corrected checked-in preflight and What-If scripts were rerun. Preflight completed, and the corrected What-If script validated and summarized the same nine approved Create predictions with zero Deletes, Modifies, unexpected resource types, Storage Accounts, or role assignments.
- Latest sanitized summary and raw validation/What-If output are under `/tmp/pse-pulse-phase4b/run.jRqMjZ/`; no raw output was added to Git.
- What-If used temporary SSH and dummy database credentials under `/tmp`; secret/key material was removed at exit. No real credentials were used or committed.
- Azure resources created: `0`
- Azure resources modified: `0`
- Azure resources deleted: `0`
- Provider registrations performed: `0`
- Policy changes/exemptions performed: `0`
- Role assignments performed: `0`
- Deployment create commands executed: `0`
- Quota changes requested: `0`
- Model artifacts uploaded: `0`
- Production database migrations: `0`
- Remote model activations: `0`
- Production inference runs: `0`

**NO AZURE RESOURCES WERE CREATED, MODIFIED, OR DEPLOYED.**

## Deployment gates still open

Before any later resource creation, confirm the Azure for Students offer and remaining credit/expiry, spending protection and no-PAYG-upgrade status, exact current prices for each billable service, regional VM capacity and quota, required provider registration, and an accepted monthly budget. Phase 4B does not authorize deployment, provider registration, database migration, application deployment, artifact upload/activation, inference, or scheduling.
