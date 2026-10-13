#!/usr/bin/env bash
# Activate a previously transferred and verified backend release directory.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: $0 <full-reviewed-commit-sha>" >&2
  exit 2
fi
[[ "${EUID}" -eq 0 ]] || { echo 'Run only through an approved management channel as root.' >&2; exit 1; }
python3 "${ROOT}/infrastructure/scripts/validate-runtime-config.py"
python3 "${ROOT}/infrastructure/scripts/release_manager.py" activate \
  /opt/pse-pulse --commit "$1" --type backend
echo 'Backend release atomically activated. Services were not restarted.'
