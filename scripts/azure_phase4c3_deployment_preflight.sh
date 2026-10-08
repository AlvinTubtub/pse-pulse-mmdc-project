#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly PHASE4C2_BASE='075e30834bf6b1e9b0f2088b66f40850966cc6c2'
readonly REGION='eastasia'
readonly RESOURCE_GROUP='rg-pse-pulse-student-prod'
readonly APPROVED_SUBSCRIPTION_MASK='2982c1f8-****-****-****-b4d8'
readonly APPROVED_SUBSCRIPTION_SHA256='b5c57c89ad994419385b50d7536406537d7d59fbafb0cb7fd61d0cccb6f99635'
readonly EVIDENCE_DIR='/tmp/pse-pulse-phase4c3'
readonly PARAMS="$EVIDENCE_DIR/runtime.parameters.json"
readonly TEMP_SSH_KEY="$EVIDENCE_DIR/validation_ssh"
readonly TEMP_SSH_PUB="$EVIDENCE_DIR/validation_ssh.pub"
readonly TEMP_PASSWORD="$EVIDENCE_DIR/validation_pg_password"
readonly PG_ADMIN='psepulseadmin'
readonly -a IAC_FILES=(
  infra/main.bicep
  infra/modules/network.bicep
  infra/modules/compute.bicep
  infra/modules/postgres.bicep
  infra/modules/storage.bicep
  infra/parameters/phase4b.eastasia.bicepparam
)
readonly -a IAC_HASHES=(
  efa8a5e8e4571e4a0f60b50cc06f9444826a148392f297d0b508f893c7500009
  f042280227dcc74dcb01d26ce0a5a4962f532c79e8509018916c3f3808242029
  459c7115b7a14f06b84003ad0d6f66871d6c4f80d69fa9b8506ea7beda24eec5
  3f537ceaf6d4dac37cf091fbecb0daed7e22bc1c871549f04fe03202c178ce42
  b21facba372a409be125eab051d434c90b86a9dc0ea1612e0c54451a201745eb
  c99b776765938988698a917308fbd448d903afe4a7c961de33ff304fe1d9c29c
)
readonly -a REQUIRED_PROVIDERS=(Microsoft.Resources Microsoft.Authorization Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL)
readonly -a POST_PROVIDERS=(Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL Microsoft.Storage)
readonly ROOT="$(git rev-parse --show-toplevel)"

SUBSCRIPTION_ID=''
SSH_PUBLIC_KEY=''
PG_PASSWORD=''

usage() { cat <<'EOF'
Usage: bash scripts/azure_phase4c3_deployment_preflight.sh --prepare
       bash scripts/azure_phase4c3_deployment_preflight.sh --help
This script performs preparation checks and previews only.
EOF
}
stop_gate() { local gate="$1" message="$2"; if [[ ! -L "$EVIDENCE_DIR" ]]; then mkdir -p "$EVIDENCE_DIR"; printf '%s\n' "$gate" >"$EVIDENCE_DIR/failure-gate.txt"; fi; printf 'PHASE 4C.3 STOP [%s]: %s\n' "$gate" "$message" >&2; exit 20; }
cleanup() { rm -f -- "$PARAMS" "$TEMP_SSH_KEY" "$TEMP_SSH_PUB" "$TEMP_PASSWORD"; SSH_PUBLIC_KEY=''; PG_PASSWORD=''; }
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ "$#" -eq 1 && "$1" == --help ]]; then usage; exit 0; fi
if [[ "$#" -ne 1 || "$1" != --prepare ]]; then usage >&2; exit 2; fi
cd "$ROOT"
[[ ! -L "$EVIDENCE_DIR" ]] || { echo NO_GO_EVIDENCE_PATH >&2; exit 20; }
mkdir -p "$EVIDENCE_DIR"; chmod 700 "$EVIDENCE_DIR"
python3 - "$EVIDENCE_DIR" <<'PY'
import os,sys
s=os.stat(sys.argv[1])
if s.st_uid!=os.getuid() or s.st_mode&0o077:raise SystemExit(1)
PY
rm -f "$EVIDENCE_DIR/failure-gate.txt"
echo '[4C.3 Gate A] Repository and baseline checks.'
[[ "$(git branch --show-current)" == main ]] || stop_gate NO_GO_REPOSITORY_BASELINE 'branch is not main'
git merge-base --is-ancestor "$PHASE4C2_BASE" HEAD || stop_gate NO_GO_REPOSITORY_BASELINE 'accepted Phase 4C.2 commit is not an ancestor'
git diff --quiet || stop_gate NO_GO_REPOSITORY_BASELINE 'tracked worktree modifications exist'
git diff --cached --quiet || stop_gate NO_GO_REPOSITORY_BASELINE 'staged changes exist'
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  path="${line:3}"
  [[ "$line" == '?? '* ]] || stop_gate NO_GO_REPOSITORY_BASELINE "tracked change exists: $path"
  case "$path" in PHASE4C3_DEPLOYMENT_READINESS_REPORT.md|scripts/azure_phase4c3_deployment_preflight.sh|PHASE4C3_OWNER_DEPLOYMENT_AUTHORIZATION_CHECKLIST.md) ;; *) stop_gate NO_GO_REPOSITORY_BASELINE "unexpected untracked path: $path" ;; esac
done < <(git status --porcelain --untracked-files=all)

git diff --quiet "$PHASE4C2_BASE" HEAD -- infra scripts/azure_phase4c2_post_registration_validate.sh backend/tests/test_phase4b_iac_safety.py || stop_gate NO_GO_IAC_INTEGRITY 'Phase 4B or Phase 4C.2 implementation files changed'

echo '[4C.3 Gate A] Verifying accepted IaC hashes.'
for f in "${IAC_FILES[@]}"; do git cat-file -e "HEAD:$f" || stop_gate NO_GO_IAC_INTEGRITY "candidate file is not committed: $f"; done
: >"$EVIDENCE_DIR/iac-sha256.txt"
for i in "${!IAC_FILES[@]}"; do
  f="${IAC_FILES[$i]}"
  actual="$(shasum -a 256 "$f" | awk '{print $1}')"
  printf '%s  %s\n' "$actual" "$f" | tee -a "$EVIDENCE_DIR/iac-sha256.txt"
  [[ "$actual" == "${IAC_HASHES[$i]}" ]] || stop_gate NO_GO_IAC_INTEGRITY "candidate SHA256 differs: $f"
done

safe_az() {
  local service="${1:-}" object="${2:-}" operation="${3:-}"
  case "$service:$object:$operation" in
    account:show:*|provider:show:*|group:exists:*|policy:assignment:list|vm:list-usage:*|rest:--method:*|vm:image:list|postgres:flexible-server:list-skus|bicep:build:*|deployment:sub:validate|deployment:sub:what-if) ;;
    *) echo "FAIL: unapproved Azure operation: az $service $object $operation" >&2; return 64 ;;
  esac
  if [[ "$service:$object" == rest:--method ]]; then local arg get_seen=false; for arg in "$@"; do case "$arg" in GET|get) get_seen=true ;; esac; done; [[ "$get_seen" == true ]] || return 64; fi
  az "$@"
}
echo '[4C.3 Gate A] Verifying the existing authenticated Azure context.'
account="$(safe_az account show --output json 2>"$EVIDENCE_DIR/account.stderr")" || stop_gate NO_GO_AZURE_AUTH_CONTEXT 'az account show could not use the existing authenticated context; no login was attempted'
account_summary="$(printf '%s' "$account" | python3 -c 'import hashlib,json,sys; d=json.load(sys.stdin); sid=d.get("id",""); mask=(sid[:8]+"-****-****-****-"+sid[-4:]) if len(sid)>=13 else "UNAVAILABLE"; digest=hashlib.sha256(sid.encode()).hexdigest(); print("\t".join((d.get("name",""),d.get("state",""),mask,digest,sid)))')" || stop_gate NO_GO_SUBSCRIPTION 'account output could not be parsed'
IFS=$'\t' read -r SUB_NAME SUB_STATE SUB_MASK SUBSCRIPTION_SHA256 SUBSCRIPTION_ID <<<"$account_summary"
unset account account_summary
printf 'Subscription: %s / %s; masked ID %s\n' "$SUB_NAME" "$SUB_STATE" "$SUB_MASK"
[[ "$SUB_NAME" == 'Azure for Students' && "$SUB_STATE" == Enabled && "$SUB_MASK" == "$APPROVED_SUBSCRIPTION_MASK" && "$SUBSCRIPTION_SHA256" == "$APPROVED_SUBSCRIPTION_SHA256" ]] || stop_gate NO_GO_SUBSCRIPTION 'selected subscription is not the exact known enabled owner-approved subscription'

echo '[4C.3 Gate A] Checking provider states and target resource-group absence.'
: >"$EVIDENCE_DIR/providers-before.tsv"
for provider in "${REQUIRED_PROVIDERS[@]}" Microsoft.Storage; do
  state="$(safe_az provider show --namespace "$provider" --query registrationState --output tsv)" || stop_gate NO_GO_PROVIDER_STATE "could not read provider state: $provider"
  printf '%s\t%s\n' "$provider" "$state" >>"$EVIDENCE_DIR/providers-before.tsv"
  if [[ "$provider" == Microsoft.Storage ]]; then
    [[ "$state" == NotRegistered ]] || stop_gate NO_GO_PROVIDER_STATE 'Microsoft.Storage must remain NotRegistered'
  else
    [[ "$state" == Registered ]] || stop_gate NO_GO_PROVIDER_STATE "$provider is not Registered"
  fi
done
rg_before="$(safe_az group exists --name "$RESOURCE_GROUP" --output tsv)" || stop_gate NO_GO_RESOURCE_GROUP 'resource group absence check failed'
printf '%s\n' "$rg_before" >"$EVIDENCE_DIR/resource-group-before.txt"
[[ "$rg_before" == false ]] || stop_gate NO_GO_RESOURCE_GROUP 'target resource group already exists; it will not be reused or overwritten'

echo '[4C.3 Gate A] Rechecking East Asia policy, quota, SKU, image, and PostgreSQL.'
safe_az policy assignment list --scope "/subscriptions/$SUBSCRIPTION_ID" --disable-scope-strict-match true --output json >"$EVIDENCE_DIR/policy-assignments.json" || stop_gate NO_GO_POLICY_CHANGED 'could not read region policy assignments'
if ! python3 - "$EVIDENCE_DIR/policy-assignments.json" >"$EVIDENCE_DIR/policy-summary.txt" <<'PY'
import json,sys
doc=json.load(open(sys.argv[1])); rows=doc if isinstance(doc,list) else doc.get('value',[])
found=[]
def values(x):
 if isinstance(x,dict):
  out=[]
  for k,v in x.items():
   if 'location' in k.lower() or 'allowed' in k.lower(): out.extend(values(v))
   elif isinstance(v,(dict,list)): out.extend(values(v))
  return out
 if isinstance(x,list): return [y for v in x for y in values(v)]
 return [x] if isinstance(x,str) else []
for row in rows:
 p=row.get('properties',row); name=row.get('name',''); display=p.get('displayName','')
 if name=='sys.regionrestriction' or 'regionrestriction' in str(p.get('policyDefinitionId','')).lower() or 'allowed resource deployment regions' in str(display).lower():
  allowed=sorted(set(values(p.get('parameters',{})))); found.append((name,display,allowed))
for name,display,allowed in found: print(f'assignment={name}; display={display}; allowed={",".join(allowed)}')
if not found or not any(any(v.lower()=='eastasia' for v in allowed) for _,_,allowed in found): raise SystemExit(1)
PY
then stop_gate NO_GO_POLICY_CHANGED 'East Asia is not explicitly allowed by sys.regionrestriction'; fi

safe_az vm list-usage --location "$REGION" --output json >"$EVIDENCE_DIR/vm-usage.json" || stop_gate NO_GO_INSUFFICIENT_QUOTA 'could not read current East Asia VM quota'
sku_url="https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27$REGION%27"
safe_az rest --method GET --url "$sku_url" --output json >"$EVIDENCE_DIR/compute-skus.json" || stop_gate NO_GO_PRIMARY_VM_RESTRICTED 'read-only VM SKU catalog query failed'
if ! python3 - "$EVIDENCE_DIR/vm-usage.json" "$EVIDENCE_DIR/compute-skus.json" >"$EVIDENCE_DIR/quota-sku-summary.json" <<'PY'
import json,re,sys
usage=json.load(open(sys.argv[1])); sku_doc=json.load(open(sys.argv[2]))
rows=usage if isinstance(usage,list) else usage.get('value',[])
def norm(v): return re.sub(r'[^a-z0-9]','',str(v).lower())
def quota(want):
 for row in rows:
  n=row.get('name',{}); value=n.get('value','') if isinstance(n,dict) else str(n); label=n.get('localizedValue','') if isinstance(n,dict) else ''
  if want=='total' and (norm(value) in ('cores','totalregionalcores') or 'total regional vcpu' in label.lower()): return row
  if want=='family' and 'basv2' in norm(value): return row
  if want=='vms' and (norm(value)=='virtualmachines' or norm(label)=='virtualmachines'): return row
 return None
def summary(row):
 if row is None:return None
 current=int(row.get('currentValue',0)); limit=int(row.get('limit',0)); return {'current':current,'limit':limit,'remaining':limit-current}
catalog=sku_doc if isinstance(sku_doc,list) else sku_doc.get('value',[])
def sku(name):
 matches=[x for x in catalog if x.get('name')==name]
 if len(matches)!=1:return {'found':False,'count':len(matches)}
 item=matches[0]; caps={x.get('name'):x.get('value') for x in item.get('capabilities',[]) if isinstance(x,dict)}
 return {'found':True,'eastAsiaSupported':any(str(x).lower()=='eastasia' for x in item.get('locations',[])),'restrictions':item.get('restrictions',[]),'family':item.get('family'),'vCPU':caps.get('vCPUs'),'memoryGB':caps.get('MemoryGB'),'architecture':caps.get('CpuArchitectureType') or caps.get('Architecture'),'zones':sorted({str(z) for info in item.get('locationInfo',[]) if isinstance(info,dict) for z in info.get('zones',[])})}
q={'totalRegionalVcpus':summary(quota('total')),'basv2Family':summary(quota('family')),'virtualMachines':summary(quota('vms'))}
primary=sku('Standard_B2als_v2'); fallback=sku('Standard_B2as_v2')
fallback['informationalAvailable']=bool(fallback.get('found') and fallback.get('eastAsiaSupported') and fallback.get('restrictions')==[] and fallback.get('architecture')=='x64')
family_ok=primary.get('family')=='standardBasv2Family' and q['basv2Family'] is not None
out={'quota':q,'primary':primary,'fallback':fallback,'quotaFamilyMapping':family_ok}
print(json.dumps(out,indent=2))
if any(v is None for v in q.values()) or not family_ok:raise SystemExit('quota/family evidence missing')
if q['totalRegionalVcpus']['remaining']<2 or q['basv2Family']['remaining']<2 or q['virtualMachines']['remaining']<1:raise SystemExit('insufficient quota')
if not primary.get('found') or not primary.get('eastAsiaSupported') or primary.get('restrictions')!=[] or primary.get('architecture')!='x64':raise SystemExit('primary SKU unavailable or restricted')
if str(primary.get('vCPU'))!='2' or float(primary.get('memoryGB') or 0)!=4.0:raise SystemExit('primary VM spec mismatch')
if primary.get('family')!='standardBasv2Family':raise SystemExit('primary VM quota family mismatch')
PY
then stop_gate NO_GO_INSUFFICIENT_QUOTA 'quota or exact Basv2-family mapping failed; no quota request was made'; fi

safe_az vm image list --location "$REGION" --publisher Canonical --offer ubuntu-24_04-lts --sku server --all --output json >"$EVIDENCE_DIR/ubuntu-images.json" || stop_gate NO_GO_UBUNTU_IMAGE 'Ubuntu image catalog query failed'
if ! python3 - "$EVIDENCE_DIR/ubuntu-images.json" >"$EVIDENCE_DIR/ubuntu-summary.json" <<'PY'
import json,re,sys
doc=json.load(open(sys.argv[1])); rows=doc if isinstance(doc,list) else doc.get('value',[])
rows=[x for x in rows if x.get('publisher')=='Canonical' and x.get('offer')=='ubuntu-24_04-lts' and x.get('sku')=='server' and x.get('architecture')=='x64']
def key(x):return tuple(int(n) for n in re.findall(r'\d+',str(x)))
if not rows:raise SystemExit('no x64 Ubuntu 24.04 image is listed')
latest=max(rows,key=lambda x:key(x.get('version','')))
print(json.dumps({k:latest.get(k) for k in ('publisher','offer','sku','version','architecture')},indent=2))
PY
then stop_gate NO_GO_UBUNTU_IMAGE 'Canonical Ubuntu 24.04 x64 image is unavailable'; fi

safe_az postgres flexible-server list-skus --location "$REGION" --output json >"$EVIDENCE_DIR/postgres-skus.json" || stop_gate NO_GO_POSTGRES_RESTRICTED 'PostgreSQL SKU catalog query failed'
if ! python3 - "$EVIDENCE_DIR/postgres-skus.json" >"$EVIDENCE_DIR/postgres-summary.json" <<'PY'
import json,sys
doc=json.load(open(sys.argv[1])); locations=doc if isinstance(doc,list) else doc.get('value',[])
def available(x):return str(x or '')=='Available'
evaluated=[]
for location in locations:
 if not isinstance(location,dict):continue
 tiers=location.get('supportedServerEditions',[])
 burstable=[]
 for tier in tiers:
  if not isinstance(tier,dict) or str(tier.get('name','')).lower()!='burstable' or not available(tier.get('status')):continue
  for sku in tier.get('supportedServerSkus',[]):
   if isinstance(sku,dict) and str(sku.get('name','')).lower()=='standard_b1ms' and available(sku.get('status')) and not sku.get('reason'):
    burstable.append({'tierStatus':tier.get('status'),'skuStatus':sku.get('status')})
 versions=[v for v in location.get('supportedServerVersions',[]) if isinstance(v,dict) and str(v.get('name',''))=='16' and available(v.get('status'))]
 evaluated.append({'locationStatus':location.get('status'),'restricted':location.get('restricted'),'b1msBurstable':burstable,'postgres16':[v.get('status') for v in versions]})
passed=[x for x in evaluated if str(x.get('restricted','')).lower()=='disabled' and x['b1msBurstable'] and x['postgres16']]
out={'capabilityLocations':evaluated,'standardB1msBurstableAvailable':bool(passed),'postgres16Supported':bool(passed)}
print(json.dumps(out,indent=2))
if not passed:raise SystemExit('Standard_B1ms Burstable and PostgreSQL 16 support is not explicitly available or the location is restricted')
PY
then stop_gate NO_GO_POSTGRES_RESTRICTED 'Standard_B1ms Burstable/PostgreSQL 16 capability failed; no substitution was made'; fi

echo '[4C.3 Gate A] Compiling the Bicep template locally.'
if ! safe_az bicep build --file infra/main.bicep --stdout >"$EVIDENCE_DIR/bicep-build.json" 2>"$EVIDENCE_DIR/bicep-build.stderr"; then stop_gate NO_GO_IAC_COMPILE 'local Bicep compilation failed; ARM validation and What-If were not run'; fi

load_prepare_credentials() {
  ssh-keygen -q -t ed25519 -N '' -C phase4c3-validation-only -f "$TEMP_SSH_KEY" >/dev/null 2>&1 || stop_gate NO_GO_VALIDATION_CREDENTIALS 'temporary prepare key generation failed'
  SSH_PUBLIC_KEY="$(cat "$TEMP_SSH_PUB")"
  PG_PASSWORD="$(openssl rand -base64 48 | tr -d '\n')"
  printf '%s' "$PG_PASSWORD" >"$TEMP_PASSWORD"
  chmod 600 "$TEMP_SSH_KEY" "$TEMP_SSH_PUB" "$TEMP_PASSWORD"
}
load_prepare_credentials
printf '%s\n%s\n' "$SSH_PUBLIC_KEY" "$PG_PASSWORD" | python3 -c 'import json,pathlib,sys; p=pathlib.Path(sys.argv[1]); pub=sys.stdin.readline().rstrip("\n"); pw=sys.stdin.readline().rstrip("\n"); v={"location":"eastasia","resourceGroupName":"rg-pse-pulse-student-prod","vmSize":"Standard_B2als_v2","enableSsh":False,"adminSshCidr":"","deployBlob":False,"vmAdminUsername":"psepulseops","administratorLogin":"psepulseadmin","postgresVersion":"16","postgresSku":"Standard_B1ms","adminSshPublicKey":pub,"administratorPassword":pw}; d={"$schema":"https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#","contentVersion":"1.0.0.0","parameters":{k:{"value":x} for k,x in v.items()}}; p.write_text(json.dumps(d,indent=2)+"\n"); p.chmod(0o600)' "$PARAMS"
PARAM_SHA="$(shasum -a 256 "$PARAMS" | awk '{print $1}')"

echo '[4C.3 Gate A] ARM subscription-scope validation.'
if ! safe_az deployment sub validate --name 'psepulse-phase4c3-gate-a-validate' --location "$REGION" --template-file infra/main.bicep --parameters "@$PARAMS" --output json >"$EVIDENCE_DIR/arm-validation.json" 2>"$EVIDENCE_DIR/arm-validation.stderr"; then stop_gate NO_GO_ARM_VALIDATION 'subscription-scope ARM validation failed'; fi
if ! python3 - "$EVIDENCE_DIR/arm-validation.json" >"$EVIDENCE_DIR/arm-validation-summary.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); state=d.get('properties',{}).get('provisioningState') or d.get('provisioningState') or d.get('status')
print(json.dumps({'provisioningState':state}))
if state!='Succeeded':raise SystemExit(1)
PY
then stop_gate NO_GO_ARM_VALIDATION 'ARM validation did not return Succeeded'; fi
ARM_VALIDATED=true

echo '[4C.3 Gate A] Final subscription-scope What-If.'
if ! safe_az deployment sub what-if --name 'psepulse-phase4c3-gate-a-whatif' --location "$REGION" --template-file infra/main.bicep --parameters "@$PARAMS" --result-format FullResourcePayloads --no-pretty-print --output json >"$EVIDENCE_DIR/whatif.json" 2>"$EVIDENCE_DIR/whatif.stderr"; then stop_gate NO_GO_WHATIF_DRIFT 'subscription-scope What-If failed'; fi
python3 - "$EVIDENCE_DIR/whatif.json" "$EVIDENCE_DIR/whatif-summary.json" "$SUBSCRIPTION_ID" <<'PY' || stop_gate NO_GO_WHATIF_DRIFT 'exact inventory or security assertions failed'
import json,re,sys
A={'Microsoft.Resources/resourceGroups':1,'Microsoft.Network/networkSecurityGroups':1,'Microsoft.Network/virtualNetworks':1,'Microsoft.Network/publicIPAddresses':1,'Microsoft.Network/networkInterfaces':1,'Microsoft.Network/privateDnsZones':1,'Microsoft.Network/privateDnsZones/virtualNetworkLinks':1,'Microsoft.Compute/virtualMachines':1,'Microsoft.DBforPostgreSQL/flexibleServers':1}
d=json.load(open(sys.argv[1]));p=d.get('properties',d);changes=p.get('changes')
approved_subscription=sys.argv[3].lower()
if not isinstance(changes,list):raise SystemExit('missing changes')
def typ(x):
 if x.get('resourceType'):return str(x['resourceType'])
 q=[s for s in str(x.get('resourceId','')).split('/') if s]
 if 'providers' in q:
  i=q.index('providers');return q[i+1]+'/'+('/'.join(q[i+2::2]))
 if len(q)>=4 and q[-2]=='resourceGroups':return 'Microsoft.Resources/resourceGroups'
 raise SystemExit('change row lacks a valid resource type and resource ID')
R=[]
for c in changes:
 if not isinstance(c,dict):raise SystemExit('malformed row')
 t=typ(c)
 if t=='Microsoft.Resources/deployments':continue
 raw_id=str(c.get('resourceId',''))
 if not raw_id.lower().startswith('/subscriptions/'+approved_subscription+'/'):raise SystemExit('resource ID is missing or outside the approved subscription')
 R.append({'changeType':c.get('changeType'),'resourceType':t,'resourceId':re.sub(r'(?i)(/subscriptions/)[0-9a-f-]{36}',r'\1<masked>',raw_id),'after':c.get('after') or {}})
C={k:sum(x['resourceType']==k for x in R) for k in sorted({x['resourceType'] for x in R})}; ct=[str(x['changeType']).lower() for x in R]; CC={k:ct.count(k.lower()) for k in ('Create','Modify','Delete','Ignore','NoEffect','NoChange')}
statuses=[]
if 'status' in d:statuses.append(d.get('status'))
if 'provisioningState' in p:statuses.append(p.get('provisioningState'))
if not statuses or any(s!='Succeeded' for s in statuses):raise SystemExit('What-If lacks explicit successful status')
if len(R)!=9 or C!=A:raise SystemExit(f'inventory mismatch {C}')
if any(x['changeType']!='Create' for x in R) or CC!={'Create':9,'Modify':0,'Delete':0,'Ignore':0,'NoEffect':0,'NoChange':0}:raise SystemExit(f'change mismatch {CC}')
U=sorted(set(C)-set(A)); S=sum(n for k,n in C.items() if k.lower()=='microsoft.storage/storageaccounts'); Q=sum(n for k,n in C.items() if k.lower()=='microsoft.authorization/roleassignments')
if U or S or Q:raise SystemExit('unexpected type, Storage Account, or Role Assignment')
def one(t):return next(x['after'] for x in R if x['resourceType']==t)
rg=one('Microsoft.Resources/resourceGroups')
rg_name=rg.get('name') or rg['resourceId'].rstrip('/').split('/')[-1]
if rg_name!='rg-pse-pulse-student-prod' or rg.get('location')!='eastasia':raise SystemExit('resource group name/location mismatch')
for row in R:
 if row['resourceType']!='Microsoft.Resources/resourceGroups' and '/resourcegroups/rg-pse-pulse-student-prod/' not in row['resourceId'].lower():
  raise SystemExit('resource is outside the approved resource group')
v=one('Microsoft.Compute/virtualMachines');vp=v.get('properties',{});im=vp.get('storageProfile',{}).get('imageReference',{})
if vp.get('hardwareProfile',{}).get('vmSize')!='Standard_B2als_v2' or (im.get('publisher'),im.get('offer'),im.get('sku'),im.get('version'))!=('Canonical','ubuntu-24_04-lts','server','latest'):raise SystemExit('VM/image mismatch')
if v.get('identity',{}).get('type')!='SystemAssigned' or vp.get('storageProfile',{}).get('osDisk',{}).get('diskSizeGB')!=32 or vp.get('osProfile',{}).get('linuxConfiguration',{}).get('disablePasswordAuthentication') is not True:raise SystemExit('VM identity/disk/auth mismatch')
rules=one('Microsoft.Network/networkSecurityGroups').get('properties',{}).get('securityRules',[]);allow=[x.get('properties',{}) for x in rules if str(x.get('properties',{}).get('direction','')).lower()=='inbound' and str(x.get('properties',{}).get('access','')).lower()=='allow']
if len(rules)!=1 or len(allow)!=1:raise SystemExit('NSG must have exactly one inbound allow rule')
r=allow[0]
if str(r.get('protocol','')).lower()!='tcp' or r.get('sourceAddressPrefix')!='Internet' or r.get('sourcePortRange')!='*' or r.get('destinationAddressPrefix')!='*' or r.get('destinationPortRange')!='443' or r.get('priority')!=100 or any(k in r for k in ('sourceAddressPrefixes','destinationAddressPrefixes','sourcePortRanges','destinationPortRanges')):raise SystemExit('unsafe or non-exact NSG rule')
x=one('Microsoft.DBforPostgreSQL/flexibleServers');xp=x.get('properties',{})
if x.get('sku',{}).get('name')!='Standard_B1ms' or x.get('sku',{}).get('tier')!='Burstable' or xp.get('version')!='16' or xp.get('storage',{}).get('storageSizeGB')!=32:raise SystemExit('PostgreSQL SKU/version/storage mismatch')
if xp.get('network',{}).get('publicNetworkAccess')!='Disabled' or xp.get('highAvailability',{}).get('mode')!='Disabled' or xp.get('backup',{}).get('geoRedundantBackup')!='Disabled' or xp.get('backup',{}).get('backupRetentionDays')!=7:raise SystemExit('PostgreSQL security/backup mismatch')
if not xp.get('network',{}).get('delegatedSubnetResourceId') or not xp.get('network',{}).get('privateDnsZoneArmResourceId'):raise SystemExit('PostgreSQL private references absent')
x=one('Microsoft.Network/virtualNetworks').get('properties',{});subs=x.get('subnets',[])
if x.get('addressSpace',{}).get('addressPrefixes')!=['10.20.0.0/16'] or len(subs)!=2:raise SystemExit('VNet mismatch')
sm={s.get('name'):s.get('properties',{}) for s in subs}
if sm.get('snet-app',{}).get('addressPrefix')!='10.20.1.0/24' or sm.get('snet-postgres',{}).get('addressPrefix')!='10.20.2.0/24':raise SystemExit('subnet CIDR mismatch')
if not any(a.get('properties',{}).get('serviceName')=='Microsoft.DBforPostgreSQL/flexibleServers' for a in sm.get('snet-postgres',{}).get('delegations',[])):raise SystemExit('PostgreSQL delegation absent')
x=one('Microsoft.Network/publicIPAddresses')
if x.get('sku',{}).get('name')!='Standard' or x.get('properties',{}).get('publicIPAllocationMethod')!='Static' or x.get('properties',{}).get('publicIPAddressVersion')!='IPv4':raise SystemExit('public IP mismatch')
z=one('Microsoft.Network/privateDnsZones');l=one('Microsoft.Network/privateDnsZones/virtualNetworkLinks')
vnet_row=next(x for x in R if x['resourceType']=='Microsoft.Network/virtualNetworks')
link_vnet=l.get('properties',{}).get('virtualNetwork',{}).get('id','')
masked_link_vnet=re.sub(r'(?i)(/subscriptions/)[0-9a-f-]{36}',r'\1<masked>',link_vnet)
if z.get('name')!='private.postgres.database.azure.com' or l.get('properties',{}).get('registrationEnabled') is not False or masked_link_vnet.lower()!=vnet_row['resourceId'].lower():raise SystemExit('private DNS zone/link mismatch')
n={x['resourceType']:x['after'].get('name') or x['resourceId'].rstrip('/').split('/')[-1] for x in R};O={'status':'Succeeded','nonMetadataRowCount':9,'changeTypeCounts':CC,'resourceTypeCounts':C,'unexpectedResourceTypes':U,'storageAccountCount':S,'roleAssignmentCount':Q,'securityAssertions':'passed','resourceNames':n,'resourceIds':{x['resourceType']:x['resourceId'] for x in R}}
with open(sys.argv[2],'w') as f:json.dump(O,f,indent=2);f.write('\n')
print(json.dumps(O,indent=2))
PY
WHATIF_ACCEPTED=true
cat "$EVIDENCE_DIR/whatif-summary.json"
echo '[4C.3 Gate A] Rechecking provider states and target resource-group absence after What-If.'
: >"$EVIDENCE_DIR/providers-after.tsv"
for provider in "${POST_PROVIDERS[@]}"; do
  state="$(safe_az provider show --namespace "$provider" --query registrationState --output tsv)" || stop_gate NO_GO_PROVIDER_STATE "could not reread provider state: $provider"
  printf '%s\t%s\n' "$provider" "$state" >>"$EVIDENCE_DIR/providers-after.tsv"
  if [[ "$provider" == Microsoft.Storage ]]; then [[ "$state" == NotRegistered ]] || stop_gate NO_GO_PROVIDER_STATE 'Microsoft.Storage changed'
  else [[ "$state" == Registered ]] || stop_gate NO_GO_PROVIDER_STATE "$provider changed"; fi
done
rg_after="$(safe_az group exists --name "$RESOURCE_GROUP" --output tsv)" || stop_gate NO_GO_RESOURCE_GROUP 'post-What-If resource-group check failed'
printf '%s\n' "$rg_after" >"$EVIDENCE_DIR/resource-group-after.txt"
[[ "$rg_after" == false ]] || stop_gate NO_GO_RESOURCE_GROUP 'target resource group exists after What-If; no cleanup was attempted'

printf 'TECHNICAL_PREFLIGHT: PASS\nPHASE 4C.3 GATE A: NO_GO_BILLING_SAFETY\nAZURE_INFRASTRUCTURE_NOT_DEPLOYED\nOWNER_DEPLOYMENT_AUTHORIZATION: NOT_GRANTED\n'
printf 'Billing, offer, credit expiry, payment, spending-limit behavior, monthly budget/alerts, and current cost require owner reconfirmation.\n'
printf 'Azure infrastructure resources created: 0\nAzure infrastructure resources modified: 0\nAzure infrastructure resources deleted: 0\nAzure mutation commands: 0\n'
