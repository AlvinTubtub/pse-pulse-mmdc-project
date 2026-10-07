#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly PHASE4B_BASE='c5baf980d9c15a8913e155cbb0769dda70dab017'
readonly REGION='eastasia'
readonly RESOURCE_GROUP='rg-pse-pulse-student-prod'
readonly EVIDENCE_DIR='/tmp/pse-pulse-phase4c0'
readonly REPO_ROOT="$(git rev-parse --show-toplevel)"

cd "$REPO_ROOT"
mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"

echo '[Phase 4C.0] Checking repository safety gates.'
[[ "$(git branch --show-current)" == 'main' ]] || { echo 'FAIL: branch must be main.' >&2; exit 1; }
git merge-base --is-ancestor "$PHASE4B_BASE" HEAD || { echo 'FAIL: Phase 4B baseline is not an ancestor.' >&2; exit 1; }
git diff --quiet || { echo 'FAIL: tracked working-tree changes are present.' >&2; exit 1; }
git diff --cached --quiet || { echo 'FAIL: staged changes are present.' >&2; exit 1; }

# Azure calls go through this allowlist. No arbitrary az command or shell evaluation is used.
safe_az() {
  local service="${1:-}" operation="${2:-}"
  case "$service:$operation" in
    account:show|account:list|account:list-locations|provider:show|group:exists|vm:list-skus|vm:list-usage|vm:image|postgres:flexible-server|policy:assignment|billing:account|consumption:credits|rest:--method)
      ;;
    *) echo "FAIL: Azure command is not on the read-only allowlist: az $service $operation" >&2; exit 64 ;;
  esac
  if [[ "$service:$operation" == 'rest:--method' ]]; then
    local found_get=false arg
    for arg in "$@"; do [[ "$arg" == 'GET' ]] && found_get=true; done
    [[ "$found_get" == true ]] || { echo 'FAIL: az rest must use GET.' >&2; exit 64; }
  fi
  az "$@"
}

capture_az() {
  local label="$1"; shift
  echo "[Phase 4C.0] Read-only Azure query: $label"
  if safe_az "$@" >"$EVIDENCE_DIR/$label.json" 2>"$EVIDENCE_DIR/$label.stderr"; then
    echo "success" >"$EVIDENCE_DIR/$label.status"
  else
    echo "unavailable" >"$EVIDENCE_DIR/$label.status"
    echo "[Phase 4C.0] Query unavailable: $label (details retained under $EVIDENCE_DIR)."
  fi
}

capture_az account-show account show --output json
capture_az account-list account list --output json
capture_az locations account list-locations --output json
capture_az provider-resources provider show --namespace Microsoft.Resources --output json
capture_az provider-authorization provider show --namespace Microsoft.Authorization --output json
capture_az provider-network provider show --namespace Microsoft.Network --output json
capture_az provider-compute provider show --namespace Microsoft.Compute --output json
capture_az provider-postgres provider show --namespace Microsoft.DBforPostgreSQL --output json
capture_az provider-storage provider show --namespace Microsoft.Storage --output json
capture_az target-resource-group group exists --name "$RESOURCE_GROUP" --output tsv
capture_az vm-usage vm list-usage --location "$REGION" --output json
capture_az ubuntu-images vm image list --location "$REGION" --publisher Canonical --offer ubuntu-24_04-lts --sku server --all --output json

echo '[Phase 4C.0] Attempting read-only billing evidence queries.'
capture_az billing-accounts billing account list --output json
capture_az consumption-credits consumption credits list --output json

# Keep subscription IDs only in mode-0600 temporary evidence; never print them.
subscription_id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("id", ""))' "$EVIDENCE_DIR/account-show.json" 2>/dev/null || true)"
if [[ -n "$subscription_id" ]]; then
  capture_az policy-assignments policy assignment list --scope "/subscriptions/$subscription_id" --disable-scope-strict-match true --output json
  capture_az subscription-compute-skus rest --method GET --url "https://management.azure.com/subscriptions/$subscription_id/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27$REGION%27"
  capture_az postgres-capabilities rest --method GET --url "https://management.azure.com/subscriptions/$subscription_id/providers/Microsoft.DBforPostgreSQL/locations/$REGION/capabilities?api-version=2024-08-01"
else
  echo 'unavailable' >"$EVIDENCE_DIR/policy-assignments.status"
  echo 'unavailable' >"$EVIDENCE_DIR/subscription-compute-skus.status"
  echo 'unavailable' >"$EVIDENCE_DIR/postgres-capabilities.status"
fi

fetch_retail_prices() {
  local label="$1" filter="$2"
  echo "[Phase 4C.0] Public Retail Prices API GET: $label"
  if curl --fail --silent --show-error --get \
      --data-urlencode "$filter" \
      'https://prices.azure.com/api/retail/prices' \
      --output "$EVIDENCE_DIR/retail-$label.json" \
      2>"$EVIDENCE_DIR/retail-$label.stderr"; then
    echo success >"$EVIDENCE_DIR/retail-$label.status"
  else
    echo unavailable >"$EVIDENCE_DIR/retail-$label.status"
    echo "[Phase 4C.0] Price query unavailable: $label."
  fi
}

fetch_retail_prices vm-primary "\$filter=serviceName eq 'Virtual Machines' and armRegionName eq 'eastasia' and armSkuName eq 'Standard_B2als_v2' and priceType eq 'Consumption'"
fetch_retail_prices vm-fallback "\$filter=serviceName eq 'Virtual Machines' and armRegionName eq 'eastasia' and armSkuName eq 'Standard_B2as_v2' and priceType eq 'Consumption'"
fetch_retail_prices os-disk "\$filter=serviceName eq 'Storage' and armRegionName eq 'eastasia' and contains(meterName, 'E4') and priceType eq 'Consumption'"
fetch_retail_prices public-ip "\$filter=serviceName eq 'Virtual Network' and armRegionName eq 'eastasia' and contains(productName, 'IP') and priceType eq 'Consumption'"
fetch_retail_prices postgres-compute "\$filter=serviceName eq 'Azure Database for PostgreSQL' and armRegionName eq 'eastasia' and contains(productName, 'PostgreSQL Flexible Server') and priceType eq 'Consumption'"
fetch_retail_prices postgres-storage "\$filter=serviceName eq 'Azure Database for PostgreSQL' and armRegionName eq 'eastasia' and contains(meterName, 'Storage') and priceType eq 'Consumption'"
fetch_retail_prices private-dns-zone "\$filter=serviceName eq 'Azure DNS' and meterName eq 'Private Zone' and priceType eq 'Consumption'"
fetch_retail_prices private-dns-queries "\$filter=serviceName eq 'Azure DNS' and meterName eq 'Private Queries' and priceType eq 'Consumption'"

echo '[Phase 4C.0] Read-only evidence collection completed.'
echo "Raw CLI/REST and retail-price responses are mode-restricted under $EVIDENCE_DIR only."
echo 'No Azure mutation command is permitted by the script allowlist.'
