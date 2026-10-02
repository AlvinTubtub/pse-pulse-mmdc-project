#!/usr/bin/env bash
# ==============================================================================
# PSE Pulse — Manual Pipeline Runner Trigger
# ==============================================================================

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${APP_DIR}"

echo ">>> Triggering PSE Pulse End-of-Day Pipeline..."
"${APP_DIR}/backend/.venv/bin/python" -m backend.pipeline.runner
