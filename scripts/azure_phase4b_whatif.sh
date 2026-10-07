#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly PHASE4A_BASE='4078b6161801a73a5266ee80dcc0470d979a8cb0'
readonly REGION='eastasia'
readonly RESOURCE_GROUP='rg-pse-pulse-student-prod'
readonly BASE_PARAMETERS='infra/parameters/phase4b.eastasia.bicepparam'
readonly AZURE_CONFIG_DIR="${AZURE_CONFIG_DIR:-/tmp/pse-pulse-phase4b/azure-config}"
readonly DOTNET_BUNDLE_EXTRACT_BASE_DIR="${DOTNET_BUNDLE_EXTRACT_BASE_DIR:-/tmp/pse-pulse-phase4b/dotnet-cache}"
export AZURE_CONFIG_DIR DOTNET_BUNDLE_EXTRACT_BASE_DIR

fail() {
  printf 'WHAT-IF BLOCKED: %s\n' "$1" >&2
  exit "${2:-2}"
}

assert_az_commands_are_non_deploying() {
  local line command
  while IFS= read -r line; do
    command="${line#*:}"
    command="${command#"${command%%[![:space:]]*}"}"
    case "$command" in
      'az version'*|'az bicep version'*|'az bicep lint'*|'az bicep build'*|'az bicep build-params'*|'az account show'*|'az provider show'*|'az group exists'*|'az deployment sub validate'*|'az deployment sub what-if'*) ;;
      *) fail "command guard rejected Azure operation: ${command%% *}" 3 ;;
    esac
  done < <(grep -nE '^[[:space:]]*az[[:space:]]+' "$0" || true)
}

assert_az_commands_are_non_deploying

cd "$(git rev-parse --show-toplevel)"
[[ "$(git branch --show-current)" == 'main' ]] || fail 'branch is not main'
git merge-base --is-ancestor "$PHASE4A_BASE" HEAD || fail 'HEAD is not descended from the trusted Phase 4A baseline'
git diff --quiet || fail 'tracked working-tree changes detected'
git diff --cached --quiet || fail 'staged changes detected'

account_json="$(az account show --output json 2>/dev/null)" || fail 'Azure login is unavailable'
printf '%s\n' "$account_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("state")=="Enabled" else 1)' || fail 'selected subscription is not enabled'

exists="$(az group exists --name "$RESOURCE_GROUP" --output tsv)" || fail 'resource-group collision check failed'
[[ "$exists" == 'false' ]] || fail "target resource group already exists: $RESOURCE_GROUP"

required_providers=(Microsoft.Resources Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL Microsoft.Authorization)
required_unregistered=()
for provider in "${required_providers[@]}"; do
  state="$(az provider show --namespace "$provider" --query registrationState --output tsv)" || fail "cannot inspect provider $provider"
  printf '%s: %s\n' "$provider" "$state"
  [[ "$state" == 'Registered' ]] || required_unregistered+=("$provider")
done
storage_state="$(az provider show --namespace Microsoft.Storage --query registrationState --output tsv)" || fail 'cannot inspect optional provider Microsoft.Storage'
printf 'Microsoft.Storage (optional while deployBlob=false): %s\n' "$storage_state"

provider_registration_blocker() {
  local raw_file="$1"
  local provider
  grep -Eqi 'MissingSubscriptionRegistration|NoRegisteredProviderFound|resource provider.*not registered|register the resource provider' "$raw_file" || return 1
  for provider in "${required_unregistered[@]}"; do
    grep -Fqi "$provider" "$raw_file" && return 0
  done
  return 1
}

workdir="$(mktemp -d /tmp/pse-pulse-phase4b/run.XXXXXX)"
cleanup() {
  rm -f "$workdir/ephemeral_ssh" "$workdir/ephemeral_ssh.pub" "$workdir/dummy_pg_password" "$workdir/runtime-parameters.json" "$workdir/runtime-parameters.bicepparam"
}
trap cleanup EXIT

ssh-keygen -q -t ed25519 -N '' -C 'phase4b-validation-only' -f "$workdir/ephemeral_ssh" >/dev/null 2>&1 || fail 'could not generate temporary SSH key'
openssl rand -base64 48 >"$workdir/dummy_pg_password"
chmod 600 "$workdir/dummy_pg_password"

python3 - "$workdir" "$BASE_PARAMETERS" <<'PY'
import pathlib
import sys
import subprocess

workdir = pathlib.Path(sys.argv[1])
public_key = (workdir / "ephemeral_ssh.pub").read_text().strip()
password = (workdir / "dummy_pg_password").read_text().strip()
root = pathlib.Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
parameters_path = pathlib.Path(sys.argv[2])
source = (root / parameters_path).read_text()
template_relative = pathlib.Path(__import__("os").path.relpath(root / "infra/main.bicep", start=workdir))
source = source.replace("using '../main.bicep'", f"using '{template_relative.as_posix()}'")
source += f"\nparam adminSshPublicKey = '{public_key}'\nparam administratorPassword = '{password}'\n"
target = workdir / "runtime-parameters.bicepparam"
target.write_text(source)
target.chmod(0o600)
PY
az bicep build-params --file "$workdir/runtime-parameters.bicepparam" --outfile "$workdir/runtime-parameters.json" >/dev/null || fail 'could not compile the runtime parameter file'
chmod 600 "$workdir/runtime-parameters.json"

printf '%s\n' 'Bicep lint:'
az bicep lint --file infra/main.bicep >/dev/null || fail 'Bicep lint failed'
for module in infra/modules/network.bicep infra/modules/compute.bicep infra/modules/postgres.bicep infra/modules/storage.bicep; do
  az bicep lint --file "$module" >/dev/null || fail "Bicep lint failed: $module"
done

az bicep build --file infra/main.bicep --outfile "$workdir/main.json" >/dev/null || fail 'Bicep build failed'
az bicep build --file infra/modules/network.bicep --outfile "$workdir/network.json" >/dev/null || fail 'network module build failed'
az bicep build --file infra/modules/compute.bicep --outfile "$workdir/compute.json" >/dev/null || fail 'compute module build failed'
az bicep build --file infra/modules/postgres.bicep --outfile "$workdir/postgres.json" >/dev/null || fail 'PostgreSQL module build failed'
az bicep build --file infra/modules/storage.bicep --outfile "$workdir/storage.json" >/dev/null || fail 'storage module build failed'

if ! az deployment sub validate \
  --name "phase4b-validate-eastasia" \
  --location "$REGION" \
  --template-file infra/main.bicep \
  --parameters "@$workdir/runtime-parameters.json" \
  --output json >"$workdir/validate.raw.json" 2>&1; then
  if provider_registration_blocker "$workdir/validate.raw.json"; then
    printf 'WHATIF_BLOCKED_BY_PROVIDER_REGISTRATION: %s\n' "${required_unregistered[*]}" >&2
    fail "subscription ARM validation failed because a required provider is not registered; stopping before What-If (raw evidence: $workdir/validate.raw.json)" 42
  elif grep -q 'RequestDisallowedByAzure' "$workdir/validate.raw.json"; then
    printf '%s\n' 'WHATIF_BLOCKED_BY_REGION_OR_SUBSCRIPTION_POLICY' >&2
    fail "subscription ARM validation was denied by Azure policy; stopping before What-If (raw evidence: $workdir/validate.raw.json)" 43
  elif grep -Eq 'AuthorizationFailed|Forbidden|does not have authorization' "$workdir/validate.raw.json"; then
    printf '%s\n' 'WHATIF_BLOCKED_BY_RBAC' >&2
    fail "subscription ARM validation lacks required authorization; stopping before What-If (raw evidence: $workdir/validate.raw.json)" 44
  fi
  fail "subscription ARM validation failed; stopping before What-If (raw evidence: $workdir/validate.raw.json)" 4
fi

if ! az deployment sub what-if \
  --name "phase4b-whatif-eastasia" \
  --location "$REGION" \
  --template-file infra/main.bicep \
  --parameters "@$workdir/runtime-parameters.json" \
  --result-format ResourceIdOnly \
  --no-pretty-print \
  --output json >"$workdir/whatif.raw.json" 2>&1; then
  if provider_registration_blocker "$workdir/whatif.raw.json"; then
    printf 'WHATIF_BLOCKED_BY_PROVIDER_REGISTRATION: %s\n' "${required_unregistered[*]}" >&2
    fail "subscription What-If failed; raw output retained only under /tmp: $workdir/whatif.raw.json" 42
  elif grep -q 'RequestDisallowedByAzure' "$workdir/whatif.raw.json"; then
    printf '%s\n' 'WHATIF_BLOCKED_BY_REGION_OR_SUBSCRIPTION_POLICY' >&2
    fail "subscription What-If was denied by Azure policy; raw output retained only under /tmp: $workdir/whatif.raw.json" 43
  fi
  fail "subscription What-If failed; raw output retained only under /tmp: $workdir/whatif.raw.json" 5
fi

python3 - "$workdir/whatif.raw.json" "$workdir/whatif-summary.json" <<'PY'
import json
import pathlib
import re
import sys

raw_path, summary_path = map(pathlib.Path, sys.argv[1:])
data = json.loads(raw_path.read_text())
properties = data.get("properties", data)
changes = properties.get("changes", []) if isinstance(properties, dict) else []
allowed_resource_types = {
    "Microsoft.Resources/resourceGroups",
    "Microsoft.Network/networkSecurityGroups",
    "Microsoft.Network/virtualNetworks",
    "Microsoft.Network/publicIPAddresses",
    "Microsoft.Network/networkInterfaces",
    "Microsoft.Network/privateDnsZones",
    "Microsoft.Network/privateDnsZones/virtualNetworkLinks",
    "Microsoft.Compute/virtualMachines",
    "Microsoft.DBforPostgreSQL/flexibleServers",
}
allowed_change_types = {"Create", "Deploy", "NoChange"}
rows = []
for item in changes:
    resource_id = item.get("resourceId", "")
    segments = [segment for segment in resource_id.split("/") if segment]
    if "providers" in segments:
        provider_index = segments.index("providers")
        namespace = segments[provider_index + 1]
        resource_names = segments[provider_index + 2 :: 2]
        resource_type = namespace + "/" + "/".join(resource_names)
    else:
        resource_type = "Microsoft.Resources/resourceGroups"
    resource_id = re.sub(
        r"(?i)(/subscriptions/)[0-9a-f-]{36}",
        r"\1<masked>",
        resource_id,
    )
    rows.append({
        "changeType": item.get("changeType"),
        "resourceType": item.get("resourceType") or resource_type,
        "resourceId": resource_id,
    })
change_counts = {
    change_type: sum(1 for row in rows if row["changeType"] == change_type)
    for change_type in sorted({row["changeType"] for row in rows})
}
resource_counts = {
    resource_type: sum(1 for row in rows if row["resourceType"] == resource_type)
    for resource_type in sorted({row["resourceType"] for row in rows})
}
unexpected_resource_types = sorted({row["resourceType"] for row in rows} - allowed_resource_types)
unexpected_change_types = sorted({row["changeType"] for row in rows} - allowed_change_types)
summary = {
    "status": properties.get("provisioningState") or data.get("status"),
    "changes": rows,
    "changeTypeCounts": change_counts,
    "resourceTypeCounts": resource_counts,
    "unexpectedResourceTypes": unexpected_resource_types,
    "unexpectedChangeTypes": unexpected_change_types,
    "deleteCount": sum(1 for row in rows if (row["changeType"] or "").lower() == "delete"),
    "modifyCount": sum(1 for row in rows if (row["changeType"] or "").lower() == "modify"),
    "storageAccountCount": resource_counts.get("Microsoft.Storage/storageAccounts", 0),
    "roleAssignmentCount": resource_counts.get("Microsoft.Authorization/roleAssignments", 0),
}
summary_path.write_text(json.dumps(summary, indent=2) + "\n")
summary_path.chmod(0o600)
print(json.dumps(summary, indent=2))
if summary["status"] != "Succeeded":
    raise SystemExit("What-If response did not report Succeeded")
if unexpected_resource_types or unexpected_change_types or summary["deleteCount"] or summary["modifyCount"]:
    raise SystemExit("What-If result violates the approved Phase 4B inventory/change gate")
if summary["storageAccountCount"] or summary["roleAssignmentCount"]:
    raise SystemExit("Optional storage or role assignment appeared while deployBlob=false")
PY

printf '%s\n' "Raw validation and What-If outputs are retained under $workdir only. No resource deployment was performed."
