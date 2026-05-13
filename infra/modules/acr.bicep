// ============================================================================
// acr.bicep — Premium ACR with geo-replication, private endpoint
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string
param peSubnetId string
param privateDnsZoneId string

@description('Geo-replication target region (e.g., northeurope)')
param replicaLocation string

var acrName = replace('acrfraudintel${env}${regionCode}', '-', '')

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Premium' }
  identity: { type: 'SystemAssigned' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    networkRuleBypassOptions: 'AzureServices'
    networkRuleSet: {
      defaultAction: 'Allow'
    }
    zoneRedundancy: 'Enabled'
    policies: {
      quarantinePolicy: { status: 'enabled' }
      trustPolicy: { type: 'Notary', status: 'enabled' }
      retentionPolicy: { days: 30, status: 'enabled' }
      exportPolicy: { status: 'enabled' }
    }
  }
}

resource replica 'Microsoft.ContainerRegistry/registries/replications@2023-11-01-preview' = {
  parent: acr
  name: replicaLocation
  location: replicaLocation
  tags: tags
  properties: {
    zoneRedundancy: 'Enabled'
  }
}

resource acrDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: acr
  name: 'diag-${acrName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${acrName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${acrName}'
        properties: {
          privateLinkServiceId: acr.id
          groupIds: [ 'registry' ]
        }
      }
    ]
  }
}

resource peDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: pe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'registry', properties: { privateDnsZoneId: privateDnsZoneId } }
    ]
  }
}

output acrId string = acr.id
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
