targetScope = 'subscription'

@description('Azure region for the resource group and all regional resources.')
param location string

@description('Deterministic resource group name for the PSE Pulse student deployment.')
param resourceGroupName string = 'rg-pse-pulse-student-prod'

@description('Primary x86-64 VM candidate. Use a separately approved override only after quota and cost review.')
@allowed([
  'Standard_B2als_v2'
  'Standard_B2as_v2'
])
param vmSize string = 'Standard_B2als_v2'

@description('Whether to add a narrowly scoped SSH rule. Disabled in the baseline.')
param enableSsh bool = false

@description('Specific administrator CIDR required when SSH is enabled.')
param adminSshCidr string = ''

@description('Whether to include optional artifact Blob Storage. Disabled in the baseline.')
param deployBlob bool = false

@description('Linux administrator account name.')
param vmAdminUsername string = 'psepulseops'

@description('SSH public key supplied only through a temporary runtime parameter file.')
param adminSshPublicKey string

@description('PostgreSQL administrator login name.')
param administratorLogin string = 'psepulseadmin'

@description('Temporary validation value or later protected runtime secret. Never put a value in the parameter file.')
@secure()
param administratorPassword string

@description('PostgreSQL major version. Keep pinned to a supported major.')
@allowed([
  '16'
])
param postgresVersion string = '16'

@description('PostgreSQL Flexible Server SKU candidate.')
@allowed([
  'Standard_B1ms'
])
param postgresSku string = 'Standard_B1ms'

var projectSuffix = uniqueString(subscription().id, resourceGroupName)
var resourceTags = {
  project: 'pse-pulse'
  environment: 'production'
  managedBy: 'bicep'
  costClass: 'student-project'
}

resource futureResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: resourceTags
}

module network './modules/network.bicep' = {
  name: 'network-${projectSuffix}'
  scope: futureResourceGroup
  params: {
    location: location
    vnetName: 'vnet-psepulse-${projectSuffix}'
    nsgName: 'nsg-psepulse-app'
    publicIpName: 'pip-psepulse-app'
    nicName: 'nic-psepulse-app'
    enableSsh: enableSsh
    adminSshCidr: adminSshCidr
    tags: resourceTags
  }
}

module compute './modules/compute.bicep' = {
  name: 'compute-${projectSuffix}'
  scope: futureResourceGroup
  params: {
    location: location
    vmName: 'vm-psepulse-${projectSuffix}'
    vmSize: vmSize
    networkInterfaceId: network.outputs.networkInterfaceId
    adminUsername: vmAdminUsername
    adminSshPublicKey: adminSshPublicKey
    tags: resourceTags
  }
}

module postgres './modules/postgres.bicep' = {
  name: 'postgres-${projectSuffix}'
  scope: futureResourceGroup
  params: {
    location: location
    serverName: 'pg-psepulse-${projectSuffix}'
    skuName: postgresSku
    postgresVersion: postgresVersion
    administratorLogin: administratorLogin
    administratorPassword: administratorPassword
    delegatedSubnetId: network.outputs.postgresSubnetId
    privateDnsZoneId: network.outputs.privateDnsZoneId
    tags: resourceTags
  }
}

module storage './modules/storage.bicep' = if (deployBlob) {
  name: 'storage-${projectSuffix}'
  scope: futureResourceGroup
  params: {
    location: location
    deployBlob: deployBlob
    storageAccountName: take('psepulse${projectSuffix}', 24)
    vmPrincipalId: compute.outputs.vmPrincipalId
    tags: resourceTags
  }
}

@description('Future resource group name.')
output resourceGroupName string = futureResourceGroup.name

@description('Selected resource location.')
output location string = location

@description('Application VM name.')
output vmName string = 'vm-psepulse-${projectSuffix}'

@description('PostgreSQL Flexible Server name.')
output postgresServerName string = 'pg-psepulse-${projectSuffix}'

@description('PostgreSQL Private DNS zone name.')
output privateDnsZoneName string = network.outputs.privateDnsZoneName

@description('Application public IP resource name.')
output publicIpName string = 'pip-psepulse-app'
