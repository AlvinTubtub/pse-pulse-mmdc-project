#!/usr/bin/env bash
# ==============================================================================
# PSE Pulse — Ubuntu 24.04 LTS VM Provisioning Script
# ==============================================================================
# Target VM SKU: Standard_B2ats_v2 (2 vCPU, 1 GiB RAM)
# Target OS: Ubuntu 24.04 LTS x86_64
#
# DO NOT EXECUTE ON LOCAL DEVELOPMENT MACHINE.
# Intended for future Azure VM initial bootstrap.
# ==============================================================================

set -euo pipefail

echo ">>> [1/7] Updating Ubuntu package lists..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo ">>> [2/7] Installing base runtime packages (Nginx, Python 3.12, Git)..."
sudo apt-get install -y \
    nginx \
    python3.12 \
    python3.12-venv \
    python3-pip \
    git \
    curl \
    ufw \
    fail2ban

echo ">>> [3/7] Creating non-root application user 'psepulse'..."
if ! id -u psepulse >/dev/null 2>&1; then
    sudo useradd -r -s /bin/false -d /opt/pse-pulse psepulse
fi

echo ">>> [4/7] Creating directories..."
sudo mkdir -p /var/www/pse-pulse/out
sudo mkdir -p /opt/pse-pulse
sudo mkdir -p /etc/pse-pulse
sudo chown -R www-data:www-data /var/www/pse-pulse
sudo chown -R psepulse:psepulse /opt/pse-pulse

echo ">>> [5/7] Configuring UFW Firewall (SSH restricted to SSH_ALLOWED_CIDR + HTTP + HTTPS)..."
: "${SSH_ALLOWED_CIDR:?Error: Set SSH_ALLOWED_CIDR to your administrator public IP CIDR before running (e.g. export SSH_ALLOWED_CIDR='203.0.113.10/32')}"
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from "${SSH_ALLOWED_CIDR}" to any port 22 proto tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'
sudo ufw --force enable

echo ">>> [6/7] Configuring Swap (1 GiB) for Low-Memory Safety..."
# A 1 GiB swap file prevents out-of-memory kernel panics on 1 GiB RAM VM
if [ ! -f /swapfile ]; then
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    sudo sysctl vm.swappiness=10
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
fi

echo ">>> [7/7] VM base provisioning complete!"
echo "Next: Deploy Nginx configuration, systemd services, and application code."
