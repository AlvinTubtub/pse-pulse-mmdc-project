// ==============================================================================
// PSE Pulse — Personal Azure Edition
// Bicep Infrastructure Deployment Template
// ==============================================================================
// WARNING: DO NOT EXECUTE THIS TEMPLATE UNTIL REVIEWED AND APPROVED.
// DO NOT RUN 'az deployment group create'.
// Sized strictly for Azure for Students free-tier allowances ($0 target).
// ==============================================================================
// NETWORKING DESIGN NOTE:
// This personal deployment chooses PostgreSQL public access with a single-IP
// firewall and mandatory TLS to avoid provisioning an Azure Private DNS zone
// outside the explicitly approved free-service allowances.
// ==============================================================================

@description('Azure deployment region (e.g. southeastasia, eastasia).')
param location string = resourceGroup().location

@description('Deployment environment name.')
@allowed([
  'development'
  'staging'
  'production'
])
param environment string = 'production'

@description('Virtual machine SKU. Standard_B2ats_v2 is primary; Standard_B1s is fallback.')
@allowed([
  'Standard_B2ats_v2'
  'Standard_B1s'
])
param vmSize string = 'Standard_B2ats_v2'

@description('Linux administrator username for the VM.')
param adminUsername string = 'psepulse'

@description('SSH RSA/ED25519 public key string for authentication. Never commit private keys.')
@secure()
param adminSshPublicKey string

@description('CIDR prefix allowed to access SSH (port 22). Must be explicitly set to administrator IP CIDR (e.g. 203.0.113.10/32).')
param allowedSshSourceIp string

@description('PostgreSQL server administrator username.')
param dbAdminUsername string = 'pseadmin'

@description('PostgreSQL server administrator password.')
@secure()
param dbAdminPassword string

@description('Allocated database storage size in GiB. Kept at 32 GB for free-tier ceiling.')
@maxValue(32)
param dbStorageSizeGB int = 32

@description('Unique suffix for global resource naming.')
param uniqueSuffix string = uniqueString(resourceGroup().id)

// Resource Names
var vnetName = 'vnet-pse-pulse-${environment}'
var nsgName = 'nsg-pse-pulse-${environment}'
var publicIpName = 'pip-pse-pulse-${environment}'
var nicName = 'nic-pse-pulse-${environment}'
var vmName = 'vm-pse-pulse-${environment}'
var dbServerName = 'psql-pse-pulse-${environment}-${uniqueSuffix}'
var storageAccountName = 'stprepuls${take(uniqueSuffix, 10)}'

// 1. Network Security Group
resource nsg 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: nsgName
  location: location
  properties: {
    securityRules: [
      {
        name: 'Allow-SSH'
        properties: {
          priority: 1000
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '22'
          sourceAddressPrefix: allowedSshSourceIp
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'Allow-HTTP'
        properties: {
          priority: 1010
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'Allow-HTTPS'
        properties: {
          priority: 1020
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: '*'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// 2. Virtual Network & Single Subnet for VM (No Private DNS / Delegated Subnet)
resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.0.0.0/16'
      ]
    }
    subnets: [
      {
        name: 'snet-vm'
        properties: {
          addressPrefix: '10.0.1.0/24'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}

// 3. Public IPv4 (Single static allocated address for VM)
resource publicIp 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: publicIpName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Regional'
  }
  properties: {
    publicIPAddressVersion: 'IPv4'
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      domainNameLabel: 'pse-pulse-${uniqueSuffix}'
    }
  }
}

// 4. Network Interface
resource nic 'Microsoft.Network/networkInterfaces@2023-09-01' = {
  name: nicName
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: vnet.properties.subnets[0].id
          }
          privateIPAllocationMethod: 'Dynamic'
          publicIPAddress: {
            id: publicIp.id
          }
        }
      }
    ]
  }
}

// 5. Host Virtual Machine (Ubuntu 24.04 LTS, Standard_B2ats_v2 or Standard_B1s)
resource vm 'Microsoft.Compute/virtualMachines@2023-09-01' = {
  name: vmName
  location: location
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: 'psepulse-vm'
      adminUsername: adminUsername
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${adminUsername}/.ssh/authorized_keys'
              keyData: adminSshPublicKey
            }
          ]
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Premium_LRS' // P6 disk tier (64 GiB)
        }
        diskSizeGB: 64
        caching: 'ReadWrite'
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: nic.id
        }
      ]
    }
  }
}

// 6. Azure Database for PostgreSQL Flexible Server (Burstable B1ms, 32 GB storage ceiling)
// Uses Public Access with single-IP firewall to avoid billable Private DNS Zone
resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-03-01-preview' = {
  name: dbServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: dbAdminUsername
    administratorLoginPassword: dbAdminPassword
    storage: {
      storageSizeGB: dbStorageSizeGB
      autoGrow: 'Disabled' // Strictly enforce 32 GB cost guardrail
    }
    highAvailability: {
      mode: 'Disabled' // No HA to avoid extra VM billing
    }
  }
}

// 7. PostgreSQL Firewall Rule: Strictly restricted ONLY to the VM Public IPv4
resource postgresFirewallRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-03-01-preview' = {
  parent: postgresServer
  name: 'allow-pse-pulse-vm-ip'
  properties: {
    startIpAddress: publicIp.properties.ipAddress
    endIpAddress: publicIp.properties.ipAddress
  }
}

// Database creation
resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-03-01-preview' = {
  parent: postgresServer
  name: 'pse_pulse_prod'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Server configuration: explicitly enforce TLS/SSL
resource postgresRequireSsl 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-03-01-preview' = {
  parent: postgresServer
  name: 'require_secure_transport'
  properties: {
    value: 'on'
    source: 'user-override'
  }
}

// 8. Azure Blob Storage Account (Standard LRS Hot, < 5 GB)
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'pse-pulse-data'
  properties: {
    publicAccess: 'None'
  }
}

// Outputs
output vmPublicFqdn string = publicIp.properties.dnsSettings.fqdn
output vmPrivateIp string = nic.properties.ipConfigurations[0].properties.privateIPAddress
output postgresFqdn string = postgresServer.properties.fullyQualifiedDomainName
output storageAccountName string = storageAccount.name
