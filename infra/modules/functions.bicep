// ============================================================================
// functions.bicep — Enforcement Azure Function (async action path)
//
// Flex Consumption (Linux, Python) Function app consuming the Service Bus
// `highrisk-alerts` queue and taking durable action (block / step-up / notify /
// open case). Cost-optimised: FC1 (pay-per-execution, ~€0 idle).
//
// Fully key-less to satisfy the org "no shared-key storage" policy:
//   * deployment package -> blob container via the app's managed identity
//   * AzureWebJobsStorage -> identity-based (Storage Blob Data Owner granted)
//   * Service Bus trigger -> identity-based (Data Receiver granted by servicebus.bicep)
// App code is published separately (services/enforcement-function/).
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

@description('App Insights connection string for Function telemetry.')
param appInsightsConnectionString string

@description('Fully-qualified Service Bus namespace host for the identity-based trigger.')
param serviceBusFqdn string

@description('Name of the high-risk queue the enforcement consumer binds to.')
param queueName string = 'highrisk-alerts'

@description('Subnet resource id (delegated to Microsoft.App/environments) for outbound VNet integration so the Function reaches the Cosmos private endpoint. Empty disables VNet integration.')
param functionSubnetId string = ''

@description('Cosmos DB account name the enforcement consumer opens cases in. Empty disables case persistence + RBAC.')
param cosmosAccountName string = ''

@description('Cosmos endpoint (documentEndpoint) for case persistence.')
param cosmosEndpoint string = ''

@description('Cosmos database + container for enforcement cases.')
param cosmosDatabase string = 'fraud'
param cosmosCasesContainer string = 'cases'

@description('Private-endpoint subnet id (snet-pe) for the identity-based host storage. Empty disables storage private endpoints (leaves public access enabled).')
param privateEndpointSubnetId string = ''

@description('Private DNS zone ids for storage blob/queue/table (from the network module). Required when privateEndpointSubnetId is set.')
param blobDnsZoneId string = ''
param queueDnsZoneId string = ''
param tableDnsZoneId string = ''

var funcName = 'func-heimdall-enforce-${env}-${regionCode}'
var planName = 'plan-func-heimdall-${env}-${regionCode}'
var stName = 'stfn${env}heimdall${regionCode}'
var deployContainerName = 'deployment'

// Built-in role: Storage Blob Data Owner
var blobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'

resource st 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
    // Locked to private-endpoint-only access once a PE subnet is supplied. The
    // Flex Consumption host reaches blob/queue/table via the private endpoints
    // below (over the Function's VNet integration); public access is disabled.
    publicNetworkAccess: empty(privateEndpointSubnetId) ? 'Enabled' : 'Disabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: st
  name: 'default'
}

resource deployContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deployContainerName
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  tags: tags
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  kind: 'functionapp'
  properties: {
    reserved: true // Linux
  }
}

resource func 'Microsoft.Web/sites@2023-12-01' = {
  name: funcName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    // Outbound VNet integration: the enforcement consumer reaches the Cosmos
    // private endpoint to open cases (Cosmos is public-network-access Disabled).
    virtualNetworkSubnetId: empty(functionSubnetId) ? null : functionSubnetId
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${st.properties.primaryEndpoints.blob}${deployContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
      scaleAndConcurrency: {
        instanceMemoryMB: 2048
        maximumInstanceCount: 40
      }
    }
    siteConfig: {
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        // Identity-based host storage (no shared keys).
        { name: 'AzureWebJobsStorage__accountName', value: st.name }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
        { name: 'ENFORCEMENT_QUEUE', value: queueName }
        // Identity-based Service Bus trigger connection.
        { name: 'ServiceBusConnection__fullyQualifiedNamespace', value: serviceBusFqdn }
        { name: 'ServiceBusConnection__credential', value: 'managedidentity' }
        // Cosmos case persistence (identity-based; reached via VNet + private endpoint).
        { name: 'COSMOS_ENDPOINT', value: cosmosEndpoint }
        { name: 'COSMOS_DATABASE', value: cosmosDatabase }
        { name: 'COSMOS_CASES_CONTAINER', value: cosmosCasesContainer }
      ]
    }
  }
}

// The app's identity needs blob data access for deployment + AzureWebJobsStorage.
resource stRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: st
  name: guid(st.id, func.id, blobDataOwnerRoleId)
  properties: {
    principalId: func.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataOwnerRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Cosmos DB data-plane RBAC (Built-in Data Contributor) so the enforcement
// consumer can upsert case documents. Skipped when no Cosmos account is supplied.
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = if (!empty(cosmosAccountName)) {
  name: cosmosAccountName
}

resource cosmosDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = if (!empty(cosmosAccountName)) {
  parent: cosmos
  name: guid(cosmosAccountName, func.id, 'data-contributor')
  properties: {
    principalId: func.identity.principalId
    // Built-in Cosmos DB Data Contributor.
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmos.id
  }
}

// ---------------------------------------------------------------------------
// Private endpoints for the identity-based host storage (blob/queue/table).
// Flex Consumption + identity-based AzureWebJobsStorage needs all three; a
// file share is NOT used. Created in snet-pe with a DNS zone group so the A
// records auto-register in the private zones the Function resolves over its
// VNet integration. Deployment package + host coordination stay fully private.
// ---------------------------------------------------------------------------
var storagePeEnabled = !empty(privateEndpointSubnetId)
var storagePeGroups = [
  { svc: 'blob', zoneId: blobDnsZoneId }
  { svc: 'queue', zoneId: queueDnsZoneId }
  { svc: 'table', zoneId: tableDnsZoneId }
]

resource stPrivateEndpoints 'Microsoft.Network/privateEndpoints@2023-11-01' = [for g in storagePeGroups: if (storagePeEnabled) {
  name: 'pe-stfn-${g.svc}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'conn-stfn-${g.svc}'
        properties: {
          privateLinkServiceId: st.id
          groupIds: [ g.svc ]
        }
      }
    ]
  }
}]

resource stPeDnsGroups 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = [for (g, i) in storagePeGroups: if (storagePeEnabled) {
  name: '${stPrivateEndpoints[i].name}/default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: g.svc
        properties: { privateDnsZoneId: g.zoneId }
      }
    ]
  }
}]

output functionName string = func.name
output functionId string = func.id
output functionPrincipalId string = func.identity.principalId
output functionDefaultHostName string = func.properties.defaultHostName
