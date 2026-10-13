# Azure Cost Guardrails

The hard personal-spending limit is **USD 0**. The historical Azure for Students allocation was **USD 100**; the current balance, expiry, subscription spending limit, and exact meter eligibility were not checked. The owner-provided October 2026 Cost Analysis screenshot is reported as showing **USD 4.88 accrued** and a **USD 75 budget alert**. This evidence was not independently queried, and a budget alert is not a hard spending cap.

## Existing-resource boundary

The owner reports an existing East Asia Ubuntu 24.04 `Standard_B2als_v2` VM and private PostgreSQL 16 `Standard_B1ms` server. Phase 4D application deployment is limited to those resources. Do not deploy the older `infrastructure/azure` templates, create another resource, change quotas or network rules, register a provider, purchase a domain, add paid monitoring/storage, or upgrade to Pay-As-You-Go.

## Before any live operation

1. Confirm current Azure for Students subscription state, remaining credit and expiry in the owner account.
2. Confirm the subscription spending limit remains enabled and that credit exhaustion may suspend service. Do not use a payment method or PAYG fallback.
3. Estimate VM runtime, attached OS disk, public IPv4, PostgreSQL compute/storage/backups, private DNS queries, package downloads, certificate operations, and egress using current account/region data.
4. Stop if expected usage can exceed the available student credit or create any personal charge. Cost alerts are not hard spending caps.
5. Recheck remaining credit during setup and after any package installation, database operation, or sustained VM runtime.

No price estimate in this repository is a current personalized quote. Credit can be consumed while personal out-of-pocket stays at zero, so the owner should decide whether to continue if service suspension is preferable to consuming the balance.

## Excluded by this project constraint

- Pay-As-You-Go conversion or payment method attachment.
- New VM, Storage Account, managed database, public DNS/domain, gateway, firewall, monitoring workspace, or other billable Azure infrastructure.
- Infrastructure redeployment, provider registration, quota changes, or NSG changes as part of Phase 4D.

During this validation, one read-only `az account show --output json` attempt failed because the CLI had no authenticated session. No billing/resource query or Azure mutation was performed.
