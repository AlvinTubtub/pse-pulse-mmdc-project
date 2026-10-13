#!/usr/bin/env bash
# Install a prebuilt, hash-verified static export on the existing VM.
# This script does not build, call Azure, change the NSG, or start Nginx.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <verified-artifact-directory> <full-reviewed-commit-sha>" >&2
  exit 2
fi
ARTIFACT_DIR="$1"
COMMIT_SHA="$2"
[[ "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'A full lowercase Git SHA is required.' >&2; exit 2; }
[[ "${EUID}" -eq 0 ]] || { echo 'Run only through an approved management channel as root.' >&2; exit 1; }

python3 "${ROOT}/infrastructure/scripts/release_manager.py" deploy-static \
  "$ARTIFACT_DIR" /var/www/pse-pulse --commit "$COMMIT_SHA"
echo 'Static release verified and atomically activated. Nginx was not started or reloaded.'
