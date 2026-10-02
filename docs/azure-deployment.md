# Azure Deployment Runbook (Future Phase Execution)

> [!CAUTION]
> **DO NOT EXECUTE THESE COMMANDS DURING PHASE 1.**
> This runbook is a procedural reference documenting how the application will be provisioned and deployed in a future phase once local review has been completed and approved.

---

## 1. Prerequisites Checklist

Before initiating deployment:
1. Active **Azure for Students** subscription with available credit allocation.
2. Verified spending limits enabled in the Azure Portal.
3. Azure CLI (`az`) installed on local development workstation.
4. SSH keypair generated (`ssh-keygen -t ed25519 -C "psepulse@azure"`).
5. Reviewed `infrastructure/azure/main.bicep` and populated `parameters.json`.

---

## 2. Phase A: Provisioning Infrastructure via Bicep

### Step 1: Login and Set Subscription
```bash
az login
az account set --subscription "Azure for Students"
```

### Step 2: Create Azure Resource Group
```bash
az group create \
  --name rg-pse-pulse-prod \
  --location southeastasia
```

### Step 3: Validate Bicep Template (Dry Run)
```bash
az deployment group validate \
  --resource-group rg-pse-pulse-prod \
  --template-file infrastructure/azure/main.bicep \
  --parameters @infrastructure/azure/parameters.json
```

### Step 4: Execute Deployment
```bash
az deployment group create \
  --resource-group rg-pse-pulse-prod \
  --template-file infrastructure/azure/main.bicep \
  --parameters @infrastructure/azure/parameters.json
```

---

> [!NOTE]
> **Strict-Free Networking Architecture:**  
> This personal deployment chooses PostgreSQL public access with a single-IP firewall and mandatory TLS to avoid provisioning an Azure Private DNS zone outside the explicitly approved free-service allowances. The PostgreSQL Flexible Server firewall rule permits traffic exclusively from the single static public IPv4 assigned to the host VM.

---

Once the VM is provisioned:

### Step 1: Connect to VM via SSH
```bash
ssh -i ~/.ssh/id_ed25519 psepulse@<VM_PUBLIC_IP>
```

### Step 2: Run Bootstrap Setup Script
```bash
git clone https://github.com/AlvinTubtub/pse-pulse-mmdc-project.git /tmp/pse-pulse
sudo bash /tmp/pse-pulse/infrastructure/scripts/setup-vm.sh
```

### Step 3: Configure Application Environment File
```bash
sudo cp /tmp/pse-pulse/.env.example /etc/pse-pulse/.env
sudo nano /etc/pse-pulse/.env
```
Ensure `DATABASE_URL` is set to the Azure PostgreSQL Flexible Server connection string and demo mode is strictly disabled:
```env
DATABASE_URL=postgresql+psycopg://pseadmin:<PASSWORD>@psql-pse-pulse-prod-...postgres.database.azure.com:5432/pse_pulse_prod?sslmode=require
ENVIRONMENT=production
DEBUG=false
DEMO_MODE=false
```
> [!CAUTION]
> **Production Demo-Data Prevention:**
> `DEMO_MODE` must be `false` when `ENVIRONMENT=production`. The application configuration enforces this with a hard validation failure (`ValueError`), preventing synthetic market records from ever polluting production.

### Step 4: Set Up Python Backend Virtual Environment
```bash
sudo rsync -av --exclude 'frontend' /tmp/pse-pulse/ /opt/pse-pulse/
cd /opt/pse-pulse
python3.12 -m venv backend/.venv
./backend/.venv/bin/pip install --upgrade pip
./backend/.venv/bin/pip install -r backend/requirements.txt
sudo chown -R psepulse:psepulse /opt/pse-pulse
```

### Step 5: Run Database Migrations (Mandatory in Production)
> [!IMPORTANT]
> **Production Schema Governance:**
> In production (`ENVIRONMENT=production`), FastAPI startup intentionally skips `Base.metadata.create_all` and skips demo data seeding when `DEMO_MODE=false`. Alembic is the authoritative and required mechanism for creating and migrating database tables before starting the backend service.

```bash
sudo -u psepulse /opt/pse-pulse/backend/.venv/bin/alembic -c /opt/pse-pulse/backend/alembic.ini upgrade head
```
Verify that migration completed to `head`:
```bash
sudo -u psepulse /opt/pse-pulse/backend/.venv/bin/alembic -c /opt/pse-pulse/backend/alembic.ini current
```

---

## 4. Phase C: Nginx & Systemd Service Activation

### Step 1: Install Nginx Configuration
```bash
sudo cp /opt/pse-pulse/infrastructure/nginx/pse-pulse.conf /etc/nginx/sites-available/pse-pulse.conf
sudo ln -sf /etc/nginx/sites-available/pse-pulse.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### Step 2: Enable & Start Systemd Services
```bash
sudo cp /opt/pse-pulse/infrastructure/systemd/pse-pulse-api.service /etc/systemd/system/
sudo cp /opt/pse-pulse/infrastructure/systemd/pse-pulse-eod.service /etc/systemd/system/
sudo cp /opt/pse-pulse/infrastructure/systemd/pse-pulse-eod.timer /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now pse-pulse-api.service
sudo systemctl enable --now pse-pulse-eod.timer
```

---

## 5. Phase D: Frontend Static Export Delivery

Build the static export locally (or in CI) with production environment flags and transfer to the VM:
```bash
cd frontend
npm ci
# Build with same-origin API routing and zero synthetic fallbacks:
NEXT_PUBLIC_API_URL="" NEXT_PUBLIC_DEMO_MODE=false npm run build
rsync -avz -e "ssh -i ~/.ssh/id_ed25519" out/ psepulse@<VM_PUBLIC_IP>:/tmp/frontend-out/
ssh -i ~/.ssh/id_ed25519 psepulse@<VM_PUBLIC_IP> "sudo rsync -av --delete /tmp/frontend-out/ /var/www/pse-pulse/out/ && sudo chown -R www-data:www-data /var/www/pse-pulse/out"
```

---

## 6. Phase E: Verification & Health Checks

```bash
# Check FastAPI service status
sudo systemctl status pse-pulse-api.service

# Check systemd timer
systemctl list-timers | grep pse-pulse

# Verify health endpoint via HTTP
curl -i http://localhost/health
curl -i http://localhost/api/v1/system/status
```
