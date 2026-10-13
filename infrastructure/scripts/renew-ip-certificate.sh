#!/usr/bin/env bash
# Lego TLS-ALPN renewal for a reviewed IP certificate. Never run in Phase 4D.1.
set -Eeuo pipefail
IFS=$'\n\t'

CONFIG=/etc/pse-pulse/acme.env
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || { echo 'ACME configuration is missing.' >&2; exit 1; }
[[ "$(stat -c '%a' "$CONFIG")" == 600 ]] || { echo 'ACME configuration must be mode 0600.' >&2; exit 1; }
[[ "$(stat -c '%u' "$CONFIG")" == 0 ]] || { echo 'ACME configuration must be owned by root.' >&2; exit 1; }
# shellcheck disable=SC1090
source "$CONFIG"

: "${ACME_EMAIL:?ACME_EMAIL is required}"
: "${ACME_IP:?ACME_IP must be the owner-verified VM public IP}"
: "${ACME_DIRECTORY_URL:?ACME_DIRECTORY_URL must be explicitly set}"
: "${LEGO_VERSION:?LEGO_VERSION must pin the reviewed lego v5 release}"
: "${LEGO_SHA256:?LEGO_SHA256 must pin the reviewed lego executable}"
ACME_ALLOW_PRODUCTION="${ACME_ALLOW_PRODUCTION:-false}"
LEGO_BIN="${LEGO_BIN:-/usr/local/bin/lego}"
LEGO_PATH="${LEGO_PATH:-/var/lib/lego}"
TLS_DIR=/etc/pse-pulse/tls
CURRENT_LINK="${TLS_DIR}/current"
CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

[[ "$ACME_ALLOW_PRODUCTION" == true || "$ACME_ALLOW_PRODUCTION" == false ]] || { echo 'Invalid production ACME gate.' >&2; exit 1; }
if [[ "$ACME_DIRECTORY_URL" == https://acme-staging-v02.api.letsencrypt.org/directory ]]; then
  echo 'Staging certificates are validated in an isolated staging workspace and are never installed into Nginx.' >&2
  exit 20
fi
if [[ "$ACME_DIRECTORY_URL" == https://acme-v02.api.letsencrypt.org/directory && "$ACME_ALLOW_PRODUCTION" != true ]]; then
  echo 'Production ACME is disabled until a separate owner approval.' >&2
  exit 20
fi
if [[ "$ACME_DIRECTORY_URL" != https://acme-v02.api.letsencrypt.org/directory && "$ACME_DIRECTORY_URL" != https://acme-staging-v02.api.letsencrypt.org/directory ]]; then
  echo 'Unapproved ACME directory.' >&2
  exit 1
fi
python3 - "$ACME_IP" <<'PY'
import ipaddress, sys
ipaddress.ip_address(sys.argv[1])
PY
[[ "$LEGO_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo 'LEGO_SHA256 must be a lowercase SHA-256.' >&2; exit 1; }
[[ "$LEGO_VERSION" =~ ^5\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$ ]] || { echo 'LEGO_VERSION must be an exact reviewed lego v5 release.' >&2; exit 1; }
[[ -x "$LEGO_BIN" && -f "$CA_BUNDLE" ]] || { echo 'Pinned lego binary or system CA bundle is unavailable.' >&2; exit 1; }
[[ "$(sha256sum "$LEGO_BIN" | awk '{print $1}')" == "$LEGO_SHA256" ]] || { echo 'lego executable SHA-256 does not match the reviewed pin.' >&2; exit 1; }
actual_lego_version="$("$LEGO_BIN" --version | awk 'NR == 1 {print $3}')"
[[ "$actual_lego_version" == "$LEGO_VERSION" ]] || { echo 'lego version output does not match the reviewed version pin.' >&2; exit 1; }

CERT="${LEGO_PATH}/certificates/${ACME_IP}.crt"
KEY="${LEGO_PATH}/certificates/${ACME_IP}.key"
[[ -s "$CERT" && -s "$KEY" ]] || { echo 'No certificate exists; initial issuance requires a separately reviewed staging procedure.' >&2; exit 1; }

if openssl x509 -in "$CURRENT_LINK/fullchain.pem" -checkip "$ACME_IP" -checkend 259200 -noout >/dev/null 2>&1; then
  echo 'Current IP certificate has more than 72 hours remaining; renewal is not due.'
  exit 0
fi

previous_target=""
if [[ -L "$CURRENT_LINK" ]]; then
  previous_target="$(readlink -f "$CURRENT_LINK")"
  [[ "$previous_target" == "$TLS_DIR"/* && -d "$previous_target" ]] || { echo 'Current TLS target is outside its managed directory.' >&2; exit 1; }
elif [[ -e "$CURRENT_LINK" ]]; then
  echo 'Current TLS path must be a managed symbolic link.' >&2
  exit 1
fi

was_active=false
systemctl is-active --quiet nginx.service && was_active=true || true
nginx_stopped=false
certificate_switched=false
staging_dir=""
target_dir=""
restore_safe_nginx() {
  local rc=$?
  if [[ "$certificate_switched" == true ]]; then
    if [[ -n "$previous_target" ]]; then
      local restore_link="${TLS_DIR}/.current.restore.$$"
      ln -s "$previous_target" "$restore_link"
      mv -Tf "$restore_link" "$CURRENT_LINK"
    else
      rm -f "$CURRENT_LINK"
    fi
  fi
  if [[ "$nginx_stopped" == true ]]; then
    if [[ "$was_active" == true ]] && openssl x509 -in "$CURRENT_LINK/fullchain.pem" -checkip "$ACME_IP" -checkend 86400 -noout >/dev/null 2>&1 && nginx -t; then
      if ! systemctl start nginx.service || ! systemctl is-active --quiet nginx.service; then
        echo 'Nginx recovery failed after certificate rollback; manual service recovery is required.' >&2
      fi
    elif [[ "$was_active" == true ]]; then
      echo 'No valid certificate remains; previously active Nginx is left stopped.' >&2
    fi
  elif [[ "$was_active" == true ]]; then
    if ! systemctl start nginx.service || ! systemctl is-active --quiet nginx.service; then
      echo 'Nginx recovery failed; manual service recovery is required.' >&2
    fi
  fi
  [[ -z "$staging_dir" || ! -d "$staging_dir" ]] || rm -rf -- "$staging_dir"
  [[ -z "$target_dir" || ! -d "$target_dir" || "$target_dir" == "$previous_target" ]] || rm -rf -- "$target_dir"
  exit "$rc"
}
trap restore_safe_nginx EXIT

systemctl stop nginx.service
nginx_stopped=true
"$LEGO_BIN" run --path "$LEGO_PATH" \
  --accept-tos --email "$ACME_EMAIL" --domains "$ACME_IP" \
  --tls --server "$ACME_DIRECTORY_URL" --profile shortlived \
  --renew-days 3 --cert.name "$ACME_IP"

python3 - "$CERT" "$KEY" "$ACME_IP" "$CA_BUNDLE" <<'PY'
import pathlib, re, subprocess, sys, tempfile
cert_path, key_path, ip, ca_bundle = map(pathlib.Path, sys.argv[1:])
cert_path = pathlib.Path(sys.argv[1]); key_path = pathlib.Path(sys.argv[2]); ip = sys.argv[3]; ca_bundle = pathlib.Path(sys.argv[4])
pem = cert_path.read_text(encoding="ascii")
blocks = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", pem, re.S)
if not blocks:
    raise SystemExit("ACME output contains no PEM certificate.")
with tempfile.TemporaryDirectory() as tmp:
    leaf = pathlib.Path(tmp) / "leaf.pem"
    chain = pathlib.Path(tmp) / "chain.pem"
    leaf.write_text(blocks[0] + "\n", encoding="ascii")
    chain.write_text("\n".join(blocks[1:]) + ("\n" if len(blocks) > 1 else ""), encoding="ascii")
    subprocess.run(["openssl", "x509", "-in", str(leaf), "-checkip", ip, "-checkend", "86400", "-noout"], check=True, stdout=subprocess.DEVNULL)
    if len(blocks) > 1:
        subprocess.run(["openssl", "verify", "-CAfile", str(ca_bundle), "-untrusted", str(chain), str(leaf)], check=True, stdout=subprocess.DEVNULL)
    else:
        subprocess.run(["openssl", "verify", "-CAfile", str(ca_bundle), str(leaf)], check=True, stdout=subprocess.DEVNULL)
    cert_pub = subprocess.check_output(["openssl", "x509", "-in", str(leaf), "-pubkey", "-noout"])
    cert_der = subprocess.check_output(["openssl", "pkey", "-pubin", "-outform", "DER"], input=cert_pub)
    key_pub = subprocess.check_output(["openssl", "pkey", "-in", str(key_path), "-pubout", "-outform", "DER"])
    if cert_der != key_pub:
        raise SystemExit("Certificate and private key do not match.")
PY

install -d -o root -g root -m 0750 "$TLS_DIR"
target_dir="${TLS_DIR}/ip-cert-$(date -u +%Y%m%dT%H%M%SZ)-$$"
staging_dir="${TLS_DIR}/.stage-$$"
install -d -o root -g root -m 0750 "$staging_dir"
install -o root -g root -m 0644 "$CERT" "$staging_dir/fullchain.pem"
install -o root -g root -m 0600 "$KEY" "$staging_dir/privkey.pem"
mv -- "$staging_dir" "$target_dir"
staging_dir=""
new_link="${TLS_DIR}/.current.new.$$"
ln -s "$target_dir" "$new_link"
mv -Tf "$new_link" "$CURRENT_LINK"
certificate_switched=true
nginx -t
if [[ "$was_active" == true ]]; then
  systemctl start nginx.service
  systemctl is-active --quiet nginx.service || { echo 'Nginx did not become active after certificate renewal.' >&2; exit 1; }
fi
nginx_stopped=false
certificate_switched=false
trap - EXIT
echo 'IP certificate renewed and validated; the prior Nginx service state was preserved.'
