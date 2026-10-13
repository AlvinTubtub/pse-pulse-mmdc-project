#!/usr/bin/env bash
# Production-only scheduler wrapper. The Python entry point validates manifests,
# the reviewed PSE calendar, model gates, source coverage, and output lineage.
set -Eeuo pipefail
IFS=$'\n\t'

APP_DIR=/opt/pse-pulse/current
[[ -d "$APP_DIR" && -x "$APP_DIR/backend/.venv-inference/bin/python" ]] || {
  echo 'Verified active application release is unavailable.' >&2
  exit 1
}
exec "$APP_DIR/backend/.venv-inference/bin/python" -m backend.pipeline.production_runner \
  --scheduled --reconcile-pending
