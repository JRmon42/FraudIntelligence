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

@description('Create a geo-replica in replicaLocation. Set false for single-region deployment.')
param enableReplica bool = false

var acrName = replace('acrheimdall${env}${regionCode}', '-', '')

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
      // Quarantine and trust (Notary v1) policies were enabled originally but
      // caused MANIFEST_UNKNOWN pull failures from Container Apps because images
      // landed in Quarantined state. Disabled here so future redeploys do not
      // re-enable them. Re-enable behind a feature flag once a quarantine
      // scanner workflow is in place.
      quarantinePolicy: { status: 'disabled' }
      trustPolicy: { type: 'Notary', status: 'disabled' }
      retentionPolicy: { days: 30, status: 'enabled' }
      exportPolicy: { status: 'enabled' }
    }
  }
}

resource replica 'Microsoft.ContainerRegistry/registries/replications@2023-11-01-preview' = if (enableReplica) {
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
