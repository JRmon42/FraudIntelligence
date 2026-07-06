// ============================================================================
// servicebus.bicep — Service Bus namespace + high-risk alert queue
//
// Async enforcement path (out of the 18 ms scoring budget): scoring-api and
// Stream Analytics publish high-risk decisions to the `highrisk-alerts` queue;
// the enforcement Function consumes them (block / step-up / notify / open case).
//
// Cost-optimised: defaults to **Standard** (~€10/mo + usage). Private endpoints
// require Premium, so Standard is deployed public with TLS 1.2 and local-auth
// disabled (Entra-only) — senders/receivers use their managed identity.
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string

@description('Service Bus SKU. Premium is required for private endpoints & zone redundancy.')
@allowed([ 'Standard', 'Premium' ])
param skuName string = 'Standard'

@description('Object IDs granted Azure Service Bus Data Sender on the namespace (scoring-api, orchestrator, ASA).')
param senderPrincipalIds array = []

@description('Object IDs granted Azure Service Bus Data Receiver on the namespace (enforcement Function).')
param receiverPrincipalIds array = []

var sbName = 'sbns-heimdall-${env}-${regionCode}'
var queueName = 'highrisk-alerts'

// Built-in role definition IDs
var dataSenderRoleId = '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'   // Azure Service Bus Data Sender
var dataReceiverRoleId = '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0' // Azure Service Bus Data Receiver

resource sb 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: sbName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuName
  }
  identity: { type: 'SystemAssigned' }
  properties: {
    minimumTlsVersion: '1.2'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    zoneRedundant: skuName == 'Premium'
  }
}

resource queue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sb
  name: queueName
  properties: {
    lockDuration: 'PT1M'
    maxDeliveryCount: 10
    deadLetteringOnMessageExpiration: true
    defaultMessageTimeToLive: 'P7D'
    enablePartitioning: skuName == 'Standard'
  }
}

resource senders 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for pid in senderPrincipalIds: {
  scope: sb
  name: guid(sb.id, pid, dataSenderRoleId)
  properties: {
    principalId: pid
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', dataSenderRoleId)
    principalType: 'ServicePrincipal'
  }
}]

resource receivers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for pid in receiverPrincipalIds: {
  scope: sb
  name: guid(sb.id, pid, dataReceiverRoleId)
  properties: {
    principalId: pid
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', dataReceiverRoleId)
    principalType: 'ServicePrincipal'
  }
}]

resource sbDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: sb
  name: 'diag-${sbName}'
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

output namespaceId string = sb.id
output namespaceName string = sb.name
output namespaceFqdn string = '${sb.name}.servicebus.windows.net'
output queueName string = queue.name
