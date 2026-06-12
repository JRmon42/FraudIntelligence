// ============================================================================
// aml.bicep — Azure ML workspace with managed VNet + online endpoint
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string
param keyVaultId string
param appInsightsId string
param acrId string
param peSubnetId string
@description('Private DNS zone ID for privatelink.api.azureml.ms')
param amlApiDnsZoneId string
@description('Private DNS zone ID for privatelink.notebooks.azure.net')
param amlNotebooksDnsZoneId string

var workspaceName = 'mlw-heimdall-${env}-${regionCode}'
var storageName = replace('stamlheimdall${env}${regionCode}', '-', '')

resource amlStorage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_GRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Disabled'
    supportsHttpsTrafficOnly: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
    encryption: {
      services: {
        blob: { enabled: true }
        file: { enabled: true }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

resource aml 'Microsoft.MachineLearningServices/workspaces@2024-04-01' = {
  name: workspaceName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Basic', tier: 'Basic' }
  properties: {
    friendlyName: 'Heimdall ML ${env}'
    storageAccount: amlStorage.id
    keyVault: keyVaultId
    applicationInsights: appInsightsId
    containerRegistry: acrId
    publicNetworkAccess: 'Disabled'
    hbiWorkspace: true
    managedNetwork: {
      isolationMode: 'AllowOnlyApprovedOutbound'
      outboundRules: {
        AllowAzureFrontDoor: {
          type: 'ServiceTag'
          destination: {
            serviceTag: 'AzureFrontDoor.Frontend'
            protocol: 'TCP'
            portRanges: '443'
          }
          category: 'UserDefined'
        }
        AllowOpenAI: {
          type: 'FQDN'
          destination: '*.openai.azure.com'
          category: 'UserDefined'
        }
        AllowPyPI: {
          type: 'FQDN'
          destination: 'pypi.org'
          category: 'UserDefined'
        }
        AllowPyPIFiles: {
          type: 'FQDN'
          destination: 'files.pythonhosted.org'
          category: 'UserDefined'
        }
      }
    }
  }
}

resource amlDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: aml
  name: 'diag-${workspaceName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
  }
}

resource pe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: 'pe-${workspaceName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: peSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${workspaceName}'
        properties: {
          privateLinkServiceId: aml.id
          groupIds: [ 'amlworkspace' ]
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
      { name: 'api', properties: { privateDnsZoneId: amlApiDnsZoneId } }
      { name: 'notebooks', properties: { privateDnsZoneId: amlNotebooksDnsZoneId } }
    ]
  }
}

// Online endpoint placeholder
resource onlineEp 'Microsoft.MachineLearningServices/workspaces/onlineEndpoints@2024-04-01' = {
  parent: aml
  name: 'scoring-ep'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    authMode: 'Key'
    publicNetworkAccess: 'Disabled'
    description: 'Fraud scoring online endpoint'
  }
}

output amlId string = aml.id
output amlName string = aml.name
output amlPrincipalId string = aml.identity.principalId
output amlStorageId string = amlStorage.id
output onlineEndpointName string = onlineEp.name
