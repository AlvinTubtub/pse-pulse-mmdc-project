#!/usr/bin/env bash
# Idempotent, non-deploying bootstrap for the existing Ubuntu 24.04 VM.
# Run only after separate owner approval through Azure VM Run Command.
set -Eeuo pipefail
IFS=$'\n\t'

log() { printf '[pse-pulse-bootstrap] %s\n' "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }
trap 'rc=$?; log "bootstrap failed at line ${LINENO} (exit ${rc})" >&2; exit "$rc"' ERR

[[ "$(. /etc/os-release && printf '%s' "${ID:-}")" == ubuntu ]] || fail 'Ubuntu is required.'
[[ "$(. /etc/os-release && printf '%s' "${VERSION_ID:-}")" == 24.04 ]] || fail 'Ubuntu 24.04 is required.'
[[ "$(uname -m)" == x86_64 ]] || fail 'The approved VM architecture is x86_64.'

# The approved VM has 4 GiB RAM. Read the host value when available and refuse
# an unexpectedly smaller target instead of applying the retired 1 GiB tuning.
mem_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
(( mem_kib >= 3 * 1024 * 1024 )) || fail 'Expected the approved 4 GiB class VM; refusing outdated low-memory setup.'

[[ "${EUID}" -eq 0 ]] || fail 'Run as root through the approved management channel.'

log '[1/5] Installing only runtime prerequisites.'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  nginx \
  python3 \
  python3-venv \
  python3-pip \
  rsync

log '[2/5] Ensuring isolated non-login service accounts exist.'
if ! getent group psepulse >/dev/null; then
  groupadd --system psepulse
fi
if ! id -u psepulse >/dev/null 2>&1; then
  useradd --system --gid psepulse --home-dir /opt/pse-pulse \
    --shell /usr/sbin/nologin --no-create-home psepulse
fi
usermod --gid psepulse --home /opt/pse-pulse --shell /usr/sbin/nologin psepulse
for service_account in psepulse-api psepulse-eod psepulse-migration psepulse-bootstrap; do
  if ! getent group "$service_account" >/dev/null; then
    groupadd --system "$service_account"
  fi
  if ! id -u "$service_account" >/dev/null 2>&1; then
    useradd --system --gid "$service_account" --groups psepulse --home-dir /nonexistent \
      --shell /usr/sbin/nologin --no-create-home "$service_account"
  else
    usermod --gid "$service_account" --append --groups psepulse \
      --home /nonexistent --shell /usr/sbin/nologin "$service_account"
  fi
done

log '[3/5] Creating restricted release, data, and configuration directories.'
install -d -o root -g psepulse -m 0750 \
  /opt/pse-pulse /opt/pse-pulse/releases /var/lib/pse-pulse \
  /var/lib/pse-pulse/calendar /var/lib/pse-pulse/models
install -d -o root -g psepulse-eod -m 0750 \
  /var/lib/pse-pulse/incoming /var/lib/pse-pulse/approvals
install -d -o root -g psepulse-bootstrap -m 0750 \
  /var/lib/pse-pulse/bootstrap-source
install -d -o root -g root -m 0750 /etc/pse-pulse
install -d -o root -g root -m 0750 /etc/pse-pulse/tls
install -d -o root -g www-data -m 0750 \
  /var/www/pse-pulse /var/www/pse-pulse/releases
install -d -o root -g root -m 0700 /var/lib/lego

log '[4/5] Keeping the default HTTP site stopped until reviewed HTTPS is installed.'
rm -f /etc/nginx/sites-enabled/default
systemctl disable --now nginx.service >/dev/null 2>&1 || true

log '[5/5] Bootstrap complete. No application unit, timer, database migration, firewall, or Azure resource was changed.'
