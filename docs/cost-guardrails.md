# Cost Guardrails & Free-Tier Budget Protection

> [!IMPORTANT]
> **Primary Objective:** Maintain **\$0 monthly infrastructure spend** by operating strictly within the active free-tier allowances of an **Azure for Students** subscription.
>
> Cloud service pricing and free-tier allowances are determined by Microsoft and are subject to change. Always manually inspect your current Azure subscription allowances, remaining credits, and active pricing schedules in the Azure Portal before initiating any deployment.

---

## 1. Intended Azure SKUs & Free-Tier Inventory

All planned cloud resources for PSE Pulse are pinned to specific burstable SKUs:

| Component | Target SKU / Size | Constraints & Ceilings |
| :--- | :--- | :--- |
| **Virtual Machine** | `Standard_B2ats_v2` (Primary) <br> `Standard_B1s` (Fallback) | Exactly **1 VM instance**. Sized for 2 vCPU, 1 GiB RAM (or 1 vCPU, 1 GiB RAM). |
| **OS Managed Disk** | Premium SSD P6 (64 GiB) | Exactly **1 OS disk**. Fits within 64 GiB free managed disk tier. |
| **Public IP Address** | 1 Static IPv4 (`Standard` SKU) | Exactly **1 IP address** attached to the VM NIC. **Account-visible allowance: 1,500 public IP address-hours/month** on the current student dashboard. *(Note: Do not generalize this as a permanent guarantee across all Azure accounts; actual deployment must verify the active subscription dashboard as the final source of truth before provisioning).* |
| **Database Server** | Azure Database for PostgreSQL Flexible Server | Burstable `Standard_B1ms` tier. **32 GB storage ceiling**. Auto-grow disabled. Public access with single-IP firewall to avoid metered Azure Private DNS zones. |
| **Blob Storage** | Azure Storage Account (`Standard_LRS`, Hot) | Snapshots & backups kept strictly **< 5 GB**. |
| **Network Security** | Network Security Group (NSG) | Default free NSG; ports 22, 80, 443 only. |

---

## 2. Hard Architectural Ceilings

### A. The Single-VM Limit
PSE Pulse will never deploy more than **one virtual machine**. All production host tasks (Nginx reverse proxy, static file delivery, FastAPI Uvicorn application service, and systemd batch execution timers) co-exist on the single host.

### B. PostgreSQL 32-GB Storage Ceiling
Azure Database for PostgreSQL Flexible Server offers a free burstable allowance with up to 32 GiB of storage.
- Auto-grow storage is **disabled** (`autoGrow: 'Disabled'`) in Bicep templates to prevent accidental scaling beyond the 32-GB free bracket.
- Old temporary ingestion logs and ephemeral pipeline runs are pruned to keep database size well under capacity.

### C. Blob Storage Ceiling (< 5 GB)
Azure Blob Storage provides 5 GB of free LRS storage.
- Storage is utilized solely for lightweight JSON/Parquet daily snapshot exports.
- Retention policies ensure backups older than 90 days are deleted.

---

## 3. Explicitly Excluded Services

Under no circumstances should the following high-cost Azure offerings be introduced:
- **No Azure Kubernetes Service (AKS)** (incurs node pool, load balancing, and management costs).
- **No Azure Container Apps (ACA)**.
- **No Paid Azure App Service Plans** (Basic, Standard, Premium).
- **No Azure Redis Cache** (FastAPI runs in-memory caching or uses SQLite/PostgreSQL).
- **No Azure Cosmos DB**.
- **No Azure Service Bus or Event Hubs**.
- **No Azure Container Registry (ACR)** (builds occur directly on host via Git and standard Linux tools).
- **No Azure Application Gateway or Standard Load Balancers** (Nginx acts as the load balancer and reverse proxy).
- **No Azure Private DNS Zones or Private Resolvers** (PostgreSQL uses public access with single-IP firewall to avoid metered private DNS zone and resolution billing).
- **No GPU Compute Instances** (inference is performed via lightweight mathematical stubs).
- **No Premium Log Analytics / Azure Monitor Ingestion** (logs are written locally to `journald` and rotated via `logrotate`).

---

## 4. Operational Safety Warnings

> [!WARNING]
> **Azure Budget Alerts Do NOT Automatically Stop Resources.**
> Configuring a budget alert (e.g. at \$1.00) in Azure Cost Management will send an email notification when thresholds are approached, but it **will NOT terminate or deallocate** virtual machines or databases automatically.

### Recommended Safety Actions Before Deployment:
1. **Spending Limit Protection:** Verify that the subscription has the default Azure for Students Spending Limit active (which suspends resources rather than billing personal credit cards).
2. **Scheduled VM Deallocation:** In non-production testing, configure the Azure VM Auto-Shutdown feature to shut down the VM daily at 22:00 PHT.
3. **Periodic Portal Audits:** Check the Azure Cost Analysis blade weekly to confirm zero accrued charges.
