param location string
param serverName string
@allowed([
  'Standard_B1ms'
])
param skuName string
@allowed([
  '16'
])
param postgresVersion string
param administratorLogin string
@secure()
param administratorPassword string
param delegatedSubnetId string
param privateDnsZoneId string
param tags object

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01' = {
  name: serverName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    version: postgresVersion
    createMode: 'Create'
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Disabled'
      delegatedSubnetResourceId: delegatedSubnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
    }
    storage: {
      storageSizeGB: 32
      autoGrow: 'Disabled'
    }
  }
}

output serverName string = server.name
