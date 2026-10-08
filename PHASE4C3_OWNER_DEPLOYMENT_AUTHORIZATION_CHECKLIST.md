# Phase 4C.3 Owner Deployment Authorization Checklist

**Purpose:** Record owner decisions and evidence required before any future Gate B review. This checklist does not initiate or perform a deployment.

Gate A preparation authorization does **not** authorize Gate B deployment. Only the owner can authorize Gate B. ChatGPT review alone is not deployment authorization. No deployment should occur until the owner explicitly approves the reviewed deployment plan.

## A. Gate A preparation authorization

- [ ] I authorize Gate A read-only account/provider/policy/quota/catalog queries, local Bicep build, ARM validation, and What-If only.
- [ ] I understand Gate A includes no infrastructure creation, modification, deletion, or application deployment.
- [ ] I understand the preparation-only script does not provide a provisioning mode.

## B. Gate A technical verification

- [ ] Confirm the accepted repository baseline and all six IaC hashes.
- [ ] Confirm subscription identity/state, East Asia policy, required provider states, and Storage remains NotRegistered.
- [ ] Confirm the target resource group is absent before and after preview.
- [ ] Confirm primary VM quota/SKU, Ubuntu 24.04 x64 image, and PostgreSQL B1ms capability.
- [ ] Review the actual ARM validation output and full-payload What-If.
- [ ] Confirm exactly nine approved Create changes, with zero other change types, Storage Accounts, Role Assignments, or unexpected types.
- [ ] Review the exact HTTPS-only NSG rule and all network/security payloads.
- [ ] Confirm temporary validation credentials and parameters were removed.

## C. Financial eligibility confirmation

Complete immediately before any future Gate B decision. The previously reported USD 100 credit and expiry date are historical, not current.

- [ ] Current student-credit balance: ____________________
- [ ] Current Azure for Students offer and subscription state: ____________________
- [ ] Current credit expiration date: ____________________
- [ ] PAYG upgrade state: ____________________
- [ ] Payment method attached/available: ____________________
- [ ] Spending-limit behavior verified from the account: ____________________
- [ ] Monthly budget amount and alert recipients/thresholds verified: ____________________
- [ ] Current cost estimate revalidated for the exact deployment candidate: ____________________

Required status labels until verified: current balance, offer, expiry, PAYG, payment method, budget/alerts are `OWNER_RECONFIRMATION_REQUIRED`; spending-limit behavior is `UNKNOWN_UNLESS_VERIFIED`; current cost is `REVALIDATION_REQUIRED`.

## D. Infrastructure cost acknowledgment

- [ ] I reviewed the updated current cost estimate and its assumptions.
- [ ] I understand the historical gross fixed planning reference of approximately USD 70.63/month is not a guaranteed bill.
- [ ] I understand the historical allowance-adjusted fixed proxy of approximately USD 44.95/month is not a guaranteed bill.
- [ ] I understand Standard_B2als_v2 is not verified as a free VM SKU and can consume student credit.
- [ ] I understand egress, DNS, disk operations, PostgreSQL backup overage, and allowance overages can add variable charges.
- [ ] I understand the USD 75 monthly budget is alert-only and does not automatically stop spending.
- [ ] I understand charges may begin when resources are provisioned.

## E. Exact nine-resource deployment inventory

The reviewed plan must contain exactly one of each listed type, all as Create, and no other infrastructure change. The VM managed OS disk may appear as an associated Azure resource and must be verified against the VM and included in cost review.

- [ ] `Microsoft.Resources/resourceGroups`
- [ ] `Microsoft.Network/networkSecurityGroups`
- [ ] `Microsoft.Network/virtualNetworks`
- [ ] `Microsoft.Network/publicIPAddresses`
- [ ] `Microsoft.Network/networkInterfaces`
- [ ] `Microsoft.Network/privateDnsZones`
- [ ] `Microsoft.Network/privateDnsZones/virtualNetworkLinks`
- [ ] `Microsoft.Compute/virtualMachines`
- [ ] `Microsoft.DBforPostgreSQL/flexibleServers`
- [ ] Storage Accounts: zero; Role Assignments: zero; unexpected types: zero.

## F. Security and network review

- [ ] Primary VM is Standard_B2als_v2; Ubuntu 24.04 LTS x64; password authentication disabled; system-assigned identity; 32 GiB StandardSSD_LRS OS disk.
- [ ] Inbound NSG policy is exactly TCP 443 from Internet to destination `*`; no extra inbound Allow rule, broad port range, SSH, 8000, or 5432.
- [ ] VNet is 10.20.0.0/16; app subnet is 10.20.1.0/24; PostgreSQL subnet is 10.20.2.0/24 and delegated correctly.
- [ ] Public IP is Standard, Static, IPv4.
- [ ] PostgreSQL is private, Standard_B1ms Burstable, version 16, 32 GiB, HA disabled, geo-redundant backup disabled, 7-day retention.
- [ ] Private DNS zone and VNet link are present and match the preview.
- [ ] Microsoft.Storage remains NotRegistered; Blob deployment remains disabled.
- [ ] I understand public SSH remains disabled and no Bastion is included.

## G. Production credential readiness

- [ ] Owner-controlled persistent SSH public/private key pair exists outside Git and is recoverable by the owner.
- [ ] Private key is owner-owned and mode 0600 or stricter; public/private pair matches.
- [ ] Strong PostgreSQL administrator password is stored in the owner-controlled secure credential store.
- [ ] The production parameter path uses only the owner’s durable credentials; validation-only credentials are never reused.
- [ ] No private key, password, token, or Azure authentication cache will be committed or logged.

## H. Partial-failure and billing-risk acknowledgment

- [ ] I understand quota, capacity, policy, provider, network, or PostgreSQL failure may leave billable partial resources.
- [ ] I understand there will be no automatic retry, SKU/region substitution, resource deletion, quota request, or provider registration.
- [ ] I understand a failed attempt requires read-only inventory/state inspection and owner review before any further action.
- [ ] I understand an Azure quota pass does not guarantee physical VM allocation capacity.

## I. Explicit Gate B deployment authorization

Complete only after independent review of the exact committed deployment plan, fresh billing confirmation, production credentials, and final What-If.

- [ ] I am the owner and explicitly authorize Gate B deployment of the reviewed nine-resource plan.
- [ ] I reviewed the final What-If and accept the exact resource names, IDs, types, and costs.
- [ ] I confirm no material billing, region, subscription, IaC hash, policy, quota, or security drift occurred.
- [ ] Owner name: ____________________
- [ ] Date/time and review reference: ____________________
- [ ] Specific deployment plan/commit reviewed: ____________________

This checklist records future owner intent only. Completing Gate A, filling this checklist, or receiving ChatGPT approval does not itself perform or authorize an automated deployment. A separate owner action must approve the reviewed Gate B plan.

## J. Postdeployment verification requirements

- [ ] Subscription-scope deployment succeeded and the approved resource group exists.
- [ ] All nine resources exist once, with names and IDs matching the approved preview; no unexpected infrastructure resources exist.
- [ ] VM size, Ubuntu image, identity, disk size/SKU, network interface and public-IP attachment match the approved values.
- [ ] NSG exposes only the approved inbound TCP 443 rule; no public SSH, 8000, or 5432.
- [ ] VNet/subnet CIDRs, PostgreSQL delegation, and private DNS zone/link match the approved plan.
- [ ] PostgreSQL SKU/version/storage/private access/HA/backup settings match the approved plan.
- [ ] No Storage Account or Role Assignment exists; Microsoft.Storage remains NotRegistered.
- [ ] Associated VM OS disk is identified, linked to the VM, and included in inventory and cost review.
- [ ] Any mismatch or partial state stops further work for owner review; no application or Phase 4D work begins automatically.
