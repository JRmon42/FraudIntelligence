// ============================================================================
// eventhubs.bicep — Event Hubs Standard + 3 hubs + geo-DR alias
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string
param peSubnetId string
param privateDnsZoneId string

@description('Resource ID of the partner namespace for geo-DR (set on primary only)')
param partnerNamespaceId string = ''

@description('If true, create geo-DR alias (only on primary region)')
param enableGeoDr bool = false

var nsName = 'evhns-heimdall-${env}-${regionCode}'

var hubs = [
  { name: 'txn.events',     partitions: 8, retention: 3 }
  { name: 'decision.events', partitions: 4, retention: 3 }
  { name: 'feature.events',  partitions: 4, retention: 3 }
]

var consumerGroups = [ 'asa', 'orchestrator', 'fabric', 'aml' ]

resource ns 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: nsName
  location: location
  tags: tags
  sku: { name: 'Standard', tier: 'Standard', capacity: 2 }
  identity: { type: 'SystemAssigned' }
  properties: {
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    zoneRedundant: true
    isAutoInflateEnabled: true
    maximumThroughputUnits: 10
  }
}

resource eventHubs 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = [for h in hubs: {
  parent: ns
  name: h.name
  properties: {
    partitionCount: h.partitions
    messageRetentionInDays: h.retention
  }
}]

resource cgs 'Microsoft.EventHub/namespaces/eventhubs/consumergroups@2024-01-01' = [for combo in [
  { hub: 'txn.events',      cg: 'asa' }
  { hub: 'txn.events',      cg: 'orchestrator' }
  { hub: 'txn.events',      cg: 'fabric' }
  { hub: 'decision.events', cg: 'orchestrator' }
  { hub: 'decision.events', cg: 'fabric' }
  { hub: 'feature.events',  cg: 'aml' }
  { hub: 'feature.events',  cg: 'fabric' }
]: {
  name: '${ns.name}/${combo.hub}/${combo.cg}'
  dependsOn: [ eventHubs ]
}]

resource alias 'Microsoft.EventHub/namespaces/disasterRecoveryConfigs@2024-01-01' = if (enableGeoDr && !empty(partnerNamespaceId)) {
  parent: ns
  name: 'heimdall-${env}-dr-alias'
  properties: {
    partnerNamespace: partnerNamespaceId
  }
}

resource nsDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: ns
  name: 'diag-${nsName}'
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
  name: 'pe-${nsName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${nsName}'
        properties: {
          privateLinkServiceId: ns.id
          groupIds: [ 'namespace' ]
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
      { name: 'namespace', properties: { privateDnsZoneId: privateDnsZoneId } }
    ]
  }
}

output namespaceId string = ns.id
output namespaceName string = ns.name
output namespaceFqdn string = '${ns.name}.servicebus.windows.net'
