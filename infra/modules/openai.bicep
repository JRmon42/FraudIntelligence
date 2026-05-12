// ============================================================================
// openai.bicep — Azure OpenAI account with model deployments + PE + CMK
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string
param peSubnetId string
param privateDnsZoneId string

@description('Customer managed key URI (optional)')
param cmkKeyUri string = ''

@description('Custom subdomain (must be globally unique)')
param customSubdomain string = 'oai-fraudintel-${env}-${regionCode}'

@description('TPM for chat model in thousands per minute (e.g., 60 -> 60K TPM)')
param chatModelCapacity int = 60

@description('TPM for embedding model in thousands per minute')
param embeddingModelCapacity int = 60

var accountName = 'oai-fraudintel-${env}-${regionCode}'

resource oai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: customSubdomain
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    networkAcls: {
      defaultAction: 'Deny'
      virtualNetworkRules: []
      ipRules: []
    }
    encryption: empty(cmkKeyUri) ? null : {
      keySource: 'Microsoft.KeyVault'
      keyVaultProperties: {
        keyVaultUri: substring(cmkKeyUri, 0, indexOf(cmkKeyUri, '/keys/'))
        keyName: split(cmkKeyUri, '/')[5]
      }
    }
  }
}

resource gpt4o 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: oai
  name: 'gpt-4o-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: chatModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

resource emb 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: oai
  name: 'text-embedding-3-large'
  sku: {
    name: 'Standard'
    capacity: embeddingModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
  dependsOn: [ gpt4o ]
}

resource oaiDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: oai
  name: 'diag-${accountName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
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
          privateLinkServiceId: oai.id
          groupIds: [ 'account' ]
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
      { name: 'account', properties: { privateDnsZoneId: privateDnsZoneId } }
    ]
  }
}

output openAiId string = oai.id
output openAiName string = oai.name
output openAiEndpoint string = oai.properties.endpoint
output openAiPrincipalId string = oai.identity.principalId
output chatDeploymentName string = gpt4o.name
output embeddingDeploymentName string = emb.name
