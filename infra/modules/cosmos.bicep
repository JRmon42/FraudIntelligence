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

@description('Whether to add the secondary region to the Cosmos account locations array. Set false for single-region deployment; can be flipped to true later (Cosmos supports adding regions online).')
param enableSecondaryRegion bool = false

@description('Customer-managed key URI (Key Vault key) — leave empty to skip CMK')
param cmkKeyUri string = ''

@description('Key Vault resource ID for CMK access (RBAC will be assigned)')
param keyVaultId string = ''

@description('Throughput per container')
param containerThroughput int = 400

@description('AAD principal object IDs to grant Cosmos data-plane access (Built-in Data Contributor). Required for humans/auditors to query Data Explorer because local (key) auth is disabled.')
param dataPlanePrincipalIds array = []

var accountName = 'cosmos-heimdall-${env}-${regionCode}'

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
    enableMultipleWriteLocations: enableSecondaryRegion
    enableAutomaticFailover: enableSecondaryRegion
    enableFreeTier: false
    minimalTlsVersion: 'Tls12'
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    // Note: Cosmos accounts are single-API. We use SQL (Core) here for
    // transactional containers. Graph workloads use GNN embeddings served
    // from the scoring API; if a Gremlin store is later required, deploy
    // a separate Cosmos account with the EnableGremlin capability.
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    locations: enableSecondaryRegion ? [
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
    ] : [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: true
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

// Gremlin DB removed — see note on the account above. The GraphSAGE GNN
// trains in batch from Bronze/Silver tables and serves embeddings inline
// through the scoring API; an in-cluster graph store is not required.

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

// Grant human/auditor principals Cosmos data-plane access (Built-in Data Contributor).
// Required because local (key) auth is disabled — Data Explorer queries authenticate via AAD.
resource dataPlaneAssignments 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = [for pid in dataPlanePrincipalIds: {
  parent: cosmos
  name: guid(cosmos.id, pid, 'cosmos-data-contributor')
  properties: {
    principalId: pid
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
  }
}]
