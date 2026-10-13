#!/usr/bin/env bash
# Install only the externally reviewed, hash-accepted model bundle. No activation.
set -Eeuo pipefail
IFS=$'\n\t'

APP_DIR=/opt/pse-pulse/current
MODEL_ROOT=/var/lib/pse-pulse/models
if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <staged-bundle-directory> <approved-bundle-version>" >&2
  exit 2
fi
SOURCE="$1"
VERSION="$2"
[[ "${EUID}" -eq 0 ]] || { echo 'Run only through an approved management channel as root.' >&2; exit 1; }
[[ -d "$SOURCE" && ! -L "$SOURCE" ]] || { echo 'Staged model bundle must be a real directory.' >&2; exit 1; }
[[ "$VERSION" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[a-z0-9-]+$ ]] || { echo 'Invalid model bundle version.' >&2; exit 1; }
[[ -x "$APP_DIR/backend/.venv-inference/bin/python" ]] || { echo 'Verified inference environment is unavailable.' >&2; exit 1; }

TARGET="${MODEL_ROOT}/${VERSION}"
if [[ -e "$TARGET" ]]; then
  "$APP_DIR/backend/.venv-inference/bin/python" "${APP_DIR}/scripts/phase3b2_verify_bundle.py" --bundle "$TARGET" >/dev/null
  echo 'The exact approved model bundle is already installed; no files changed.'
  exit 0
fi

# Verify before copying. The verifier checks the accepted manifest and every file hash.
"$APP_DIR/backend/.venv-inference/bin/python" "${APP_DIR}/scripts/phase3b2_verify_bundle.py" --bundle "$SOURCE" >/dev/null
STAGING="${MODEL_ROOT}/.${VERSION}.stage.$$"
cleanup() { [[ -d "$STAGING" ]] && rm -rf -- "$STAGING"; }
trap cleanup EXIT
install -d -o root -g psepulse -m 0750 "$STAGING"
cp -a --no-preserve=ownership "$SOURCE"/. "$STAGING"/
chown -R root:psepulse "$STAGING"
find "$STAGING" -type d -exec chmod 0750 {} +
find "$STAGING" -type f -exec chmod 0640 {} +
"$APP_DIR/backend/.venv-inference/bin/python" "${APP_DIR}/scripts/phase3b2_verify_bundle.py" --bundle "$STAGING" >/dev/null
mv -- "$STAGING" "$TARGET"
trap - EXIT
echo 'Model bundle installed and verified. No database registration, activation, or inference was performed.'
