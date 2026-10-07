#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly PHASE4A_BASE='4078b6161801a73a5266ee80dcc0470d979a8cb0'
readonly REGION='eastasia'
readonly RESOURCE_GROUP='rg-pse-pulse-student-prod'
readonly AZURE_CONFIG_DIR="${AZURE_CONFIG_DIR:-/tmp/pse-pulse-phase4b/azure-config}"
readonly DOTNET_BUNDLE_EXTRACT_BASE_DIR="${DOTNET_BUNDLE_EXTRACT_BASE_DIR:-/tmp/pse-pulse-phase4b/dotnet-cache}"
export AZURE_CONFIG_DIR DOTNET_BUNDLE_EXTRACT_BASE_DIR

fail() {
  printf 'PREFLIGHT BLOCKED: %s\n' "$1" >&2
  exit 2
}

assert_az_commands_are_read_only() {
  local line command
  while IFS= read -r line; do
    command="${line#*:}"
    command="${command#"${command%%[![:space:]]*}"}"
    if [[ "$command" == az_readonly\ * ]]; then
      command="${command#az_readonly }"
      command="${command#* }"
    fi
    case "$command" in
      'az version'*|'az bicep version'*|'az account list'*|'az account show'*|'az account list-locations'*|'az provider show'*|'az vm list-skus'*|'az vm list-usage'*|'az vm image list'*|'az postgres flexible-server list-skus'*|'az rest --method get'*|'az group exists'*) ;;
      *) fail "read-only command guard rejected: ${command%% *}" ;;
    esac
  done < <(grep -nE '^[[:space:]]*(az|az_readonly)[[:space:]]+' "$0" || true)
}

az_readonly() {
  local timeout_seconds="$1"
  shift
  python3 - "$timeout_seconds" "$@" <<'PY'
import subprocess
import sys

seconds = int(sys.argv[1])
try:
    result = subprocess.run(sys.argv[2:], capture_output=True, text=True, timeout=seconds)
except subprocess.TimeoutExpired:
    print(f"READ-ONLY QUERY TIMED OUT after {seconds}s: {sys.argv[2]}", file=sys.stderr)
    raise SystemExit(124)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
raise SystemExit(result.returncode)
PY
}

assert_az_commands_are_read_only

cd "$(git rev-parse --show-toplevel)"
[[ "$(git branch --show-current)" == 'main' ]] || fail 'branch is not main'
git merge-base --is-ancestor "$PHASE4A_BASE" HEAD || fail 'HEAD is not descended from the trusted Phase 4A baseline'
git diff --quiet || fail 'tracked working-tree changes detected'
git diff --cached --quiet || fail 'staged changes detected'

command -v az >/dev/null 2>&1 || fail 'Azure CLI is unavailable'
command -v python3 >/dev/null 2>&1 || fail 'Python is unavailable'

printf '%s\n' 'Azure CLI:'
az_readonly 30 az version --output json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("azure-cli", "unknown"))'
printf '%s\n' 'Bicep CLI:'
az_readonly 30 az bicep version

account_json="$(az_readonly 30 az account show --output json 2>/dev/null)" || fail 'no logged-in Azure account'
printf '%s\n' "$account_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); sid=d.get("id", ""); mask=(sid[:8]+"-****-****-****-********"+sid[-4:]) if len(sid)>12 else "REDACTED"; print(json.dumps({"name":d.get("name"),"state":d.get("state"),"subscriptionId":mask},indent=2)); sys.exit(0 if d.get("state")=="Enabled" else 2)' || fail 'selected subscription is not enabled'

printf '%s\n' 'Account-access flags that require separate confirmation: Azure for Students offer, remaining credit/expiry, spending protection, and no PAYG upgrade.'
printf '%s\n' 'Provider registration states:'
for provider in Microsoft.Resources Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL Microsoft.Authorization; do
  state="$(az_readonly 30 az provider show --namespace "$provider" --query registrationState --output tsv)" || fail "could not inspect $provider"
  printf '  %s: %s\n' "$provider" "$state"
done
storage_state="$(az_readonly 30 az provider show --namespace Microsoft.Storage --query registrationState --output tsv)" || fail 'could not inspect Microsoft.Storage'
printf '  Microsoft.Storage (optional while deployBlob=false): %s\n' "$storage_state"

printf '%s\n' 'Candidate locations:'
printf 'Selected validation region: %s\n' "$REGION"
az_readonly 30 az account list-locations --query "[?name=='southeastasia' || name=='eastasia'].{name:name,displayName:displayName}" --output table

for size in Standard_B2als_v2 Standard_B2as_v2; do
  printf '%s\n' "Selected-region VM SKU: $REGION $size (availability and restrictions)"
  if sku_result="$(az_readonly 18 az vm list-skus --location "$REGION" --size "$size" --all --query '[].{name:name,family:family,locations:locations,restrictions:restrictions,capabilities:capabilities}' --output json 2>/dev/null)"; then
    printf '%s\n' "$sku_result"
  else
    printf '%s\n' 'CLI SKU listing unavailable; using read-only ARM Compute SKU endpoint.'
    sku_url="/subscriptions/{subscriptionId}/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27${REGION}%27"
    sku_query="value[?name=='${size}'].{name:name,resourceType:resourceType,locations:locations,restrictions:restrictions,locationInfo:locationInfo}"
    az_readonly 60 az rest --method get --url "$sku_url" --query "$sku_query" --output json || printf '%s\n' 'SKU availability/restrictions: UNVERIFIED (ARM SKU query unavailable)'
  fi
done
printf '%s\n' "Selected-region VM quota: $REGION"
if ! az_readonly 30 az vm list-usage --location "$REGION" --query "[?contains(name.localizedValue, 'vCPU') || contains(name.localizedValue, 'vCPUs')].{name:name.localizedValue,current:currentValue,limit:limit}" --output table; then
  printf '%s\n' 'VM quota: UNVERIFIED (read-only listing unavailable)'
fi

printf 'Canonical Ubuntu image contract in selected region (%s):\n' "$REGION"
az_readonly 30 az vm image list --location "$REGION" --publisher Canonical --offer ubuntu-24_04-lts --sku server --all --query '[0].{publisher:publisher,offer:offer,sku:sku,version:version}' --output json

printf '%s\n' "PostgreSQL Flexible Server SKU: $REGION Standard_B1ms"
sku_catalog="$(az_readonly 30 az postgres flexible-server list-skus --location "$REGION" --output json)" || fail "could not inspect PostgreSQL SKUs in $REGION"
printf '%s\n' "$sku_catalog" | python3 -c 'import json,sys; d=json.load(sys.stdin); rows=[sku for region in d for edition in region.get("supportedServerEditions",[]) if edition.get("name")=="Burstable" for sku in edition.get("supportedServerSkus",[]) if sku.get("name")=="Standard_B1ms"]; print(json.dumps(rows,indent=2) if rows else "Standard_B1ms not listed")'

printf '%s\n' "Future resource-group exists (must be false):"
exists="$(az_readonly 30 az group exists --name "$RESOURCE_GROUP" --output tsv)"
[[ "$exists" == 'false' ]] || fail "target resource group collision: $RESOURCE_GROUP"
printf '  %s\n' "$exists"

printf '%s\n' 'Preflight completed. Provider/SKU/credit restrictions remain gates; no Azure resource was changed.'
