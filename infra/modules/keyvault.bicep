// ============================================================================
// keyvault.bicep — Key Vault (RBAC), purge protection, soft delete, PE
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param tenantId string = subscription().tenantId
param logAnalyticsWorkspaceId string
param peSubnetId string
param privateDnsZoneId string

@description('Object IDs that should receive Key Vault Administrator role')
param adminPrincipalIds array = []

var kvName = 'kv-heimdall-${env}-${regionCode}'
// Key Vault Administrator role
var kvAdminRoleId = '00482a5a-887f-4fb3-b363-3b7fe8e74483'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    tenantId: tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    enabledForDeployment: false
    enabledForDiskEncryption: true
    enabledForTemplateDeployment: false
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

resource kvDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: kv
  name: 'diag-${kvName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
      { categoryGroup: 'audit', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

resource kvAdminAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (pid, i) in adminPrincipalIds: {
  scope: kv
  name: guid(kv.id, pid, kvAdminRoleId)
  properties: {
    principalId: pid
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvAdminRoleId)
    principalType: 'User'
  }
}]

// Private endpoint
resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${kvName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${kvName}'
        properties: {
          privateLinkServiceId: kv.id
          groupIds: [ 'vault' ]
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
      {
        name: 'vault'
        properties: { privateDnsZoneId: privateDnsZoneId }
      }
    ]
  }
}

output keyVaultId string = kv.id
output keyVaultName string = kv.name
output keyVaultUri string = kv.properties.vaultUri
