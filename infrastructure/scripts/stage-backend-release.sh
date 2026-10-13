#!/usr/bin/env bash
# Install isolated production API and inference environments for one staged release.
# Intended for a later reviewed VM Run Command; this file was not executed here.
set -Eeuo pipefail
IFS=$'\n\t'

APP_ROOT=/opt/pse-pulse
if [[ $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Usage: $0 <full-reviewed-commit-sha>" >&2
  exit 2
fi
COMMIT_SHA="$1"
RELEASE="${APP_ROOT}/releases/${COMMIT_SHA}"
API_ENV="${RELEASE}/backend/.venv-api"
INFERENCE_ENV="${RELEASE}/backend/.venv-inference"
MANAGER="${RELEASE}/infrastructure/scripts/release_manager.py"
API_LOCK="${RELEASE}/backend/requirements-production-api.lock"
INFERENCE_LOCK="${RELEASE}/backend/requirements-production-inference.lock"

[[ "${EUID}" -eq 0 ]] || { echo 'Run only through an approved management channel as root.' >&2; exit 1; }
[[ -d "$RELEASE" && ! -L "$RELEASE" ]] || { echo 'Staged release directory is missing or linked.' >&2; exit 1; }
[[ ! -e "${APP_ROOT}/current" || "$(readlink -f "${APP_ROOT}/current")" != "$(readlink -f "$RELEASE")" ]] || {
  echo 'Refusing to change dependencies in the active release.' >&2; exit 1;
}
[[ ! -e "$API_ENV" && ! -e "$INFERENCE_ENV" ]] || { echo 'A virtual environment already exists; refusing to mutate this release.' >&2; exit 1; }
command -v python3.12 >/dev/null || { echo 'Ubuntu Python 3.12 is required.' >&2; exit 1; }
[[ -x "$MANAGER" || -f "$MANAGER" ]] || { echo 'Release verifier is missing.' >&2; exit 1; }
[[ -s "$API_LOCK" && -s "$INFERENCE_LOCK" ]] || {
  echo 'Reviewed hash-pinned Python 3.12 API and inference lockfiles are required; refusing range-based installation.' >&2
  exit 1
}

# Lock files may contain package pins and hashes only. Reject direct URLs and
# pip directives so a reviewed lock cannot silently switch package sources.
python3.12 - "$API_LOCK" "$INFERENCE_LOCK" <<'PY'
from pathlib import Path
import re
import sys

for raw_path in sys.argv[1:]:
    path = Path(raw_path)
    for number, raw_line in enumerate(path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if ("--index-url" in lowered or "--extra-index-url" in lowered
                or "--find-links" in lowered or "--trusted-host" in lowered
                or " @ http:" in lowered or " @ https:" in lowered
                or "git+" in lowered or "://" in lowered):
            raise SystemExit(f"Refusing non-index package source in {path.name}:{number}.")
        if line.startswith("--hash="):
            if not re.fullmatch(r"--hash=sha256:[0-9a-fA-F]{64}\\?", line):
                raise SystemExit(f"Refusing invalid package hash in {path.name}:{number}.")
            continue
        if line.startswith("-"):
            raise SystemExit(f"Refusing pip option in {path.name}:{number}.")
PY

python3 "$MANAGER" verify "$RELEASE" --commit "$COMMIT_SHA" --type backend
install -d -o root -g psepulse -m 0750 "$API_ENV" "$INFERENCE_ENV"
python3.12 -m venv --copies "$API_ENV"
python3.12 -m venv --copies "$INFERENCE_ENV"
install_locked_requirements() {
  local python_bin="$1" lock_file="$2"
  env -u PIP_INDEX_URL -u PIP_EXTRA_INDEX_URL -u PIP_FIND_LINKS \
    -u PIP_TRUSTED_HOST -u PIP_NO_INDEX PIP_CONFIG_FILE=/dev/null \
    "$python_bin" -m pip install --disable-pip-version-check --no-cache-dir \
      --index-url https://pypi.org/simple \
      --require-hashes -r "$lock_file"
}
install_locked_requirements "${API_ENV}/bin/python" "$API_LOCK"
install_locked_requirements "${INFERENCE_ENV}/bin/python" "$INFERENCE_LOCK"

chown -R root:psepulse "$API_ENV" "$INFERENCE_ENV"
find "$API_ENV" "$INFERENCE_ENV" -type d -exec chmod 0750 {} +
find "$API_ENV" "$INFERENCE_ENV" -type f -exec chmod 0640 {} +
find "$API_ENV/bin" "$INFERENCE_ENV/bin" -type f -exec chmod 0750 {} +
python3 "$MANAGER" verify "$RELEASE" --commit "$COMMIT_SHA" --type backend
echo 'Production API and inference environments staged and verified. No service was activated or restarted.'
