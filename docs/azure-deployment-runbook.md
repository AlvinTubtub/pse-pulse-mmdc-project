# Azure Deployment Runbook

This runbook follows the currently reported Phase 4C.3 infrastructure baseline and Phase 4D application runtime. It replaces the superseded provisioning outline. It is preparatory documentation and does not grant authorization to run Azure commands or deploy the application.

Use the existing East Asia VM `vm-psepulse-aui7qjkkdw4ye` (`Standard_B2als_v2`) and private PostgreSQL server `pg-psepulse-aui7qjkkdw4ye` (PostgreSQL 16, `Standard_B1ms`) only. Preserve the USD 0 personal out-of-pocket limit. The owner-reported USD 100 credit must be checked again before live work.

Read [the current Phase 4D runbook](azure-deployment.md) for:

- Clean commit and release artifact preparation.
- Azure VM Run Command based bootstrap with no public SSH.
- Private PostgreSQL/TLS, secret delivery, and explicit Alembic gates.
- Official historical source and model artifact provenance.
- HTTPS acceptance requirements and disabled service timers.
- Stop conditions and independent approvals for activation and inference.

Never run old `infrastructure/azure` provisioning templates as part of Phase 4D. Do not create resources, register providers, change quotas/billing, alter NSG rules, expose port 22, or upgrade the subscription to Pay-As-You-Go.
