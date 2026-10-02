#!/usr/bin/env bash
# ==============================================================================
# PSE Pulse — Static Frontend Build & Sync Script
# ==============================================================================
# Builds Next.js static export and copies files to Nginx web root.
# ==============================================================================

set -euo pipefail

DEPLOY_DIR="/var/www/pse-pulse/out"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo ">>> Building Next.js static export..."
cd "${APP_DIR}/frontend"
npm ci
npm run build

echo ">>> Syncing static build to ${DEPLOY_DIR}..."
sudo mkdir -p "${DEPLOY_DIR}"
sudo rsync -av --delete out/ "${DEPLOY_DIR}/"
sudo chown -R www-data:www-data "${DEPLOY_DIR}"

echo ">>> Reloading Nginx..."
sudo systemctl reload nginx

echo ">>> Static frontend deployment complete!"
