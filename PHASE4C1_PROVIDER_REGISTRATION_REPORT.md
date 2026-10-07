# Phase 4C.1 Azure Resource Provider Registration

**Repository:** `AlvinTubtub/pse-pulse-mmdc-project`
**Evidence date:** 2026-10-07
**Scope:** Register only the three owner-authorized Azure resource providers.

## Gate

```text
PHASE 4C.1 PROVIDER GATE:
REQUIRED_PROVIDERS_REGISTERED
AZURE_INFRASTRUCTURE_NOT_DEPLOYED
```

**Recommendation:** READY FOR CHATGPT REVIEW BEFORE PHASE 4C.2

**AZURE SUBSCRIPTION MUTATION WAS LIMITED TO THE EXPLICITLY AUTHORIZED RESOURCE-PROVIDER REGISTRATIONS.**
**NO AZURE INFRASTRUCTURE RESOURCES WERE CREATED, MODIFIED, OR DEPLOYED.**

## Repository baseline

- Branch: `main`
- HEAD and verified `origin/main`: `c5baf980d9c15a8913e155cbb0769dda70dab017`
- Required Phase 4B commit is an ancestor of HEAD.
- No tracked changes or staged changes were present before executing the script. Phase 4C evidence files are untracked by design.
- Phase 4B files were not modified. No files were staged, committed, or pushed.
- The script passed `bash -n` and its command allowlists were inspected before execution.

## Subscription and owner-confirmed billing facts

- Subscription display name/state: **Azure for Students / Enabled**.
- Masked subscription ID: `2982c1f8-****-****-****-b4d8`.
- Owner-confirmed available credit: **$100 of $100**; used credit **$0**.
- Student-credit and free-services expiry: **2027-08-14**; owner reported 311 days remaining when checked.
- October cost at the time checked: **$0.00**.
- Plan: **Azure Plan / Microsoft Azure Plan**; billing account: **Microsoft Customer Agreement**.
- PAYG upgrade was not clicked. The portal still offered “Move to pay-as-you-go pricing for free services and uninterrupted access to Azure.” No payment method was attached.
- The spending-limit field was not displayed. No spending-protection ON/OFF state is inferred.
- Free-service meters owner confirmed: PostgreSQL Flexible Server B1ms 750 hours/month, PostgreSQL storage 32 GB/month, PostgreSQL LRS backup 32 GB/month. Each was unused when checked.
- Owner-confirmed free VM SKUs: B1s, B2pts_v2, B2ats_v2; each was unused when checked. `Standard_B2als_v2` is not a verified free SKU and remains credit-backed. `B2als_v2` is not classified as free.
- Existing owner-created Azure Cost Management budget: `Monthly_ceiling_75_USD`, **$75/month**. Alerts: actual spend 50%, actual spend 80%, forecasted spend 100%. This budget is alert-only, not a hard spending cap. Current spend was $0.00 when checked. The owner created one budget resource; no budget was created during Phase 4C.1.

These billing details are owner-confirmed portal observations carried forward from Phase 4C.0, not values independently retrieved by this registration script.

## Target and provider states

- Target region: `eastasia`.
- Target resource group: `rg-pse-pulse-student-prod`.
- Resource group before registration: **false** (does not exist).

| Provider | Before | Phase 4C.1 result | After |
| --- | --- | --- | --- |
| Microsoft.Resources | Registered | Read-only check | Registered |
| Microsoft.Authorization | Registered | Read-only check | Registered |
| Microsoft.Network | NotRegistered | Registered in 134 seconds | Registered |
| Microsoft.Compute | NotRegistered | Registered in 107 seconds | Registered |
| Microsoft.DBforPostgreSQL | NotRegistered | Registered in 82 seconds | Registered |
| Microsoft.Storage | NotRegistered | Untouched | NotRegistered |

## Authorized registration operations

The script executed exactly these registration operations, sequentially, and waited for each provider to reach `Registered` before proceeding:

1. `az provider register --namespace Microsoft.Network`
2. `az provider register --namespace Microsoft.Compute`
3. `az provider register --namespace Microsoft.DBforPostgreSQL`

The script skipped no provider as already registered. Microsoft.Storage did not appear in the registration target list and remains `NotRegistered`. The script contains no provider-unregister path and its registration wrapper rejects all namespaces outside the exact three-provider allowlist.

## Preliminary post-registration quota evidence

After Microsoft.Compute registered, the read-only `az vm list-usage --location eastasia` query returned usage information. Preliminary examples:

- Total regional vCPUs: limit **6**, current **0**.
- Standard Basv2 Family vCPUs: limit **10**, current **0**.
- Virtual Machines: limit **25,000**, current **0**.

This is preliminary quota output only. It is not a final quota, capacity, or deployment decision. Phase 4C.2 owns authoritative quota evaluation, capacity recheck, validation, and final What-If.

- Resource group after registration: **false** (does not exist).
- No resource-listing or deployment command was needed: the script issued only the three allowlisted provider-registration mutations, read-only state checks, the required resource-group existence checks, and the optional read-only VM usage query.

## Mutation accounting

| Mutation type | Count/result |
| --- | ---: |
| Provider registrations performed | **3** |
| Provider namespaces registered | `Microsoft.Network`, `Microsoft.Compute`, `Microsoft.DBforPostgreSQL` |
| Provider unregistrations performed | **0** |
| Azure resource groups created | **0** |
| Azure infrastructure resources created | **0** |
| Azure infrastructure resources modified | **0** |
| Azure infrastructure resources deleted | **0** |
| Policy changes/exemptions | **0** |
| Role assignments | **0** |
| Deployment create commands | **0** |
| Quota changes | **0** |
| Storage provider registrations | **0** |
| Application deployments | **0** |
| Artifact uploads | **0** |
| Production DB migrations | **0** |
| Remote model activations | **0** |
| Production inference runs | **0** |
| Scheduling changes | **0** |
| Budget resources newly created during Phase 4C.1 | **0** |

Existing owner-created budget: `Monthly_ceiling_75_USD`.

## Remaining Phase 4C.2 gates

- Recheck authoritative East Asia VM quota and SKU capacity for the accepted architecture.
- Run the separately reviewed post-registration deployment validation and final What-If.
- Evaluate any validation or What-If findings before any later deployment authorization.
- Keep `Microsoft.Storage` unregistered while `deployBlob=false`.
- Preserve the approved Phase 4B design unless a later reviewed change authorizes a correction.

No Phase 4C.2 or 4C.3 work was started. No resource group, infrastructure, role assignment, quota change, deployment, storage provider registration, artifact, database migration, model activation, inference run, or schedule was created or changed.
