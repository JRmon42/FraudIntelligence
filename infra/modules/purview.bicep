// ============================================================================
// purview.bicep — Purview account (catalog scans wired post-deploy via REST)
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string

@description('Resource IDs of data sources to grant Purview MSI Reader on')
param sourceResourceIds array = []

var purviewName = 'pv-fraudintel-${env}-${regionCode}'
// Reader role
var readerRoleId = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'

resource purview 'Microsoft.Purview/accounts@2024-04-01-preview' = {
  name: purviewName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Standard', capacity: 1 }
  properties: {
    publicNetworkAccess: 'Disabled'
    managedResourcesPublicNetworkAccess: 'Disabled'
    // managedEventHubState removed — the 2023-05-01-preview API doesn't
    // support enabling the managed Event Hub namespace; Atlas-style streaming
    // is configured post-deployment via the Purview data plane API.
  }
}

resource purviewDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: purview
  name: 'diag-${purviewName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
  }
}

resource sourceReaderAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (id, i) in sourceResourceIds: {
  name: guid(purview.id, id, readerRoleId)
  scope: resourceGroup()
  properties: {
    principalId: purview.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', readerRoleId)
    principalType: 'ServicePrincipal'
  }
}]

output purviewId string = purview.id
output purviewName string = purview.name
output purviewPrincipalId string = purview.identity.principalId
// NOTE: scan registration & rulesets must be created via Purview REST API or
// portal post-deploy. See infra/README.md.
