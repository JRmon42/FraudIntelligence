// ============================================================================
// cosmos.bicep — Cosmos DB multi-region + Gremlin graph + CMK + PE
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string
param peSubnetId string
param privateDnsZoneId string

@description('Secondary region for multi-region writes')
param secondaryLocation string = 'northeurope'

@description('Customer-managed key URI (Key Vault key) — leave empty to skip CMK')
param cmkKeyUri string = ''

@description('Key Vault resource ID for CMK access (RBAC will be assigned)')
param keyVaultId string = ''

@description('Throughput per container')
param containerThroughput int = 400

var accountName = 'cosmos-fraudintel-${env}-${regionCode}'

var sqlContainers = [
  { name: 'transactions', pk: '/cardId' }
  { name: 'cards',        pk: '/cardId' }
  { name: 'merchants',    pk: '/merchantId' }
  { name: 'decisions',    pk: '/transactionId' }
  { name: 'features',     pk: '/cardId' }
]

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  identity: { type: 'SystemAssigned' }
  properties: {
    databaseAccountOfferType: 'Standard'
    enableMultipleWriteLocations: true
    enableAutomaticFailover: true
    enableFreeTier: false
    minimalTlsVersion: 'Tls12'
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    capabilities: [
      { name: 'EnableGremlin' }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: true
      }
      {
        locationName: secondaryLocation
        failoverPriority: 1
        // Zone-redundant capacity is unavailable in some EU partner regions
        // (notably North Europe at the time of writing). Disable AZ on the
        // secondary so the geo-pair can still be added; primary remains AZ.
        isZoneRedundant: false
      }
    ]
    backupPolicy: {
      type: 'Continuous'
      continuousModeProperties: { tier: 'Continuous30Days' }
    }
    keyVaultKeyUri: empty(cmkKeyUri) ? null : cmkKeyUri
  }
}

// SQL DB: fraud
resource fraudDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'fraud'
  properties: {
    resource: { id: 'fraud' }
  }
}

resource sqlContainersRes 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for c in sqlContainers: {
  parent: fraudDb
  name: c.name
  properties: {
    resource: {
      id: c.name
      partitionKey: {
        paths: [ c.pk ]
        kind: 'Hash'
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [ { path: '/*' } ]
        excludedPaths: [ { path: '/"_etag"/?' } ]
      }
    }
    options: { throughput: containerThroughput }
  }
}]

// Gremlin DB: fraudgraph
resource gremlinDb 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-05-15' = {
  parent: cosmos
  name: 'fraudgraph'
  properties: {
    resource: { id: 'fraudgraph' }
  }
}

resource ringGraph 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-05-15' = {
  parent: gremlinDb
  name: 'rings'
  properties: {
    resource: {
      id: 'rings'
      partitionKey: {
        paths: [ '/entityId' ]
        kind: 'Hash'
      }
    }
    options: { throughput: containerThroughput }
  }
}

resource cosmosDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: cosmos
  name: 'diag-${accountName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [
      { category: 'Requests', enabled: true }
    ]
  }
}

resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${accountName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${accountName}'
        properties: {
          privateLinkServiceId: cosmos.id
          groupIds: [ 'Sql' ]
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
      { name: 'sql', properties: { privateDnsZoneId: privateDnsZoneId } }
    ]
  }
}

// Grant Cosmos identity Key Vault Crypto User on the KV (if CMK)
var cryptoUserRoleId = 'e147488a-f6f5-4113-8e2d-b22465e65bf6' // Key Vault Crypto User
resource kvAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(keyVaultId)) {
  scope: resourceGroup()
  name: guid(cosmos.id, keyVaultId, cryptoUserRoleId)
  properties: {
    principalId: cosmos.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cryptoUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

output cosmosId string = cosmos.id
output cosmosName string = cosmos.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output cosmosPrincipalId string = cosmos.identity.principalId
