param location string
param deployBlob bool = false
param storageAccountName string
param vmPrincipalId string
param tags object

var blobReaderRoleDefinitionId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = if (deployBlob) {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = if (deployBlob) {
  parent: storage
  name: 'default'
}

resource artifactContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = if (deployBlob) {
  parent: blobService
  name: 'model-artifacts'
  properties: {
    publicAccess: 'None'
  }
}

resource blobReaderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployBlob) {
  name: guid(artifactContainer.id, vmPrincipalId, blobReaderRoleDefinitionId)
  scope: artifactContainer
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobReaderRoleDefinitionId)
    principalId: vmPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output storageAccountName string = storage.name
