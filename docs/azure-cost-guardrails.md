# Azure Cost Guardrails — Phase 4A

No Azure budget, alert, resource, or action group was created. These are design controls for a later authorized deployment. See the [Phase 4A readiness report](../PHASE4A_READINESS_REPORT.md) for the evidence, limitations, and full entitlement matrix.

## Zero-cost definitions

**Strict zero-consumption** means no paid meter use and no reduction in Azure student credit. Full LSTM serving plus a public Standard IPv4 does not meet that standard.

**Zero out-of-pocket using student credit** means student credit pays all charges, the active spend limit stops services on exhaustion, and the subscription is not upgraded to Pay-As-You-Go. This is conditional on the exact subscription, current credit balance/expiry, and protection state. It does not promise continuous service after credit exhaustion. Never describe an unverified account allowance as `$0`.

## Resource classification

| Resource | Category | Cost control |
|---|---|---|
| B1s/B2ats_v2/B2pts_v2 compute | A only if the active offer covers eligible SKU hours | Not acceptable for the all-family workload; 1 GiB fails memory budget. |
| PostgreSQL B1ms + 32 GiB storage + 32 GiB backup | A only within the confirmed subscription offer and limits | Confirm provider, region, SKU, hourly limit, storage, backup and expiry. HA off. Stop growth before allowance overrun. |
| Azure Container Apps/Static Web Apps grants | A only within current exact grant | Different deployment design; consumption beyond the grant can use credit. |
| B2als_v2 compute | B | Public SEA catalog reference: $0.0472/hour or ~$34.46 per 730 hours. |
| B2as_v2 compute | B | Public SEA catalog reference: $0.0944/hour or ~$68.91 per 730 hours. |
| OS managed disk | B | Separate monthly charge; exact disk SKU/region price was not verified. |
| Standard static Public IPv4 | B | Public catalog reference: $0.005/hour or ~$3.65 per 730 hours. |
| Azure Private DNS zone for PostgreSQL Flexible Server private access | **B — required and metered** | Hosted-zone and DNS-query charges apply. No exact price is asserted; include zone and query estimates in the reviewed Phase 4B monthly cost. This is separate from an optional public DNS zone/domain. |
| PostgreSQL Flexible Server B1ms | A only within the exact verified student grant; otherwise B/C | Required candidate; confirm entitlement, region, compute usage and quota. |
| PostgreSQL storage and backup | A only within the exact verified student limits; otherwise B/C | Required candidate; 32 GiB data and 32 GiB backup allowance must be confirmed. Overages can consume credit or become out-of-pocket. |
| Basic VNet, app/delegated subnets and NSG | Required baseline; no direct charge assumed for basic resource | Related traffic and add-on networking meters can charge. |
| Blob capacity, transactions and transfer | B/C | Optional; separately meter storage, reads/writes/list operations, redundancy and egress. |
| PostgreSQL over included limits | B/C | Treat as credit-consuming unless a current allowance is proven. |
| Data egress | B/C | Monitor transfer. The selected VM's attached Standard public IP is the explicit inbound/outbound path; no NAT Gateway is included in the baseline. |
| Public DNS/domain | Optional; B/C by provider/meter | Separate from the required Azure Private DNS zone; price and renewal remain unverified. |
| NAT Gateway, Azure Firewall, Bastion, Load Balancer, Private Endpoint, VPN Gateway | Excluded unless separately approved; B/C | Add only if a later design proves need and separately prices it. |
| Azure Monitor / Log Analytics / Application Insights | A only within a verified grant; otherwise B/C | Journald first; cap/retain logs before enabling ingestion. |
| Additional snapshots, marketplace images/support | B/C | Optional/excluded by default. |
| Additional VM, GPU, AKS | Excluded unless separately approved; B/C | Not part of the single-VM baseline. |
| Managed identity, basic VNet, NSG | No direct resource charge identified for the base resource | Related IP, processing, traffic and monitoring meters may charge. |

Prices above are on-demand public retail catalog observations for Southeast Asia, not a personalized quote. They exclude taxes, disks, PostgreSQL, network transfer, other services, and account discounts. The rough full-time **compute + public IPv4 subtotal** for B2als_v2 + Standard IPv4 is ~$38.11/month; B2as_v2 + IPv4 is ~$72.56/month. This partial subtotal excludes at least the OS disk, required PostgreSQL Private DNS zone and queries, PostgreSQL overage, optional Blob, egress, telemetry, public DNS/domain and taxes. A $100 one-time student credit is not a twelve-month operating budget.

## Student credit and spending protection

Before any later creation, inspect Education Hub → Overview for current student credit and expiry, Subscription → Properties for offer/state, and Cost Management + Billing for current meter consumption. Keep the spending limit enabled. Microsoft documents that free allowances vary by offer and duration; use its [Azure for Students offer](https://azure.microsoft.com/en-us/free/students/), [free-service rules](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/create-free-services), [Education Hub FAQ](https://learn.microsoft.com/en-us/azure/education-hub/faq), and [spending limit documentation](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit). Account-specific eligibility must still be confirmed in the portal.

Budgets and alerts are early warnings, not hard spending caps, and can be delayed. Do not upgrade to Pay-As-You-Go to keep a resource running after credit exhaustion.

## Proposed cost controls (not created)

1. Email alert thresholds against the $100 reference credit: $25 (25%), $50 (50%), $75 (75%), $90 (90%). Recalculate against the actual remaining credit before deployment.
2. Review credit and Cost Analysis weekly during setup; perform a daily Azure resource inventory during the first deployment week, then weekly.
3. Compare actual resource inventory with the approved IaC inventory. Investigate every unplanned resource, public IP, disk, workspace, network gateway, snapshot or role assignment.
4. Deallocate compute when the product may be offline. Check the separate disk and public-IP meters; deallocation does not remove them.
5. Keep log rotation/retention bounded. Start without Log Analytics/Application Insights until a free allowance and retention cost are confirmed.
6. Review PostgreSQL storage, backups, Private DNS zone/query charges, and Blob volume/operations monthly. Keep HA disabled and avoid duplicate long-retention backups unless approved.
7. Track data egress and optional public DNS/domain renewal separately. The VM-attached public IPv4 is the selected explicit outbound path; if it is removed or the VM becomes effectively private, redesign and price egress first.
8. If estimates approach the $90 alert or an unexpected meter appears, stop the deployment workflow and ask for a new approval. Alerts do not enforce a cap.

## Cost evidence still required

Portal/account confirmation is required for Azure for Students status, remaining credit/expiry, spending protection, exact free-meter application, and usage-to-date. Confirm the chosen region's VM quota/SKU, PostgreSQL availability/quota, OS disk rate, required Private DNS zone/query rate, Blob rate/operations, public IPv4, public DNS and outbound networking prices in the Azure Pricing Calculator before Phase 4B creation approval. The baseline requires a managed OS disk, VM, Standard public IPv4, PostgreSQL Flexible Server, PostgreSQL Private DNS zone, and basic VNet/subnets/NSG. Blob, public domain/DNS, centralized Azure Monitor/Log Analytics and additional snapshots are optional. NAT Gateway, Azure Firewall, Bastion, Load Balancer, Private Endpoint, VPN Gateway, paid monitoring workspace, additional VM, GPU and AKS are excluded unless separately approved.
