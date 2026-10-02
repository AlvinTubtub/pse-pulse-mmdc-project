# Azure Infrastructure Scaffolding (Phase 1)

> [!CAUTION]
> **DO NOT EXECUTE THESE TEMPLATES.**
> **DO NOT RUN `az deployment` OR PROVISION ANY AZURE RESOURCES.**
> This directory contains infrastructure-as-code scaffolding strictly for architectural review and future deployment planning. No resources should be created until explicitly approved.

---

## Intended Target Architecture ($0 Cost Guardrail)

Every resource defined in these templates is sized strictly around the free allowances available under **Azure for Students**:

| Resource | Primary Target SKU | Fallback SKU | Sizing & Allowance Constraints |
| :--- | :--- | :--- | :--- |
| **Virtual Machine** | `Standard_B2ats_v2` | `Standard_B1s` | 2 vCPU, 1 GiB RAM, x86_64 AMD EPYC |
| **OS Managed Disk** | Premium SSD P6 (64 GiB) | Standard SSD (64 GiB) | Exactly 1 OS disk within free tier |
| **Public IPv4** | 1 Static Public IP | — | Single public IP allocated to the VM NIC |
| **PostgreSQL** | Flexible Server `Standard_B1ms` | — | Burstable 1 vCPU, 2 GiB RAM, **32 GB storage ceiling**, public access + single-IP firewall |
| **Blob Storage** | `Standard_LRS` (Hot Tier) | — | Lightweight backups & snapshots, strictly **< 5 GB** |
| **Virtual Network** | 1 VNet (`10.0.0.0/16`) | — | 1 Subnet (`10.0.1.0/24` for VM; no delegated DB subnet) |
| **Network Security Group**| Port 22 (SSH), 80 (HTTP), 443 (HTTPS) | — | SSH restricted to administrator IP in production |

---

## Networking Design Rationale: Public Access with Single-IP Firewall

> **Why Public PostgreSQL Networking is Used:**  
> This personal deployment chooses PostgreSQL public access with a single-IP firewall and mandatory TLS to avoid provisioning an Azure Private DNS zone outside the explicitly approved free-service allowances.

- **Strict Single-IP Firewall:** The Azure PostgreSQL firewall allows incoming connections exclusively from the single static public IPv4 of the PSE Pulse VM.
- **Zero Public Exposure:** `0.0.0.0/0` is strictly forbidden. Unrestricted "Allow Azure services" access is disabled. Arbitrary client IPs cannot access the database listener.
- **Mandatory TLS:** All connections enforce SSL/TLS encryption (`sslmode=require`).
- **No Azure Private DNS Metering:** Eliminates the metered private DNS zone resource that VNet integration would otherwise require.
- **No Delegated Subnet:** The VNet requires only a standard subnet for the host VM.

---

## Parameter & Secret Handling

No secrets, private keys, subscription IDs, or passwords are hardcoded in source control:
- `adminUsername`: Configured at deployment time (e.g. `psepulse`).
- `adminSshPublicKey`: OpenSSH public key (`ssh-ed25519 ...`) provided at deployment time.
- `dbAdminPassword`: Strong password supplied via secure parameter or Azure Key Vault during actual provisioning.
- `allowedSshSourceIp`: In `parameters.example.json`, set to your personal workstation public IP CIDR (e.g. `203.0.113.50/32`) rather than `*` (any) to maintain zero-trust perimeter defense.

---

## Future Dry-Run Validation Command (When Approved)

```bash
# Example future pre-flight validation ONLY:
az deployment group validate \
  --resource-group rg-pse-pulse-prod \
  --template-file infrastructure/azure/main.bicep \
  --parameters @infrastructure/azure/parameters.json
```
