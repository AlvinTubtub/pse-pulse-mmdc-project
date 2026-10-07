from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "infra"
SCRIPTS = ROOT / "scripts"
BASELINE = INFRA / "parameters" / "phase4b.eastasia.bicepparam"
PARAMETER_FILES = {
    "eastasia": BASELINE,
    "southeastasia": INFRA / "parameters" / "phase4b.southeastasia.bicepparam",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def all_bicep() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in INFRA.rglob("*.bicep"))


def test_root_is_subscription_scoped_and_baseline_is_nonsecret() -> None:
    root = read(INFRA / "main.bicep")
    assert "targetScope = 'subscription'" in root
    assert "param location string\n" in root
    assert "param location string =" not in root
    assert "@secure()\nparam administratorPassword string" in root
    assert "param vmAdminUsername string = 'psepulseops'" in root
    # psepulse is reserved for the future non-root application service account.
    assert "param vmAdminUsername string = 'psepulse'" not in root
    for region, path in PARAMETER_FILES.items():
        params = read(path)
        assert f"param location = '{region}'" in params
        assert "param vmAdminUsername = 'psepulseops'" in params
        assert not re.search(r"^param vmAdminUsername = 'psepulse'$", params, re.MULTILINE)
        assert "deployBlob = false" in params
        assert "enableSsh = false" in params
        assert not re.search(r"(?i)(password|secret|token|subscriptionId|tenantId)\s*=", params)
        assert not re.search(r"(?i)(/subscriptions/|/tenants/)[0-9a-f-]{36}", params)


def test_network_and_compute_security_baseline() -> None:
    network = read(INFRA / "modules" / "network.bicep")
    compute = read(INFRA / "modules" / "compute.bicep")
    assert "enableSsh bool = false" in network
    assert "destinationPortRange: '443'" in network
    assert "destinationPortRange: '22'" in network
    assert "enableSsh ?" in network
    assert "sourceAddressPrefix: adminSshCidr" in network
    assert "disablePasswordAuthentication: true" in compute
    assert "StandardSSD_LRS" in compute
    assert "ubuntu-24_04-lts" in compute
    assert not re.search(r"destinationPortRange:\s*'8000'", network)
    assert not re.search(r"destinationPortRange:\s*'5432'", network)
    assert "param adminSshCidr string = ''" in network
    assert not re.search(r"sourceAddressPrefix:\s*['\"](?:0\.0\.0\.0/0|\*|Internet)['\"]", network.split("name: 'allow-admin-ssh'", 1)[1])


def test_postgres_is_private_and_cost_bounded() -> None:
    postgres = read(INFRA / "modules" / "postgres.bicep")
    assert "Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01" in postgres
    assert "name: 'Standard_B1ms'" not in postgres  # parameterized SKU
    assert "Standard_B1ms" in read(INFRA / "main.bicep")
    assert "tier: 'Burstable'" in postgres
    assert "version: postgresVersion" in postgres
    assert "publicNetworkAccess: 'Disabled'" in postgres
    assert "delegatedSubnetResourceId: delegatedSubnetId" in postgres
    assert "privateDnsZoneArmResourceId: privateDnsZoneId" in postgres
    assert "mode: 'Disabled'" in postgres
    assert "geoRedundantBackup: 'Disabled'" in postgres
    assert "storageSizeGB: 32" in postgres
    assert not re.search(r"(?i)readReplica|replica|firewallRule|elasticCluster|defender", postgres)


def test_storage_is_optional_and_narrowly_scoped() -> None:
    params = read(BASELINE)
    storage = read(INFRA / "modules" / "storage.bicep")
    assert "deployBlob = false" in params
    assert "if (deployBlob)" in storage
    assert "Standard_LRS" in storage
    assert "Storage Blob Data Reader" not in storage
    assert "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1" in storage
    assert "scope: artifactContainer" in storage


def test_no_unapproved_resource_families_or_hardcoded_cloud_ids() -> None:
    bicep = all_bicep()
    assert bicep.count("Microsoft.Compute/virtualMachines@") == 1
    forbidden = (
        "Microsoft.Network/natGateways",
        "Microsoft.Network/azureFirewalls",
        "Microsoft.Network/bastionHosts",
        "Microsoft.Network/loadBalancers",
        "Microsoft.Network/privateEndpoints",
        "Microsoft.Network/virtualNetworkGateways",
        "Microsoft.ContainerService/managedClusters",
        "Microsoft.App/containerApps",
        "Microsoft.OperationalInsights/workspaces",
        "Microsoft.Insights/components",
    )
    for resource_type in forbidden:
        assert resource_type not in bicep
    assert not re.search(r"(?i)(/subscriptions/|/tenants/)[0-9a-f-]{36}", bicep)
    assert not re.search(r"(?i)(adminPassword|connectionString|accessToken|sasToken)\s*=\s*'[^']+'", bicep)


def test_scripts_contain_no_azure_mutation_command() -> None:
    exact_forbidden = (
        ("az", "group", "create"),
        ("az", "group", "delete"),
        ("az", "group", "update"),
        ("az", "deployment", "sub", "create"),
        ("az", "deployment", "group", "create"),
        ("az", "provider", "register"),
        ("az", "role", "assignment", "create"),
        ("az", "role", "assignment", "delete"),
    )
    exact_patterns = [
        re.compile(r"(?<![\w])" + r"\s+".join(map(re.escape, parts)) + r"\b", re.IGNORECASE)
        for parts in exact_forbidden
    ]
    service_mutation = re.compile(
        r"(?<![\w])az\s+(?:vm|network|postgres|storage|resource|identity)"
        r"\b(?:\s+\S+)*\s+(?:create|update|delete)\b",
        re.IGNORECASE,
    )
    for path in (SCRIPTS / "azure_phase4b_preflight.sh", SCRIPTS / "azure_phase4b_whatif.sh"):
        content = read(path)
        assert not any(pattern.search(content) for pattern in exact_patterns), path
        assert not service_mutation.search(content), path
        assert "git merge-base --is-ancestor \"$PHASE4A_BASE\" HEAD" in content
        assert "EXPECTED_HEAD" not in content
        assert "git diff --quiet" in content
        assert "git diff --cached --quiet" in content
        for match in re.finditer(r"az_readonly\s+\d+\s+az rest\b([^\n]*)", content):
            assert "--method get" in match.group(1)
    whatif = read(SCRIPTS / "azure_phase4b_whatif.sh")
    assert "az deployment sub validate" in whatif
    assert "az deployment sub what-if" in whatif
    assert "--confirm-with-what-if" not in whatif
    assert "REGION='eastasia'" in whatif
    assert "BASE_PARAMETERS='infra/parameters/phase4b.eastasia.bicepparam'" in whatif
    assert "git merge-base --is-ancestor \"$PHASE4A_BASE\" HEAD" in whatif
    assert "EXPECTED_HEAD" not in whatif
    assert "phase4b.southeastasia.bicepparam" not in whatif
    assert "source = (root / parameters_path).read_text()" in whatif
    assert "required_providers=(Microsoft.Resources Microsoft.Network Microsoft.Compute Microsoft.DBforPostgreSQL Microsoft.Authorization)" in whatif
    assert "Microsoft.Storage (optional while deployBlob=false)" in whatif
    assert "required_unregistered" in whatif


def test_no_activation_or_inference_commands_in_iac_scripts() -> None:
    content = all_bicep() + read(SCRIPTS / "azure_phase4b_preflight.sh") + read(SCRIPTS / "azure_phase4b_whatif.sh")
    assert not re.search(r"(?i)(activate[_ -]model|model[_ -]activation|run[_ -]inference)", content)
