// ============================================================================
// redis.bicep — Azure Managed Redis (feature cache)
//
// Classic "Azure Cache for Redis" is retired for new creates, so this uses
// **Azure Managed Redis** (Microsoft.Cache/redisEnterprise). Cost-optimised:
// defaults to the entry **Balanced_B0** SKU. Bump to Balanced_B1+/MemoryOptimized
// for production. TLS 1.2 enforced; data access via Entra (key-less) for the
// supplied principals. Not on the synchronous scoring path (the seeded feature
// store is used) — this provisions the documented feature-cache tier.
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string

@description('Azure Managed Redis SKU. Balanced_B0 is the entry tier.')
param skuName string = 'Balanced_B0'

@description('Object IDs granted the default Entra data access policy (e.g. scoring-api MI).')
param dataPrincipalIds array = []

var redisName = 'redis-heimdall-${env}-${regionCode}'

resource redis 'Microsoft.Cache/redisEnterprise@2024-10-01' = {
  name: redisName
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  identity: { type: 'SystemAssigned' }
  properties: {
    minimumTlsVersion: '1.2'
  }
}

resource redisDb 'Microsoft.Cache/redisEnterprise/databases@2024-10-01' = {
  parent: redis
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    port: 10000
    clusteringPolicy: 'OSSCluster'
    evictionPolicy: 'VolatileLRU'
  }
}

// Entra (key-less) data access for the supplied principals.
resource redisAccess 'Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments@2024-10-01' = [for pid in dataPrincipalIds: {
  parent: redisDb
  name: guid(redisDb.id, pid)
  properties: {
    accessPolicyName: 'default'
    user: {
      objectId: pid
    }
  }
}]

resource redisDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: redis
  name: 'diag-${redisName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

output redisId string = redis.id
output redisName string = redis.name
output redisHostName string = redis.properties.hostName
