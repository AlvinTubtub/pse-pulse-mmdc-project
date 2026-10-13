#!/usr/bin/env bash
# Package one clean, reviewed backend commit for later authenticated transfer.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <full-reviewed-commit-sha> <output-directory>" >&2
  exit 2
fi
COMMIT_SHA="$1"
OUTPUT="$2"
[[ "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'A full lowercase Git SHA is required.' >&2; exit 2; }
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$COMMIT_SHA" ]] || { echo 'Commit does not match the checked out source.' >&2; exit 1; }
git -C "$ROOT" diff --quiet || { echo 'Working tree has unstaged changes; build a reviewed commit.' >&2; exit 1; }
git -C "$ROOT" diff --cached --quiet || { echo 'Index has staged changes; build a reviewed commit.' >&2; exit 1; }
[[ ! -e "$OUTPUT" ]] || { echo 'Output path already exists; refusing to overwrite it.' >&2; exit 1; }
command -v tar >/dev/null || { echo 'tar is required.' >&2; exit 1; }

STAGING="$(mktemp -d)"
cleanup() { rm -rf -- "$STAGING"; }
trap cleanup EXIT
mkdir -p "$STAGING/release"
# Keep the reviewed backend release closure explicit. Activation, its root-run
# configuration gate, the manifest verifier, and runtime assets must travel
# together so a packaged release cannot lose a required fail-closed check.
RELEASE_PATHS=(
  backend
  scripts/phase3b2_verify_bundle.py
  infrastructure/config
  infrastructure/nginx
  infrastructure/systemd
  infrastructure/scripts/activate-backend-release.sh
  infrastructure/scripts/install-model-bundle.sh
  infrastructure/scripts/release_manager.py
  infrastructure/scripts/renew-ip-certificate.sh
  infrastructure/scripts/run-pipeline.sh
  infrastructure/scripts/setup-vm.sh
  infrastructure/scripts/stage-backend-release.sh
  infrastructure/scripts/validate-runtime-config.py
)
git -C "$ROOT" archive "$COMMIT_SHA" "${RELEASE_PATHS[@]}" | tar -x -C "$STAGING/release"
python3 "$ROOT/infrastructure/scripts/release_manager.py" create-manifest \
  "$STAGING/release" --commit "$COMMIT_SHA" --type backend
python3 "$ROOT/infrastructure/scripts/release_manager.py" verify \
  "$STAGING/release" --commit "$COMMIT_SHA" --type backend
mkdir -p "$(dirname "$OUTPUT")"
tar -C "$STAGING/release" -czf "$OUTPUT" .
shasum -a 256 "$OUTPUT"
echo 'Backend release archive created and verified; transfer and activation were not performed.'
