// ============================================================================
// synapse.bicep — Synapse workspace (serverless SQL only) + ADLS Gen2
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string

@description('SQL admin login (use AAD where possible — this is required by API)')
param sqlAdminLogin string = 'syadmin'

@secure()
@description('SQL admin password')
param sqlAdminPassword string

@description('AAD admin object id')
param aadAdminObjectId string

@description('AAD admin login name')
param aadAdminLogin string

var workspaceName = 'syn-fraudintel-${env}-${regionCode}'
var storageName = replace('stsynfraud${env}${regionCode}', '-', '')
var fsName = 'syn-fs'

resource synStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Disabled'
    supportsHttpsTrafficOnly: true
    networkAcls: { bypass: 'AzureServices', defaultAction: 'Deny' }
  }
}

resource blobSvc 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: synStorage
  name: 'default'
}

resource fs 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobSvc
  name: fsName
  properties: { publicAccess: 'None' }
}

resource syn 'Microsoft.Synapse/workspaces@2021-06-01' = {
  name: workspaceName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    defaultDataLakeStorage: {
      accountUrl: 'https://${synStorage.name}.dfs.core.windows.net'
      filesystem: fsName
    }
    sqlAdministratorLogin: sqlAdminLogin
    sqlAdministratorLoginPassword: sqlAdminPassword
    publicNetworkAccess: 'Disabled'
    managedVirtualNetwork: 'default'
    managedVirtualNetworkSettings: {
      preventDataExfiltration: true
    }
    trustedServiceBypassEnabled: true
  }
  dependsOn: [ fs ]
}

resource synAad 'Microsoft.Synapse/workspaces/administrators@2021-06-01' = {
  parent: syn
  name: 'activeDirectory'
  properties: {
    administratorType: 'ActiveDirectory'
    login: aadAdminLogin
    sid: aadAdminObjectId
    tenantId: subscription().tenantId
  }
}

resource synDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: syn
  name: 'diag-${workspaceName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
  }
}

output synapseId string = syn.id
output synapseName string = syn.name
output synapseStorageId string = synStorage.id
output synapseServerlessEndpoint string = syn.properties.connectivityEndpoints.sqlOnDemand
