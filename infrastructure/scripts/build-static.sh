#!/usr/bin/env bash
# Build a production static export on a workstation or CI runner, never on the VM.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND_DIR="${ROOT}/frontend"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <full-reviewed-commit-sha>" >&2
  exit 2
fi
COMMIT_SHA="$1"
[[ "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo 'A full lowercase Git SHA is required.' >&2; exit 2; }
git -C "$ROOT" diff --quiet || { echo 'Working tree has unstaged changes; build a reviewed commit.' >&2; exit 1; }
git -C "$ROOT" diff --cached --quiet || { echo 'Index has staged changes; build a reviewed commit.' >&2; exit 1; }
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$COMMIT_SHA" ]] || { echo 'Commit does not match the checked out source.' >&2; exit 1; }
command -v node >/dev/null || { echo 'Node.js is required on the build host.' >&2; exit 1; }
command -v npm >/dev/null || { echo 'npm is required on the build host.' >&2; exit 1; }

cd "$FRONTEND_DIR"
export NEXT_PUBLIC_DEMO_MODE=false
export NEXT_PUBLIC_API_URL=
npm ci
npm run lint
npm run typecheck
npm run build

[[ -s out/index.html ]] || { echo 'Static export is missing index.html.' >&2; exit 1; }
[[ -d out/_next/static ]] || { echo 'Static export is missing Next.js assets.' >&2; exit 1; }
python3 "${ROOT}/infrastructure/scripts/release_manager.py" create-manifest \
  out --commit "$COMMIT_SHA" --type frontend --demo-mode false
python3 "${ROOT}/infrastructure/scripts/release_manager.py" verify \
  out --commit "$COMMIT_SHA" --type frontend
echo 'Static frontend artifact is ready for an independently approved transfer.'
