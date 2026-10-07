# Phase 4C.0 Azure Deployment Authorization Preflight

**Evidence collected:** 2026-10-07 UTC
**Scope:** read-only authorization, capacity, and public retail-price preflight
**Azure mutation:** none during Phase 4C.0; Phase 4C.1 provider registration is separately authorized

## Gate

```text
PHASE 4C.0 AUTHORIZATION GATE:
READY_FOR_PROVIDER_REGISTRATION_AUTHORIZATION
AZURE_INFRASTRUCTURE_NOT_DEPLOYED
```

The subscription is enabled and the accepted East Asia policy and catalog evidence remain in place. The owner has confirmed the student-credit balance and expiry, PAYG state, displayed spending-limit field, free-service allowances, and a $75 monthly alert-only budget. The spending-limit field was not displayed, so no ON/OFF state is inferred. The owner separately authorized Phase 4C.1 registration of only Microsoft.Network, Microsoft.Compute, and Microsoft.DBforPostgreSQL.

## Repository baseline

- Repository: `AlvinTubtub/pse-pulse-mmdc-project`
- Branch: `main`
- HEAD and `origin/main`: `c5baf980d9c15a8913e155cbb0769dda70dab017`
- Working tree was clean before this Phase 4C.0 work.
- Phase 4B files and deployment design were not changed.
- The Phase 4C.0 script requires `main`, the Phase 4B commit as an ancestor, and no tracked or staged changes.
- Raw account, Azure query, and price responses are stored under `/tmp/pse-pulse-phase4c0/` with directory/file permissions restricted by `umask 077`; they are not repository files.

## Azure subscription summary

| Field | Read-only evidence |
| --- | --- |
| Display name | `Azure for Students` |
| State | `Enabled` |
| Masked subscription ID | `2982c1f8-****-****-****-b4d8` |
| Tenant display label | `Default Directory` |
| Account context | User account; billing account listing showed an active individual Microsoft Customer Agreement account |

Owner-confirmed portal observations: $100/$100 available, $0 used; student credit and free services expire 2027-08-14; October cost $0.00; subscription active/enabled on Azure Plan / Microsoft Azure Plan under a Microsoft Customer Agreement. PAYG was not upgraded; the portal still offers “Move to pay-as-you-go pricing for free services and uninterrupted access to Azure.” Upgrade was not clicked and no payment method is attached. The spending-limit field was not displayed, so no spending-protection state is inferred. These are owner-provided observations, not CLI-verified billing data.

## Student-offer evidence

- `az account show` and `az account list` returned the display name `Azure for Students` and state `Enabled`.
- Owner portal confirmation: available student credit $100/$100; used credit $0; expiry 2027-08-14; October cost $0.00.
- Owner portal confirmation: subscription active/enabled on Azure Plan / Microsoft Azure Plan; billing account type Microsoft Customer Agreement; PAYG upgrade not clicked and no payment method attached.
- The portal still offers “Move to pay-as-you-go pricing for free services and uninterrupted access to Azure.”
- **SPENDING LIMIT: NOT DISPLAYED / NO STATE INFERRED.** The owner confirmed PAYG was not upgraded, no payment method was attached, $100/$100 student credit was available, and the credit expires 2027-08-14.

Microsoft's Azure for Students FAQ directs students to the Azure Sponsorships portal for remaining credit and describes the offer's credit period and upgrade path. The Azure spending-limit documentation says credit-bearing plans can have a spending limit, but a PAYG plan does not have that spending-limit control. These public rules do not establish this account's current values. [Azure for Students FAQ](https://learn.microsoft.com/en-us/azure/education-hub/faq), [Azure spending limit](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit), [Azure subscription upgrade](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/upgrade-azure-subscription).

## Owner portal confirmations

Owner confirmations are recorded above. They do not authorize infrastructure deployment, quota changes, or later phases.

### Verified free-service meters (owner-confirmed)

- PostgreSQL Flexible Server B1ms compute: 750 hours/month; PostgreSQL storage: 32 GB/month; PostgreSQL LRS backup: 32 GB/month. Each was unused when checked.
- VM free-service SKUs: B1s, B2pts_v2, and B2ats_v2; each was unused when checked.
- Standard_B2als_v2 is not one of the verified free VM SKUs and remains credit-backed. Standard_B2as_v2 is also not verified as free. Neither B2als_v2 nor B2as_v2 is classified as free.
- The owner reported 311 days remaining when checking the 2027-08-14 expiry.

## Effective allowed-region policy

The read-only subscription-scope assignment remains `sys.regionrestriction` (`Allowed resource deployment regions`). Its allowed-location parameter includes:

`koreacentral`, `australiaeast`, `centralindia`, `eastasia`, `japaneast`

**East Asia (`eastasia`): allowed.** The assignment still includes East Asia. Southeast Asia remains excluded. The target resource group `rg-pse-pulse-student-prod` does not currently exist (`az group exists` returned `false`).

## Provider states

| Provider | Current state | Phase 4C requirement |
| --- | --- | --- |
| Microsoft.Resources | Registered | Required |
| Microsoft.Authorization | Registered | Required for the reviewed authorization model |
| Microsoft.Network | NotRegistered | Required later |
| Microsoft.Compute | NotRegistered | Required later |
| Microsoft.DBforPostgreSQL | NotRegistered | Required later |
| Microsoft.Storage | NotRegistered | Optional while `deployBlob=false`; not requested |

No provider was registered or unregistered. If owner gates are later accepted, a separate Phase 4C.1 authorization may cover only Microsoft.Network, Microsoft.Compute, and Microsoft.DBforPostgreSQL.

## East Asia VM SKU evidence

The CLI `az vm list-skus` path was slow in this subscription. The script therefore used the read-only `Microsoft.Compute/skus` ARM endpoint filtered to East Asia and saved the response under `/tmp`.

| SKU | In East Asia | Restrictions | Catalog details | Zones |
| --- | --- | --- | --- | --- |
| `Standard_B2als_v2` primary | Yes | `[]` | 2 vCPU, 4 GB, x64 | 1, 2, 3 |
| `Standard_B2as_v2` fallback | Yes | `[]` | 2 vCPU, 8 GB, x64 | 1, 2, 3 |

The catalog shows regional SKU support and no explicit SKU restriction. It does **not** prove allocated capacity or guarantee deployment capacity. The primary remains `Standard_B2als_v2`; the fallback is informational and is not selected automatically.

## VM quota evidence

`az vm list-usage --location eastasia` returned no rows while Microsoft.Compute is `NotRegistered`. An empty usage response is not treated as zero quota.

```text
VM_QUOTA_UNRESOLVED_PENDING_PROVIDER_REGISTRATION
```

No quota change was requested. Quota must be rechecked after the separately authorized provider-registration phase.

## Ubuntu image evidence

The East Asia image listing returned Canonical `ubuntu-24_04-lts`, SKU `server`, architecture `x64`. Latest stable x64 server image version visible in the read-only result: `24.04.202609040`. The committed image contract remains `version: latest`; no IaC was changed.

## PostgreSQL SKU evidence

The PostgreSQL Flexible Server East Asia capabilities endpoint returned `Standard_B1ms` under tier `Burstable` with `restricted: Disabled`:

- vCores: 1
- Memory per vCore: 2,048 MB (approximately 2 GiB)
- IOPS: 640
- Supported zones: none listed for this SKU
- Storage constraints: not exposed by this capabilities response
- PostgreSQL major version in the committed template: 16
- Provisioned storage target: 32 GB

This is catalog/capability evidence, not a promise of subscription entitlement or live provisioning capacity. Committed high availability and geo-redundant backup remain disabled; network access remains private through the delegated VNet and private DNS.

## Committed infrastructure configuration

The accepted Phase 4B deployment candidate is unchanged:

- Region `eastasia`; resource group `rg-pse-pulse-student-prod`.
- VM `Standard_B2als_v2`; fallback candidate `Standard_B2as_v2`.
- Canonical `ubuntu-24_04-lts` / `server` / x64 / `latest`.
- VM OS disk: 32 GiB, `StandardSSD_LRS` (E4 LRS tier).
- VM administrative user: `psepulseops`; reserved future non-root application/systemd user: `psepulse`.
- Public IPv4: Standard, static.
- PostgreSQL Flexible Server: `Standard_B1ms`, Burstable, PostgreSQL 16, 32 GB storage, seven-day backup retention, HA and geo-redundant backup disabled, private VNet integration, public access disabled.
- Private DNS zone: `private.postgres.database.azure.com`.
- `deployBlob=false`; `enableSsh=false`.
- No Log Analytics workspace or Application Insights resource is part of the baseline.

The accepted future inventory remains nine predicted resource types: resource group; NSG; VNet; public IPv4; NIC; private DNS zone; private DNS VNet link; VM; PostgreSQL Flexible Server.

## Current Azure public retail pricing evidence

Prices below are **PUBLIC RETAIL REFERENCE**, not an actual bill or the user's student-credit rate. They are USD Consumption/on-demand results from the official Azure Retail Prices API, queried 2026-10-07. The selection used East Asia and the approved SKU/meter; Windows, Spot, and Low Priority VM meters were excluded. API documentation: [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices). Full responses remain outside Git under `/tmp/pse-pulse-phase4c0/`.

| Baseline item | Selected public meter | Unit price / unit | Effective start | Monthly reference at 730h |
| --- | --- | ---: | --- | ---: |
| Primary VM `Standard_B2als_v2` | `Virtual Machines Basv2 Series`, meter `B2als v2`, SKU `Standard_B2als_v2`, East Asia | USD 0.0526 / 1 Hour | 2023-09-01 | USD 38.398 (USD 38.40 rounded) |
| Fallback VM `Standard_B2as_v2` | `Virtual Machines Basv2 Series`, meter `B2as v2`, SKU `Standard_B2as_v2`, East Asia | USD 0.105 / 1 Hour | 2023-09-01 | USD 76.65 |
| 32 GiB Standard SSD OS disk | `Standard SSD Managed Disks`, meter `E4 LRS Disk`, SKU `E4 LRS`, East Asia | USD 2.40 / 1 Month | 2019-01-01 | USD 2.40 |
| Standard static IPv4 | `IP Addresses`, meter `Standard IPv4 Static Public IP`, SKU `Standard`, East Asia | USD 0.005 / 1 Hour | 2018-06-01 | USD 3.65 |
| PostgreSQL B1ms compute | Flexible Server Burstable BS Series, meter/SKU `B1MS`, East Asia | USD 0.0286 / 1 Hour | 2021-12-01 | USD 20.878 (USD 20.88 rounded) |
| PostgreSQL storage | Flexible Server Storage, meter `Storage Data Stored`, East Asia | USD 0.15 / 1 GB/Month | 2021-06-01 | USD 4.80 for 32 GB |
| One Private DNS zone | Azure DNS, meter `Private Zone`, first 25 zones tier, global/Zone 2 retail record | USD 0.50 / zone-month | 2019-12-01 | USD 0.50 |

Calculations: VM and public IP hourly prices × 730; PostgreSQL compute hourly price × 730; PostgreSQL storage USD 0.15 × 32; one Private DNS zone at the first-tier monthly meter. The Standard SSD E4 LRS entry is already a monthly provisioned-disk price; it is not multiplied by hours.

The Standard SSD E4 tier corresponds to a 32 GiB provisioned disk. Its API response also lists Standard SSD operations at USD 0.002 per 10,000 operations; operation volume is unknown and is treated as variable. Standard IPv4 is separated from Basic, IPv6, IP prefix, and global IP meters.

Official pricing references: [Managed Disks](https://azure.microsoft.com/en-us/pricing/details/managed-disks/), [IP Addresses](https://azure.microsoft.com/en-us/pricing/details/ip-addresses/), [PostgreSQL Flexible Server](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/), and [Azure DNS](https://azure.microsoft.com/en-us/pricing/details/dns/). The API is the source for the meter figures above; published retail rates can differ from account-specific rates.

## Primary and fallback VM monthly references

- Primary `Standard_B2als_v2`: USD 0.0526/hour × 730 = **USD 38.398/month** (USD 38.40 rounded).
- Fallback `Standard_B2as_v2`: USD 0.105/hour × 730 = **USD 76.65/month**.
- The primary remains selected. The fallback is not substituted without separate review and approval.

## OS disk monthly reference

The committed 32 GiB `StandardSSD_LRS` disk maps to the Standard SSD E4 LRS meter, USD 2.40 per provisioned disk-month in East Asia. Disk operation usage is separate and variable; no transaction count is assumed. No snapshot charge is included.

## Public IPv4 monthly reference

The selected Standard static IPv4 meter is USD 0.005/hour in East Asia, or **USD 3.65/month** at 730 hours. The meter is not Basic IPv4, IPv6, Public IP Prefix, or Global Static Public IP.

## PostgreSQL compute and storage monthly references

- B1ms Burstable compute: USD 0.0286/hour × 730 = **USD 20.878/month** (USD 20.88 rounded).
- 32 GB provisioned storage: USD 0.15/GB-month × 32 = **USD 4.80/month**.
- Storage constraints were not returned by the region capabilities query. This price is a public reference for the provisioned 32 GB, not a student allowance determination.

## PostgreSQL backup classification

The Retail Prices API lists East Asia LRS backup storage at USD 0.095 per GB-month. Microsoft's PostgreSQL Flexible Server documentation says included backup storage is up to 100% of provisioned server storage; for this configuration that is up to 32 GB, with excess charged. Therefore the fixed subtotal assumes **USD 0 incremental backup charge only while actual retained backup storage stays within the included 32 GB**. Actual backup consumption is unknown and may exceed that allowance due to retained data and WAL/change volume, so any excess remains **VARIABLE / UNRESOLVED**. Seven-day retention does not establish a specific backup footprint. [Backup and restore cost model](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore).

## Private DNS pricing

- One Private DNS zone: USD 0.50 per zone-month in the first 25-zone tier (Retail API record has no single Azure `armRegionName`, as this is a global meter).
- Private DNS queries: USD 0.40 per million queries in the returned Private Queries retail meter.
- No query count is assumed; query usage is **VARIABLE**. The fixed one-zone charge is included in the subtotal.
- No Private Resolver or extra DNS resource is in the baseline.

## VNet, NSG, NIC, and transfer costs

For this standard architecture, no direct base resource meter was identified for the VNet, NSG, or NIC. Microsoft documents no charge for Azure Virtual Network use, NSGs, or ordinary NIC resources. [Virtual Network overview](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview), [VM resource billing overview](https://learn.microsoft.com/en-us/azure/virtual-machines/overview).

- Internet egress: **VARIABLE**; no traffic volume is invented. Microsoft currently documents inbound transfer as free and internet egress tiers (including the first 100 GB/month free in the published global bandwidth schedule); usage above included tiers can be chargeable. [Bandwidth pricing](https://azure.microsoft.com/en-us/pricing/details/bandwidth/).
- Inter-region transfer: not part of the baseline unless introduced later.
- VNet peering, NAT Gateway, Bastion, Firewall, Load Balancer, Application Gateway, and Private Endpoint are not in the baseline.
- Standard SSD operations and Private DNS query volume are also usage-variable.

## Blob and monitoring

- `deployBlob=false`: Storage Account USD 0 from this architecture; Blob operations USD 0; Blob role assignment is not deployed. Microsoft.Storage is optional and remains unregistered.
- The baseline has no Log Analytics workspace or Application Insights resource, so no paid ingestion is included. Native Azure platform metrics are documented as no-charge; no advanced metrics, custom metrics, alert rules, or diagnostic-log exports are assumed. [Azure Monitor platform metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/metrics/data-platform-metrics), [Azure Monitor cost and usage](https://learn.microsoft.com/en-us/azure/azure-monitor/usage-estimated-costs).

## Fixed monthly public-retail-reference subtotal

| Included fixed meter | USD/month |
| --- | ---: |
| Primary VM compute | 38.398 |
| 32 GiB Standard SSD E4 LRS OS disk | 2.400 |
| Standard static IPv4 | 3.650 |
| PostgreSQL B1ms compute | 20.878 |
| PostgreSQL 32 GB storage | 4.800 |
| One Private DNS zone | 0.500 |
| **Fixed public retail reference subtotal** | **70.626 (USD 70.63 rounded)** |

This is a 730-hour public retail planning subtotal before tax and account-specific benefits/discounts. It excludes the fallback VM, variable egress, DNS queries, disk operations, backup overage, snapshots, support, and any out-of-scope resource. It is not a quote or actual bill.

## Verified student/free allowances and expected credit consumption

- **VERIFIED ACCOUNT-SPECIFIC PORTAL ALLOWANCES:** PostgreSQL Flexible Server B1ms compute, 750 hours/month; PostgreSQL storage, 32 GB/month; PostgreSQL LRS backup, 32 GB/month; VM B1s, B2pts_v2, and B2ats_v2, 750 hours/month each. The owner reported these meters unused when checked. These allowances do not guarantee zero realized PostgreSQL cost before actual billing is observed; usage, eligibility application, and overages must be confirmed against billing.
- **NOT VERIFIED AS FREE:** `Standard_B2als_v2` and `Standard_B2as_v2`. The selected `Standard_B2als_v2` remains student-credit-backed.
- Keep the gross fixed public-retail subtotal of **USD 70.63/month** as the conservative gross reference; it is not an actual bill or the user's student-credit rate.
- **Allowance-adjusted planning view only:** if the verified PostgreSQL free-service meters are successfully applied, the known fixed non-PostgreSQL public-retail reference is approximately VM compute USD 38.398/month + 32 GiB Standard SSD USD 2.40/month + Standard static IPv4 USD 3.65/month + one Private DNS zone USD 0.50/month = **USD 44.948/month (USD 44.95 rounded)**. This is an approximate fixed credit-backed planning proxy, not a guaranteed actual bill.
- Keep variable items separate: internet egress, DNS queries, disk operations, PostgreSQL backup overage, and any allowance overrun. Actual credit draw and realized costs depend on usage and billing application.
- The owner confirmed $100/$100 student credit and a 2027-08-14 expiry. **SPENDING LIMIT: NOT DISPLAYED / NO STATE INFERRED.**

## Credit runway and expiry runway

- Owner-confirmed credit at time checked: $100 available out of $100; expiry 2027-08-14 (311 days remaining when checked).
- October cost was $0.00 when checked. These values are time-specific owner portal observations, not a forecast of future usage.
- Practical runway remains usage-dependent. Variable egress, DNS queries, disk operations, and backup overage can increase consumption.

## Owner monthly-budget approval

```text
OWNER_MONTHLY_BUDGET_APPROVAL:
APPROVED_AT_USD_75_PER_MONTH
```

The owner selected **$75/month** as the project budget ceiling, and the Azure Cost Management budget `Monthly_ceiling_75_USD` exists. It is alert-only, not an enforcement cap; Azure does not automatically stop resources at $75. Any infrastructure deployment still requires separate later authorization, and variable-cost exposure must be reviewed before deployment. The conservative gross public-retail reference is USD 70.63/month fixed at continuous 730-hour operation, with variable/unresolved charges; the allowance-adjusted USD 44.95/month figure above is a planning proxy only.

## Open deployment blockers

1. Microsoft.Compute was NotRegistered at the Phase 4C.0 evidence point; Phase 4C.1 subsequently registered it. Authoritative quota and capacity evaluation remain for Phase 4C.2.
2. Deployment authorization, final validation, and What-If remain for Phase 4C.2 review.
3. Spending-limit status was not displayed in the portal; no ON/OFF state is inferred.

The owner-confirmed billing state clears the Phase 4C.0 information gate for the separately authorized provider-registration step. It does not authorize infrastructure deployment, quota changes, or later phases.

## Azure mutation proof

- Azure resources created: `0`
- Azure resources modified: `0`
- Azure resources deleted: `0`
- Provider registrations performed: `0`
- Provider unregistrations performed: `0`
- Policy changes/exemptions performed: `0`
- Role assignments performed: `0`
- Deployment create commands executed: `0`
- Quota changes requested: `0`
- Azure Cost Management budget resources created: `1` (owner-created; not created during Phase 4C.0)
- Azure infrastructure resources created: `0`
- Artifact uploads: `0`
- Production DB migrations: `0`
- Remote model activations: `0`
- Production inference runs: `0`

**NO AZURE INFRASTRUCTURE RESOURCES WERE CREATED, MODIFIED, OR DEPLOYED DURING PHASE 4C.0.**

### Owner budget

The existing owner-created budget is `Monthly_ceiling_75_USD`, set to $75/month. Current spend was $0.00 when checked. Alerts are actual spend at 50%, actual spend at 80%, and forecasted spend at 100%. This is an alert-only guardrail, not a hard spending cap; Azure does not automatically stop resources at $75 based on this budget. One Azure Cost Management budget resource exists; no budget was created in Phase 4C.0. The subscription spending-limit field was not displayed, so no spending-protection state is asserted.

## Recommendation

Phase 4C.0 is ready for the separately authorized Phase 4C.1 registration of Microsoft.Network, Microsoft.Compute, and Microsoft.DBforPostgreSQL. Do not register Microsoft.Storage while `deployBlob=false`.

No deployment, quota, artifact, database, model, or scheduling action is authorized by this Phase 4C.0 result. Provider registration is authorized only by the separate Phase 4C.1 owner request.
