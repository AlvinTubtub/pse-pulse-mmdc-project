# Phase 4C.3 Gate A — Deployment Readiness Report

## Gate classification

**PHASE 4C.3 GATE A:** `NO_GO_BILLING_SAFETY`

**PHASE 4C.3 GATE B:** `NO_GO_BILLING_SAFETY` / `NO_GO_POSTGRES_CAPABILITY_INDETERMINATE`

**POSTGRESQL CAPABILITY:** `INDETERMINATE`

**TECHNICAL PREFLIGHT:** `PRIOR_RECORDED_PASS`

`WHAT-IF RAW EVIDENCE UNAVAILABLE FOR REVALIDATION`

No Azure operations were run for this PostgreSQL classification correction. The prior What-If raw response remains unavailable for revalidation against the strict NSG parser. The saved PostgreSQL capability response was available for this diagnosis and is summarized below.

**AZURE_INFRASTRUCTURE_NOT_DEPLOYED**

**OWNER_DEPLOYMENT_AUTHORIZATION:** `NOT_GRANTED`

Gate A preparation does not authorize Gate B. The preparation script has no resource-provisioning mode. Fresh financial eligibility confirmation and a separate owner decision are still required.

## Scope and repository baseline

- Repository: `AlvinTubtub/pse-pulse-mmdc-project`
- Branch: `main`
- Accepted previous baseline: `075e30834bf6b1e9b0f2088b66f40850966cc6c2`
- Current implementation baseline: `f1f9b302a335b5d92c855d6da9205d5555c6910c`
- No infrastructure-as-code files were modified.
- Phase 4B and Phase 4C.2 infrastructure files remain at their accepted content and hashes.
- The accepted Gate A deliverables are the report, preparation-only preflight script, and owner checklist. This correction also adds a focused offline regression test.
- This correction modifies exactly two tracked files and adds one new test file. The staging area is empty.

The former Phase 4C.3 provisioning runner had a guarded executable deployment path. It has been removed from the final deliverables. The replacement supports only `--prepare` and `--help`; other arguments fail before any Azure command. Its command wrapper permits read-only queries, local Bicep compilation, subscription-scope validation, and What-If only.

## Final validation hardening

- The existing Azure subscription is identified by both its masked display form and the SHA256 digest of the complete `az account show` subscription ID. The digest is calculated over the ID bytes without a newline; only the masked ID is printed. An offline negative test confirmed a different ID with the same first eight and last four characters is rejected.
- Before ARM validation, the preparation flow runs `az bicep build --file infra/main.bicep --stdout` and captures its output in the owner-only evidence directory. A mocked build failure stops with `NO_GO_IAC_COMPILE` before ARM validation. The build was not executed during this correction.
- PostgreSQL capability evidence is classified as `AVAILABLE`, `EXPLICITLY_RESTRICTED`, or `INDETERMINATE`. `AVAILABLE` requires location status `Available`, the exact `Burstable` tier, `Standard_B1ms` SKU, PostgreSQL major version `16`, explicit `Available` status for each, and `restricted=Disabled`. Location or target capability status `Disabled`, `restricted=Enabled`, or a nonempty provider reason is `EXPLICITLY_RESTRICTED`. Location status `Visible`, `Default`, null, or absent; target status `Visible`, `Default`, null, or absent; missing target entries; an unspecified location restriction; or a conflicting explicit region identifier is `INDETERMINATE`. Neither non-available classification proceeds to ARM validation or What-If. ([Microsoft Learn: Capabilities By Location](https://learn.microsoft.com/en-us/rest/api/postgresql/capabilities-by-location/execute?view=rest-postgresql-2024-08-01))
- `Standard_B2als_v2` remains the only primary VM readiness gate. `Standard_B2as_v2` is summarized as informational availability/restriction data; its absence or restriction does not fail the primary gate and does not trigger substitution.
- The What-If response must contain at least one explicit success field: top-level `status` or `properties.provisioningState`. If both are present, both must be `Succeeded`; missing both or any failure value is rejected.
- Inventory validation rejects rows lacking a usable type and resource ID, enforces the approved subscription and resource group/location, and verifies that the private DNS link references the planned VNet.

These controls were validated offline with mocks and fixtures only. They do not represent a fresh Azure preflight.

## Evidence provenance and limitation

The previous Phase 4C.3 run returned a successful preparation summary. Its recorded results were:

- Subscription: Azure for Students, Enabled; masked ID `2982c1f8-****-****-****-b4d8`.
- Required providers Registered; Microsoft.Storage NotRegistered.
- Target resource group absent before and after What-If.
- East Asia policy allowed the region.
- Regional vCPU quota: 0 of 6 used, 6 remaining; Basv2-family: 0 of 10 used, 10 remaining; VM count: 0 of 25,000 used.
- Primary `Standard_B2als_v2`: East Asia listed, no restrictions, `standardBasv2Family`, 2 vCPU, 4 GiB, x64. Informational fallback `Standard_B2as_v2`: listed with no restrictions.
- Canonical Ubuntu 24.04 x64 image visible; latest recorded catalog version `24.04.202609040`.
- PostgreSQL catalog listed `Standard_B1ms` under Burstable and listed PostgreSQL 16. The earlier word “visible” referred to catalog listing, not an API `Visible` status; the saved response has `null` status fields as detailed below.
- Bicep build and ARM subscription-scope validation succeeded.
- What-If returned 9 creates, 0 Modify, 0 Delete, 0 Ignore, 0 NoEffect, 0 NoChange, 0 Storage Accounts, and 0 Role Assignments.

The prior output showed exact counts and a successful security assertion. During the earlier correction, `/tmp/pse-pulse-phase4c3/` was absent, so its raw What-If JSON, detailed quota/catalog responses, and validation response were not available for independent reinspection. The PostgreSQL capability response was later available and is summarized below. No Azure commands were rerun. The updated strict NSG validator was exercised against local What-If fixtures only; it was not applied to the unavailable live What-If JSON. These are historical results, not a fresh Azure verification.

## Gate B PostgreSQL capability diagnosis

The saved response at `/tmp/pse-pulse-phase4c3/postgres-skus.json` contained one `FlexibleServerCapabilities` record. It listed the `Burstable` tier, `Standard_B1ms` under that tier, and PostgreSQL major version `16`. The location status, each target capability status and reason, and location `restricted` field were present with JSON `null`. The B1ms record reported 1 vCore, 2048 MB per vCore, 640 IOPS, zones 1–3, and HA modes SameZone and ZoneRedundant. These catalog entries establish listing only; they do not establish explicit availability or an explicit region restriction.

The previous parser required each target status to equal `Available` and required `restricted` to equal `Disabled`, but did not check the location-level status. It therefore rejected this response, while its message inaccurately described an unspecified restriction as a restricted location. The corrected summary preserves field state (`ABSENT`, `NULL`, or a returned value), records the requested region and location-level status, lists provider reasons after redaction, and emits the exact stop reason. The record label `FlexibleServerCapabilities` is not treated as a region identifier. The response has no explicit region identifier; the request itself is scoped with `--location eastasia`. If a region identifier is returned and conflicts with that requested region, the evidence is rejected as indeterminate. No Azure call was made to refresh this evidence.

**Classification:** `INDETERMINATE` — target capabilities are listed but explicit availability is unspecified; location status and restriction state are also unspecified. The script stops with `NO_GO_POSTGRES_CAPABILITY_INDETERMINATE`. It uses `NO_GO_POSTGRES_RESTRICTED` only for explicit disablement, an explicitly restricted location, or a blocking provider reason.

**Testing scope:** the classification correction was tested offline only with local JSON fixtures. It was not executed against Azure. Null or absent metadata is never treated as success or reported as confirmed restriction.

## IaC candidate

The new script checks the six accepted SHA256 values before any Azure query:

| Candidate file | Accepted SHA256 |
| --- | --- |
| `infra/main.bicep` | `efa8a5e8e4571e4a0f60b50cc06f9444826a148392f297d0b508f893c7500009` |
| `infra/modules/network.bicep` | `f042280227dcc74dcb01d26ce0a5a4962f532c79e8509018916c3f3808242029` |
| `infra/modules/compute.bicep` | `459c7115b7a14f06b84003ad0d6f66871d6c4f80d69fa9b8506ea7beda24eec5` |
| `infra/modules/postgres.bicep` | `3f537ceaf6d4dac37cf091fbecb0daed7e22bc1c871549f04fe03202c178ce42` |
| `infra/modules/storage.bicep` | `b21facba372a409be125eab051d434c90b86a9dc0ea1612e0c54451a201745eb` |
| `infra/parameters/phase4b.eastasia.bicepparam` | `c99b776765938988698a917308fbd448d903afe4a7c961de33ff304fe1d9c29c` |

No IaC was changed. The candidate keeps `deployBlob=false` and `enableSsh=false`.

## What-If inventory contract

The validator reads Azure's subscription-scope What-If JSON from `properties.changes` and validates each `changeType`, `resourceType`, `resourceId`, and `after` payload, including explicit success status. It permits excluding nested `Microsoft.Resources/deployments` metadata only. It requires the resource IDs to belong to the approved subscription and resource group, and the resource group to be named `rg-pse-pulse-student-prod` in East Asia. The private DNS virtual network link must point to the planned VNet. It requires exactly one Create of each approved type:

| Resource type | Count |
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

Any missing, duplicate, unexpected, or non-Create resource change fails closed. Storage Accounts and Role Assignments are explicitly rejected. The parser also checks the approved VM, disk, identity and authentication settings; network ranges, subnet delegation and private DNS; public IPv4; and PostgreSQL SKU, version, storage and private settings.

The NSG contract requires exactly one rule and it must be Inbound, Allow, TCP, from `Internet`, source port `*`, destination `*`, destination port `443`, priority 100. Port ranges and plural source/destination fields are rejected. Additional rules, public SSH, public 8000/5432, and any other source/destination contract fail closed. Committed network IaC was not changed.

## Financial eligibility

Every current billing item remains unverified and must be reconfirmed by the owner:

| Item | Status |
| --- | --- |
| Student credit current balance | `OWNER_RECONFIRMATION_REQUIRED` |
| Current Azure for Students offer | `OWNER_RECONFIRMATION_REQUIRED` |
| Credit expiration | `OWNER_RECONFIRMATION_REQUIRED` |
| PAYG state | `OWNER_RECONFIRMATION_REQUIRED` |
| Payment method | `OWNER_RECONFIRMATION_REQUIRED` |
| Spending-limit behavior | `UNKNOWN_UNLESS_VERIFIED` |
| Monthly budget and alerts | `OWNER_RECONFIRMATION_REQUIRED` |
| Current cost estimate | `REVALIDATION_REQUIRED` |

The prior USD 100 / USD 100 credit figure and 2027-08-14 expiry are historical evidence, not current eligibility. Historical fixed-cost planning references are approximately USD 70.63/month gross and USD 44.95/month allowance-adjusted proxy. Neither is a guaranteed bill. The USD 75/month budget remains alert-only and does not stop charges. Variable egress, DNS, disk, backup, or allowance-overage costs can apply.

## Credential and authorization boundary

The preparation script generates temporary validation-only SSH and PostgreSQL values, writes a mode-0600 parameter file under an owner-only evidence directory, and removes the parameter file and temporary values on every exit path. It does not copy Azure authentication state. No production credential is requested or used.

The owner checklist records future production credential and explicit authorization requirements. No authorization is accepted by this script from a variable, configuration file, saved output, or other automatic source. ChatGPT review alone is not owner authorization.

## Verification performed for this correction

- `bash -n scripts/azure_phase4c3_deployment_preflight.sh`: passed.
- Existing Phase 4C.3 offline tests: **13 unittest methods passed** in the earlier correction, covering repository safety, Bicep capture, capability checks, What-If status handling, and inventory validation.
- PostgreSQL classification regression tests for this correction: **24 unittest methods passed** using local JSON fixtures; no Azure CLI was invoked.
- The regression test is in `backend/tests/test_phase4c3_postgres_capability.py`; its generated fixtures and output use temporary directories under `/tmp/`. No Azure CLI operation was run.
- Mutation-command scan found no operational resource provisioning command, provider mutation, dynamic shell evaluation, or alternate execution mode in the new script.
- Secret scan found no credentials, full subscription/tenant IDs, or Azure authentication state in the modified deliverables.
- `git diff --check` passed. Exactly two tracked files are modified, the new regression test is untracked, and the staging area is empty.

## Mutation accounting

For this correction:

| Azure mutation | Count |
| --- | ---: |
| Resource creates | 0 |
| Resource modifications | 0 |
| Resource deletions | 0 |
| Provider registrations/unregistrations | 0 |
| Quota, policy, or budget changes | 0 |
| Role assignment changes | 0 |
| Azure commands executed | 0 |

No Azure commands were run during this correction. The earlier preparation summary recorded one ARM validation and one What-If; their raw responses could not be re-read because the saved evidence directory was unavailable.

## Final Gate A status

**PHASE 4C.3 GATE B:** `NO_GO_BILLING_SAFETY` / `NO_GO_POSTGRES_CAPABILITY_INDETERMINATE`

**OWNER DEPLOYMENT AUTHORIZATION:** `NOT_GRANTED`

**PHASE 4C.3 GATE A:** `NO_GO_BILLING_SAFETY`

**TECHNICAL PREFLIGHT:** `PRIOR_RECORDED_PASS; RAW EVIDENCE UNAVAILABLE FOR REVALIDATION`

**AZURE_INFRASTRUCTURE_NOT_DEPLOYED**

**OWNER_DEPLOYMENT_AUTHORIZATION:** `NOT_GRANTED`

**RECOMMENDATION:** `AWAITING CHATGPT FINAL REVIEW BEFORE COMMIT`
