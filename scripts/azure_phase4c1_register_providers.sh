#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly PHASE4B_BASE='c5baf980d9c15a8913e155cbb0769dda70dab017'
readonly REGION='eastasia'
readonly RESOURCE_GROUP='rg-pse-pulse-student-prod'
readonly EVIDENCE_DIR='/tmp/pse-pulse-phase4c1'
readonly AZURE_CONFIG_DIR_PHASE4C1="$EVIDENCE_DIR/azure-config"
readonly -a REQUIRED_PROVIDERS=(Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL)
readonly -a STATE_PROVIDERS=(Microsoft.Resources Microsoft.Authorization Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL Microsoft.Storage)

readonly REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"
export AZURE_CONFIG_DIR="$AZURE_CONFIG_DIR_PHASE4C1"

cleanup() {
  if [[ -d "$AZURE_CONFIG_DIR_PHASE4C1" ]]; then
    rm -rf -- "$AZURE_CONFIG_DIR_PHASE4C1"
  fi
}
trap cleanup EXIT

echo '[Phase 4C.1] Checking repository safety gates.'
[[ "$(git branch --show-current)" == 'main' ]] || { echo 'FAIL: branch must be main.' >&2; exit 1; }
git merge-base --is-ancestor "$PHASE4B_BASE" HEAD || { echo 'FAIL: Phase 4B baseline is not an ancestor.' >&2; exit 1; }
git diff --quiet || { echo 'FAIL: tracked working-tree changes are present.' >&2; exit 1; }
git diff --cached --quiet || { echo 'FAIL: staged changes are present.' >&2; exit 1; }

# All read-only Azure operations pass through this explicit command allowlist.
safe_read() {
  local service="${1:-}" operation="${2:-}"
  case "$service:$operation" in
    account:show|provider:show|group:exists|vm:list-usage) ;;
    *) echo "FAIL: Azure read is not on the allowlist: az $service $operation" >&2; return 64 ;;
  esac
  az "$@"
}

# The only Azure mutation wrapper accepts exactly the three owner-authorized namespaces.
register_provider() {
  local namespace="${1:-}"
  case "$namespace" in
    Microsoft.Network|Microsoft.Compute|Microsoft.DBforPostgreSQL) ;;
    Microsoft.Storage|Microsoft.Authorization|Microsoft.Resources|*)
      echo "FAIL: provider registration namespace is not authorized: $namespace" >&2
      return 64
      ;;
  esac
  echo "[Phase 4C.1] Authorized mutation: az provider register --namespace $namespace"
  az provider register --namespace "$namespace" --output none
}

account_json="$(safe_read account show --output json)"
printf '%s' "$account_json" | python3 -c '
import json, sys
data = json.load(sys.stdin)
name = data.get("name", "")
state = data.get("state", "")
sub_id = data.get("id", "")
masked = (sub_id[:8] + "-****-****-****-" + sub_id[-4:]) if len(sub_id) >= 13 else "UNAVAILABLE"
print(f"Subscription display name: {name}")
print(f"Subscription state: {state}")
print(f"Masked subscription ID: {masked}")
if name != "Azure for Students" or state != "Enabled":
    raise SystemExit("FAIL: selected subscription is not the enabled Azure for Students subscription.")
'
unset account_json

check_resource_group() {
  local label="$1" value
  value="$(safe_read group exists --name "$RESOURCE_GROUP" --output tsv)"
  printf '%s\n' "$value" >"$EVIDENCE_DIR/resource-group-$label.txt"
  echo "Target resource group exists ($label): $value"
  [[ "$value" == 'false' ]] || { echo "FAIL: target resource group must remain nonexistent ($label)." >&2; return 1; }
}

get_provider_state() {
  local namespace="$1"
  safe_read provider show --namespace "$namespace" --query registrationState --output tsv
}

echo '[Phase 4C.1] Reading baseline provider states.'
: >"$EVIDENCE_DIR/pre-provider-states.tsv"
for namespace in "${STATE_PROVIDERS[@]}"; do
  state="$(get_provider_state "$namespace")"
  printf '%s\t%s\n' "$namespace" "$state" | tee -a "$EVIDENCE_DIR/pre-provider-states.tsv"
done

pre_state() {
  awk -F '\t' -v ns="$1" '$1 == ns { print $2; found=1 } END { if (!found) exit 1 }' "$EVIDENCE_DIR/pre-provider-states.tsv"
}
[[ "$(pre_state Microsoft.Resources)" == 'Registered' ]] || { echo 'FAIL: Microsoft.Resources must already be Registered.' >&2; exit 1; }
[[ "$(pre_state Microsoft.Authorization)" == 'Registered' ]] || { echo 'FAIL: Microsoft.Authorization must already be Registered.' >&2; exit 1; }
[[ "$(pre_state Microsoft.Storage)" == 'NotRegistered' ]] || { echo 'FAIL: Microsoft.Storage must be NotRegistered before this phase.' >&2; exit 1; }
for namespace in "${REQUIRED_PROVIDERS[@]}"; do
  state="$(pre_state "$namespace")"
  [[ "$state" == 'Registered' || "$state" == 'NotRegistered' || "$state" == 'Unregistered' ]] || {
    echo "FAIL: unsupported pre-registration state for $namespace: $state" >&2; exit 1;
  }
done

check_resource_group before
: >"$EVIDENCE_DIR/registration-results.tsv"

for namespace in "${REQUIRED_PROVIDERS[@]}"; do
  started="$(date +%s)"
  state="$(get_provider_state "$namespace")"
  if [[ "$state" == 'Registered' ]]; then
    result='ALREADY_REGISTERED'
    elapsed=0
  else
    register_provider "$namespace"
    deadline=$(( $(date +%s) + 900 ))
    while true; do
      state="$(get_provider_state "$namespace")"
      [[ "$state" == 'Registered' ]] && break
      if [[ "$state" != 'Registering' && "$state" != 'NotRegistered' && "$state" != 'Unregistered' ]]; then
        printf '%s\tFAILED\t%s\n' "$namespace" "$state" >>"$EVIDENCE_DIR/registration-results.tsv"
        echo "FAIL: $namespace reached unexpected state: $state" >&2
        exit 1
      fi
      if (( $(date +%s) >= deadline )); then
        printf '%s\tTIMEOUT\t%s\n' "$namespace" "$state" >>"$EVIDENCE_DIR/registration-results.tsv"
        echo "FAIL: timed out waiting for $namespace; final state: $state" >&2
        exit 1
      fi
      sleep 10
    done
    result='REGISTERED'
    elapsed=$(( $(date +%s) - started ))
  fi
  printf '%s\t%s\t%s\t%s\n' "$namespace" "$result" "$state" "$elapsed" | tee -a "$EVIDENCE_DIR/registration-results.tsv"
  if [[ "$namespace" == 'Microsoft.Compute' ]]; then
    echo '[Phase 4C.1] Optional preliminary read-only East Asia VM quota query.'
    if safe_read vm list-usage --location "$REGION" --output json >"$EVIDENCE_DIR/eastasia-vm-usage.json" 2>"$EVIDENCE_DIR/eastasia-vm-usage.stderr"; then
      echo 'Preliminary quota query: available (raw result is restricted to the temporary evidence directory).'
    else
      echo 'Preliminary quota query: unavailable (not a final quota/capacity decision).'
    fi
  fi
done

check_resource_group after
echo '[Phase 4C.1] Reading final provider states.'
: >"$EVIDENCE_DIR/post-provider-states.tsv"
for namespace in "${STATE_PROVIDERS[@]}"; do
  state="$(get_provider_state "$namespace")"
  printf '%s\t%s\n' "$namespace" "$state" | tee -a "$EVIDENCE_DIR/post-provider-states.tsv"
done

for namespace in "${REQUIRED_PROVIDERS[@]}" Microsoft.Resources Microsoft.Authorization; do
  state="$(awk -F '\t' -v ns="$namespace" '$1 == ns { print $2 }' "$EVIDENCE_DIR/post-provider-states.tsv")"
  [[ "$state" == 'Registered' ]] || { echo "FAIL: required final state not Registered: $namespace ($state)" >&2; exit 1; }
done
storage_state="$(awk -F '\t' '$1 == "Microsoft.Storage" { print $2 }' "$EVIDENCE_DIR/post-provider-states.tsv")"
[[ "$storage_state" == 'NotRegistered' ]] || { echo "FAIL: Microsoft.Storage changed unexpectedly: $storage_state" >&2; exit 1; }
echo '[Phase 4C.1] Authorized registration and post-state checks completed.'
echo "Sanitized evidence files are under $EVIDENCE_DIR; the isolated Azure CLI config will be removed on exit."
