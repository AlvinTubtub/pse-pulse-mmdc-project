#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly PHASE4C1_BASE='4e8c536d8e191f158189f1d3997411b86648cf16'
readonly REGION='eastasia'
readonly RESOURCE_GROUP='rg-pse-pulse-student-prod'
readonly EVIDENCE_DIR='/tmp/pse-pulse-phase4c2'
readonly PARAMS="$EVIDENCE_DIR/validation.parameters.json"
readonly SSH_KEY="$EVIDENCE_DIR/validation_ssh"
readonly SSH_PUB="$EVIDENCE_DIR/validation_ssh.pub"
readonly PG_PASSWORD="$EVIDENCE_DIR/validation_pg_password"
readonly -a PROVIDERS=(Microsoft.Resources Microsoft.Authorization Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL Microsoft.Storage)
readonly -a IAC_FILES=(infra/main.bicep infra/modules/network.bicep infra/modules/compute.bicep infra/modules/postgres.bicep infra/modules/storage.bicep infra/parameters/phase4b.eastasia.bicepparam)
readonly ROOT="$(git rev-parse --show-toplevel)"

cd "$ROOT"
mkdir -p "$EVIDENCE_DIR"
chmod 700 "$EVIDENCE_DIR"
rm -f "$EVIDENCE_DIR/failure-gate.txt"

cleanup() {
  rm -f -- "$SSH_KEY" "$SSH_PUB" "$PG_PASSWORD" "$PARAMS"
}
trap cleanup EXIT

stop_gate() {
  printf '%s\n' "$1" >"$EVIDENCE_DIR/failure-gate.txt"
  printf 'PHASE 4C.2 STOP [%s]: %s\n' "$1" "$2" >&2
  exit 20
}

echo '[4C.2] Repository and baseline guards.'
[[ "$(git branch --show-current)" == main ]] || stop_gate NO_GO_REPOSITORY_BASELINE 'branch is not main'
git merge-base --is-ancestor "$PHASE4C1_BASE" HEAD || stop_gate NO_GO_REPOSITORY_BASELINE 'Phase 4C.1 baseline is not an ancestor'
[[ "$(git rev-parse HEAD)" == "$PHASE4C1_BASE" ]] || stop_gate NO_GO_REPOSITORY_BASELINE 'HEAD is not the accepted Phase 4C.1 commit'
git diff --quiet || stop_gate NO_GO_REPOSITORY_BASELINE 'tracked changes exist'
git diff --cached --quiet || stop_gate NO_GO_REPOSITORY_BASELINE 'staged changes exist'
[[ -z "$(git diff --name-only c5baf980d9c15a8913e155cbb0769dda70dab017 HEAD -- infra/ scripts/azure_phase4b_preflight.sh scripts/azure_phase4b_whatif.sh backend/tests/test_phase4b_iac_safety.py)" ]] || stop_gate NO_GO_IAC_INTEGRITY 'Phase 4B implementation files changed'

echo '[4C.2] Static IaC contract check and candidate hashes.'
python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys
r=Path(sys.argv[1]); main=(r/'infra/main.bicep').read_text(); net=(r/'infra/modules/network.bicep').read_text(); vm=(r/'infra/modules/compute.bicep').read_text(); pg=(r/'infra/modules/postgres.bicep').read_text(); storage=(r/'infra/modules/storage.bicep').read_text(); par=(r/'infra/parameters/phase4b.eastasia.bicepparam').read_text()
checks={
 'subscription scope':"targetScope = 'subscription'" in main,
 'East Asia':"param location = 'eastasia'" in par,
 'B2als primary':"param vmSize = 'Standard_B2als_v2'" in par,
 'Blob disabled': 'param deployBlob = false' in par,
 'SSH disabled': 'param enableSsh = false' in par,
 'VM admin psepulseops':"param vmAdminUsername = 'psepulseops'" in par,
 'PostgreSQL admin psepulseadmin':"param administratorLogin = 'psepulseadmin'" in par,
 'PostgreSQL 16/B1ms':"param postgresVersion = '16'" in par and "param postgresSku = 'Standard_B1ms'" in par,
 'HTTPS 443':"destinationPortRange: '443'" in net,
 'No public 8000/5432 rule':all(x not in net for x in ('8000','5432')),
 'Standard static IPv4':all(x in net for x in ("name: 'Standard'","publicIPAllocationMethod: 'Static'","publicIPAddressVersion: 'IPv4'")),
 'Ubuntu 24.04 latest x64 contract':all(x in vm for x in ("publisher: 'Canonical'","offer: 'ubuntu-24_04-lts'","sku: 'server'","version: 'latest'")),
 '32 GiB Standard SSD': 'diskSizeGB: 32' in vm and "storageAccountType: 'StandardSSD_LRS'" in vm,
 'PostgreSQL private 7-day no HA/no geo':all(x in pg for x in ("publicNetworkAccess: 'Disabled'",'backupRetentionDays: 7',"geoRedundantBackup: 'Disabled'","mode: 'Disabled'",'delegatedSubnetResourceId:','privateDnsZoneArmResourceId:')),
 'Optional storage resources conditional':storage.count('= if (deployBlob)')==4,
 'No unrelated baseline services':all(x not in main+net+vm+pg+storage for x in ('Microsoft.Network/natGateways','Microsoft.Network/bastionHosts','Microsoft.Network/azureFirewalls','Microsoft.Network/loadBalancers','Microsoft.ContainerService/managedClusters','Microsoft.App/containerApps','Microsoft.Network/privateEndpoints')),
}
for k,v in checks.items(): print(f'{"PASS" if v else "FAIL"}: {k}')
if not all(checks.values()): raise SystemExit(1)
PY
for f in "${IAC_FILES[@]}"; do git cat-file -e "HEAD:$f" || stop_gate NO_GO_IAC_INTEGRITY "not committed: $f"; done
sha256sum "${IAC_FILES[@]}" >"$EVIDENCE_DIR/iac-sha256.txt"
cat "$EVIDENCE_DIR/iac-sha256.txt"

echo '[4C.2] Local Bicep build.'
if ! az bicep build --file infra/main.bicep --stdout >"$EVIDENCE_DIR/main.arm.json" 2>"$EVIDENCE_DIR/bicep-build.stderr"; then
  cat "$EVIDENCE_DIR/bicep-build.stderr" >&2
  stop_gate NO_GO_IAC_COMPILE 'Bicep build failed; IaC was not modified'
fi
chmod 600 "$EVIDENCE_DIR/main.arm.json" "$EVIDENCE_DIR/bicep-build.stderr"
echo 'Bicep build succeeded.'

# All Azure operations are checked here. This permits read-only queries plus only the explicitly authorized validate/what-if operations.
safe_az() {
  local s="${1:-}" o="${2:-}" t="${3:-}"
  case "$s:$o:$t" in
    account:show:*|provider:show:*|group:exists:*|policy:assignment:list|policy:assignment:show|policy:definition:show|vm:list-usage:*|vm:list-skus:*|vm:image:list|postgres:flexible-server:list-skus|deployment:sub:validate|deployment:sub:what-if|rest:--method:*) ;;
    *) echo "FAIL: unapproved Azure command: az $s $o $t" >&2; return 64 ;;
  esac
  if [[ "$s:$o" == rest:--method ]]; then
    local arg found=false
    for arg in "$@"; do case "$arg" in GET|get) found=true ;; esac; done
    [[ "$found" == true ]] || { echo 'FAIL: REST is GET-only.' >&2; return 64; }
  fi
  az "$@"
}

echo '[4C.2] Subscription, provider, and resource-group guards.'
account="$(safe_az account show --output json 2>"$EVIDENCE_DIR/account.stderr")" || stop_gate NO_GO_AZURE_AUTH_CONTEXT 'az account show could not use the existing authenticated Azure CLI context'
summary="$(printf '%s' "$account" | python3 -c 'import json,sys; d=json.load(sys.stdin); sid=d.get("id",""); m=(sid[:8]+"-****-****-****-"+sid[-4:]) if len(sid)>=13 else "UNAVAILABLE"; print("\t".join((d.get("name",""),d.get("state",""),m,sid)))')"
IFS=$'\t' read -r SUB_NAME SUB_STATE SUB_MASKED SUB_ID <<<"$summary"
unset account summary
printf 'Subscription: %s / %s; masked ID %s\n' "$SUB_NAME" "$SUB_STATE" "$SUB_MASKED"
[[ "$SUB_NAME" == 'Azure for Students' && "$SUB_STATE" == Enabled ]] || stop_gate NO_GO_SUBSCRIPTION 'expected Azure for Students / Enabled'
: >"$EVIDENCE_DIR/providers-before.tsv"
for p in "${PROVIDERS[@]}"; do
  state="$(safe_az provider show --namespace "$p" --query registrationState --output tsv)" || stop_gate NO_GO_PROVIDER_STATE "cannot read $p"
  printf '%s\t%s\n' "$p" "$state" | tee -a "$EVIDENCE_DIR/providers-before.tsv"
  if [[ "$p" == Microsoft.Storage ]]; then [[ "$state" == NotRegistered ]] || stop_gate NO_GO_PROVIDER_STATE 'Microsoft.Storage is not NotRegistered'
  else [[ "$state" == Registered ]] || stop_gate NO_GO_PROVIDER_STATE "$p is not Registered"; fi
done
rg_before="$(safe_az group exists --name "$RESOURCE_GROUP" --output tsv)" || stop_gate NO_GO_RESOURCE_GROUP 'resource group query failed'
printf '%s\n' "$rg_before" >"$EVIDENCE_DIR/resource-group-before.txt"
echo "Resource group exists before validation: $rg_before"
[[ "$rg_before" == false ]] || stop_gate NO_GO_RESOURCE_GROUP 'target resource group already exists'

echo '[4C.2] East Asia policy recheck.'
safe_az policy assignment list --scope "/subscriptions/$SUB_ID" --disable-scope-strict-match true --output json >"$EVIDENCE_DIR/policy-assignments.json" || stop_gate NO_GO_POLICY_CHANGED 'policy assignment query failed'
safe_az policy definition show --name sys.regionrestriction --output json >"$EVIDENCE_DIR/policy-definition.json" 2>"$EVIDENCE_DIR/policy-definition.stderr" || true
if ! python3 - "$EVIDENCE_DIR/policy-assignments.json" >"$EVIDENCE_DIR/policy-summary.txt" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); rows=d if isinstance(d,list) else d.get('value',[]); found=[]
def collect(x):
 out=[]
 if isinstance(x,dict):
  for k,v in x.items():
   if 'location' in k.lower() or 'allowed' in k.lower(): out+=collect(v)
   elif isinstance(v,(dict,list)): out+=collect(v)
 elif isinstance(x,list):
  for v in x: out+=collect(v)
 elif isinstance(x,str): out.append(x)
 return out
for a in rows:
 p=a.get('properties',a); name=a.get('name',''); display=p.get('displayName','')
 if name=='sys.regionrestriction' or 'regionrestriction' in str(p.get('policyDefinitionId','')).lower() or 'allowed resource deployment regions' in str(display).lower():
  vals=sorted(set(collect(p.get('parameters',{})))); found.append((name,display,vals))
for n,dsp,vals in found: print(f'assignment={n}; display={dsp}; allowed={",".join(vals)}')
if not found or not any(any(v.lower()=='eastasia' for v in vals) for _,_,vals in found): raise SystemExit(1)
PY
then stop_gate NO_GO_POLICY_CHANGED 'sys.regionrestriction does not explicitly allow eastasia'; fi
cat "$EVIDENCE_DIR/policy-summary.txt"

echo '[4C.2] Authoritative East Asia quota and VM SKU catalog.'
safe_az vm list-usage --location "$REGION" --output json >"$EVIDENCE_DIR/vm-usage.json" || stop_gate NO_GO_INSUFFICIENT_QUOTA 'VM usage query failed'
sku_url="https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Compute/skus?api-version=2021-07-01&%24filter=location%20eq%20%27$REGION%27"
safe_az rest --method GET --url "$sku_url" --output json >"$EVIDENCE_DIR/compute-skus.json" || stop_gate NO_GO_PRIMARY_VM_RESTRICTED 'GET-only Compute SKU query failed'
if python3 - "$EVIDENCE_DIR/vm-usage.json" "$EVIDENCE_DIR/compute-skus.json" "$EVIDENCE_DIR/compute-skus.json" >"$EVIDENCE_DIR/quota-sku-summary.json" <<'PY'
import json,re,sys
usage=json.load(open(sys.argv[1])); primary=json.load(open(sys.argv[2])); fallback=json.load(open(sys.argv[3]))
def norm(x): return re.sub('[^a-z0-9]','',str(x).lower())
rows=usage if isinstance(usage,list) else usage.get('value',[])
def qrow(kind):
 for r in rows:
  n=r.get('name',{}); value=n.get('value','') if isinstance(n,dict) else str(n); label=n.get('localizedValue','') if isinstance(n,dict) else ''
  if kind=='cores' and (norm(value) in ('cores','totalregionalcores') or 'total regional vcpu' in label.lower()): return r
  if kind=='vms' and (norm(value)=='virtualmachines' or norm(label)=='virtualmachines'): return r
  if kind=='family' and 'basv2' in norm(value): return r
 return None
def quota(r):
 if r is None:return None
 c=int(r.get('currentValue',0)); l=int(r.get('limit',0)); return {'current':c,'limit':l,'remaining':l-c}
def getsku(doc,name):
 items=doc if isinstance(doc,list) else doc.get('value',[])
 m=[x for x in items if x.get('name')==name]
 if len(m)!=1:return {'found':False,'count':len(m)}
 x=m[0]; caps={c.get('name'):c.get('value') for c in x.get('capabilities',[]) if isinstance(c,dict)}
 return {'found':True,'eastAsiaSupported':any(norm(v)=='eastasia' for v in x.get('locations',[])),'locations':x.get('locations',[]),'restrictions':x.get('restrictions',[]),'family':x.get('family',''),'vCPU':caps.get('vCPUs') or caps.get('vCPU'),'memoryGB':caps.get('MemoryGB'),'architecture':caps.get('CpuArchitectureType') or caps.get('Architecture'),'zones':sorted({str(z) for l in x.get('locationInfo',[]) if isinstance(l,dict) for z in l.get('zones',[])}),'capabilities':caps}
q={'totalRegionalVcpus':quota(qrow('cores')),'basv2Family':quota(qrow('family')),'virtualMachines':quota(qrow('vms'))}
p=getsku(primary,'Standard_B2als_v2'); f=getsku(fallback,'Standard_B2as_v2')
family_mapping=bool(p.get('family') and 'basv2' in norm(p.get('family')) and qrow('family') is not None)
out={'quota':q,'primary':p,'fallback':f,'quotaFamilyMapping':{'skuFamily':p.get('family'),'quotaFamilyName':'Standard Basv2 Family vCPUs','establishedByCurrentSkuFamilyMetadata':family_mapping}}
print(json.dumps(out,indent=2))
if not all(q[k] for k in q):raise SystemExit(2)
if not family_mapping:raise SystemExit(3)
if q['totalRegionalVcpus']['remaining']<2 or q['basv2Family']['remaining']<2 or q['virtualMachines']['remaining']<1:raise SystemExit(4)
for x,name in ((p,'primary'),(f,'fallback')):
 if not x.get('found') or not x.get('eastAsiaSupported') or x.get('restrictions')!=[] or norm(x.get('architecture')) not in ('x64','amd64'):
  raise SystemExit(5 if name=='primary' else 6)
if str(p.get('vCPU'))!='2' or float(p.get('memoryGB') or 0)<3.9 or float(p.get('memoryGB') or 0)>4.1:raise SystemExit(5)
PY
then
  :
else
  code=$?
  case "$code" in 5) stop_gate NO_GO_PRIMARY_VM_RESTRICTED 'primary VM lacks supported x64 metadata or has a restriction/spec mismatch' ;; 6) stop_gate NO_GO_PRIMARY_VM_RESTRICTED 'fallback catalog is not viable; no automatic substitution' ;; *) stop_gate NO_GO_INSUFFICIENT_QUOTA 'fresh quota or exact Basv2 family mapping failed' ;; esac
fi
cat "$EVIDENCE_DIR/quota-sku-summary.json"

echo '[4C.2] Rechecking Ubuntu image and PostgreSQL capability.'
safe_az vm image list --location "$REGION" --publisher Canonical --offer ubuntu-24_04-lts --sku server --all --output json >"$EVIDENCE_DIR/ubuntu-images.json" || stop_gate NO_GO_UBUNTU_IMAGE 'Ubuntu image query failed'
python3 - "$EVIDENCE_DIR/ubuntu-images.json" >"$EVIDENCE_DIR/ubuntu-summary.json" <<'PY'
import json,re,sys
data=json.load(open(sys.argv[1])); rows=data if isinstance(data,list) else data.get('value',[])
rows=[x for x in rows if x.get('publisher')=='Canonical' and x.get('offer')=='ubuntu-24_04-lts' and x.get('sku')=='server']
if not rows:raise SystemExit('Canonical Ubuntu image not found')
def vkey(x):return tuple(int(n) for n in re.findall(r'\d+',str(x)))
latest=max(rows,key=lambda x:vkey(x.get('version','')))
out={k:latest.get(k) for k in ('publisher','offer','sku','version','architecture','osArchitecture') if k in latest}
out.setdefault('architecture',out.get('osArchitecture','not exposed by az vm image list'))
print(json.dumps(out,indent=2))
if out['architecture'] not in ('x64','X64','amd64','AMD64'):raise SystemExit('image architecture is not explicitly reported as x64')
PY
cat "$EVIDENCE_DIR/ubuntu-summary.json"

safe_az postgres flexible-server list-skus --location "$REGION" --output json >"$EVIDENCE_DIR/postgres-skus.json" || stop_gate NO_GO_POSTGRES_RESTRICTED 'PostgreSQL SKU catalog query failed'
if ! python3 - "$EVIDENCE_DIR/postgres-skus.json" >"$EVIDENCE_DIR/postgres-summary.json" <<'PY'
import json,sys
data=json.load(open(sys.argv[1])); matches=[]
def walk(x,parents=()):
 if isinstance(x,dict):
  if x.get('name')=='Standard_B1ms':matches.append({'parents':list(parents),'sku':x})
  for k,v in x.items():walk(v,parents+(k,))
 elif isinstance(x,list):
  for v in x:walk(v,parents)
walk(data)
def flatten(x):
 if isinstance(x,dict):return ' '.join(str(k)+' '+flatten(v) for k,v in x.items())
 if isinstance(x,list):return ' '.join(flatten(v) for v in x)
 return str(x)
context=flatten(matches); alltext=flatten(data)
restricted=('restricted' in context.lower() and 'false' not in context.lower() and 'disabled' not in context.lower())
summary={'matches':matches,'burstableVisible':'Burstable' in context or 'Burstable' in alltext,'postgres16Visible':'16' in alltext,'restrictionExplicitlyEnabled':restricted}
print(json.dumps(summary,indent=2))
if not matches or not summary['burstableVisible'] or restricted:raise SystemExit(1)
PY
then stop_gate NO_GO_POSTGRES_RESTRICTED 'B1ms is missing, not Burstable, or explicitly restricted'; fi
cat "$EVIDENCE_DIR/postgres-summary.json"

echo '[4C.2] Generating validation-only temporary credentials and parameters.'
ssh-keygen -q -t ed25519 -N '' -C phase4c2-validation-only -f "$SSH_KEY" >/dev/null 2>&1 || stop_gate NO_GO_TEMP_CREDENTIALS 'ephemeral SSH key generation failed'
openssl rand -base64 48 >"$PG_PASSWORD"
chmod 600 "$SSH_KEY" "$SSH_PUB" "$PG_PASSWORD"
python3 - "$SSH_PUB" "$PG_PASSWORD" "$PARAMS" <<'PY'
from pathlib import Path
import json,sys
pub=Path(sys.argv[1]).read_text().strip(); password=Path(sys.argv[2]).read_text().strip()
values={'location':'eastasia','resourceGroupName':'rg-pse-pulse-student-prod','vmSize':'Standard_B2als_v2','enableSsh':False,'adminSshCidr':'','deployBlob':False,'vmAdminUsername':'psepulseops','administratorLogin':'psepulseadmin','postgresVersion':'16','postgresSku':'Standard_B1ms','adminSshPublicKey':pub,'administratorPassword':password}
doc={'$schema':'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#','contentVersion':'1.0.0.0','parameters':{k:{'value':v} for k,v in values.items()}}
p=Path(sys.argv[3]); p.write_text(json.dumps(doc,indent=2)+'\n'); p.chmod(0o600)
PY

echo '[4C.2] ARM subscription-scope validation.'
if ! safe_az deployment sub validate --name phase4c2-validate-eastasia --location "$REGION" --template-file infra/main.bicep --parameters "@$PARAMS" --output json >"$EVIDENCE_DIR/arm-validation.json" 2>"$EVIDENCE_DIR/arm-validation.stderr"; then
  stop_gate NO_GO_ARM_VALIDATION 'ARM validation failed; What-If was not attempted'
fi
python3 - "$EVIDENCE_DIR/arm-validation.json" >"$EVIDENCE_DIR/arm-validation-summary.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); state=d.get('properties',{}).get('provisioningState') or d.get('provisioningState') or d.get('status')
print(json.dumps({'provisioningState':state}))
if state!='Succeeded': raise SystemExit(1)
PY
cat "$EVIDENCE_DIR/arm-validation-summary.json"

echo '[4C.2] Final subscription-scope What-If (non-deploying).'
if ! safe_az deployment sub what-if --name phase4c2-final-whatif-eastasia --location "$REGION" --template-file infra/main.bicep --parameters "@$PARAMS" --result-format FullResourcePayloads --no-pretty-print --output json >"$EVIDENCE_DIR/whatif.json" 2>"$EVIDENCE_DIR/whatif.stderr"; then
  stop_gate NO_GO_WHATIF_DRIFT 'What-If failed; no deployment was attempted'
fi
if ! python3 - "$EVIDENCE_DIR/whatif.json" >"$EVIDENCE_DIR/whatif-summary.json" <<'PY'
import copy,json,re,sys
EXPECTED={
 'Microsoft.Resources/resourceGroups':1,
 'Microsoft.Network/networkSecurityGroups':1,
 'Microsoft.Network/virtualNetworks':1,
 'Microsoft.Network/publicIPAddresses':1,
 'Microsoft.Network/networkInterfaces':1,
 'Microsoft.Network/privateDnsZones':1,
 'Microsoft.Network/privateDnsZones/virtualNetworkLinks':1,
 'Microsoft.Compute/virtualMachines':1,
 'Microsoft.DBforPostgreSQL/flexibleServers':1,
}
def typ(c):
 t=c.get('resourceType')
 if t:return t
 seg=[x for x in c.get('resourceId','').split('/') if x]
 if 'providers' in seg:
  i=seg.index('providers');return seg[i+1]+'/'+ '/'.join(seg[i+2::2])
 return 'Microsoft.Resources/resourceGroups'
def summarize(doc):
 p=doc.get('properties',doc); changes=p.get('changes',[]); rows=[]
 for c in changes:
  t=typ(c)
  if t=='Microsoft.Resources/deployments':continue
  rows.append({'changeType':c.get('changeType'),'resourceType':t,'resourceId':re.sub(r'(?i)(/subscriptions/)[0-9a-f-]{36}',r'\1<masked>',c.get('resourceId','')),'after':c.get('after') or {}})
 types={t:sum(1 for x in rows if x['resourceType']==t) for t in sorted({x['resourceType'] for x in rows})}
 kinds=[str(x['changeType']).lower() for x in rows]
 out={'status':p.get('provisioningState') or doc.get('status'),'rowCount':len(rows),'changeTypeCounts':{t:kinds.count(t.lower()) for t in ('Create','Modify','Delete','Ignore','NoEffect','NoChange')},'createCount':kinds.count('create'),'modifyCount':kinds.count('modify'),'deleteCount':kinds.count('delete'),'ignoreCount':kinds.count('ignore'),'noEffectCount':kinds.count('noeffect'),'noChangeCount':kinds.count('nochange'),'resourceTypeCounts':types,'plannedResourceTypes':sorted(set(types)),'unexpectedResourceTypes':sorted(set(types)-set(EXPECTED)),'storageAccountCount':sum(1 for t,n in types.items() if t.lower()=='microsoft.storage/storageaccounts' for _ in range(n)),'roleAssignmentCount':sum(1 for t,n in types.items() if t.lower()=='microsoft.authorization/roleassignments' for _ in range(n)),'changes':[{k:v for k,v in x.items() if k!='after'} for x in rows]}
 valid=(out['status'] in (None,'Succeeded') and len(rows)==9 and types==EXPECTED and out['createCount']==9 and out['modifyCount']==0 and out['deleteCount']==0 and out['ignoreCount']==0 and out['noEffectCount']==0 and out['noChangeCount']==0 and out['unexpectedResourceTypes']==[] and out['storageAccountCount']==0 and out['roleAssignmentCount']==0 and all(x['changeType']=='Create' for x in rows))
 return out,valid

# Exercise the exact-count gate against the required drift cases before trusting Azure output.
fixtures=[{'changeType':'Create','resourceType':t} for t in EXPECTED for _ in range(EXPECTED[t])]
def doc(rows):return {'status':'Succeeded','changes':rows}
def rejected(label,mutate):
 candidate=copy.deepcopy(fixtures);mutate(candidate)
 _,accepted=summarize(doc(candidate))
 if accepted:raise SystemExit('validator self-test accepted drift: '+label)
tests=[
 ('two NSGs and no public IP',lambda x:(x.__setitem__(next(i for i,r in enumerate(x) if r['resourceType']=='Microsoft.Network/publicIPAddresses'),{'changeType':'Create','resourceType':'Microsoft.Network/networkSecurityGroups'}))),
 ('two NICs and no DNS link',lambda x:(x.__setitem__(next(i for i,r in enumerate(x) if r['resourceType']=='Microsoft.Network/privateDnsZones/virtualNetworkLinks'),{'changeType':'Create','resourceType':'Microsoft.Network/networkInterfaces'}))),
 ('missing approved type',lambda x:x.pop(next(i for i,r in enumerate(x) if r['resourceType']=='Microsoft.Network/publicIPAddresses'))),
 ('duplicate approved type',lambda x:x.append({'changeType':'Create','resourceType':'Microsoft.Network/publicIPAddresses'})),
 ('tenth non-metadata resource',lambda x:x.append({'changeType':'Create','resourceType':'Microsoft.Network/loadBalancers'})),
 ('unexpected resource type',lambda x:x.__setitem__(next(i for i,r in enumerate(x) if r['resourceType']=='Microsoft.Network/publicIPAddresses'),{'changeType':'Create','resourceType':'Microsoft.Network/loadBalancers'})),
 ('Modify',lambda x:x[0].update(changeType='Modify')),
 ('Delete',lambda x:x[0].update(changeType='Delete')),
 ('Ignore',lambda x:x[0].update(changeType='Ignore')),
 ('NoEffect',lambda x:x[0].update(changeType='NoEffect')),
 ('NoChange',lambda x:x[0].update(changeType='NoChange')),
 ('Storage Account',lambda x:x.append({'changeType':'Create','resourceType':'Microsoft.Storage/storageAccounts'})),
 ('Role Assignment',lambda x:x.append({'changeType':'Create','resourceType':'Microsoft.Authorization/roleAssignments'})),
]
for label,mutate in tests:rejected(label,mutate)

d=json.load(open(sys.argv[1])); out,valid=summarize(d)
out['exactInventoryNegativeCases']='passed (%d cases)'%len(tests)
print(json.dumps(out,indent=2))
if not valid:raise SystemExit(1)
PY
then
  cat "$EVIDENCE_DIR/whatif-summary.json"
  stop_gate NO_GO_WHATIF_DRIFT 'What-If inventory differs from the exact approved 9-resource Create plan'
fi
cat "$EVIDENCE_DIR/whatif-summary.json"

echo '[4C.2] Post-What-If resource-group and provider recheck.'
rg_after="$(safe_az group exists --name "$RESOURCE_GROUP" --output tsv)" || stop_gate UNEXPECTED_AZURE_MUTATION_DETECTED 'resource group recheck failed'
printf '%s\n' "$rg_after" >"$EVIDENCE_DIR/resource-group-after.txt"
[[ "$rg_after" == false ]] || stop_gate UNEXPECTED_AZURE_MUTATION_DETECTED 'resource group unexpectedly exists after What-If'
: >"$EVIDENCE_DIR/providers-after.tsv"
for p in Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL Microsoft.Storage; do
  state="$(safe_az provider show --namespace "$p" --query registrationState --output tsv)" || stop_gate NO_GO_PROVIDER_STATE "cannot reread $p"
  printf '%s\t%s\n' "$p" "$state" | tee -a "$EVIDENCE_DIR/providers-after.tsv"
  if [[ "$p" == Microsoft.Storage ]]; then [[ "$state" == NotRegistered ]] || stop_gate NO_GO_PROVIDER_STATE 'Microsoft.Storage changed'
  else [[ "$state" == Registered ]] || stop_gate NO_GO_PROVIDER_STATE "$p changed"; fi
done
echo 'DEPLOYMENT_CAPACITY_STATUS: PRECHECK_PASS_CAPACITY_NOT_GUARANTEED'
echo 'NO AZURE INFRASTRUCTURE RESOURCES WERE CREATED, MODIFIED, OR DEPLOYED.'
echo "Evidence is under $EVIDENCE_DIR; temporary SSH keys, PostgreSQL password, and parameter JSON are removed on exit."
