// ============================================================================
// streamanalytics.bicep — ASA job: txn.events -> features
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string

@description('Event Hubs namespace name (input + output)')
param eventHubsNamespaceName string

@description('Cosmos account name (output reference store)')
param cosmosAccountName string

@description('Cosmos database for features output')
param cosmosDatabaseName string = 'fraud'

@description('Cosmos container for features output')
param cosmosContainerName string = 'features'

@description('Streaming units')
param streamingUnits int = 3

var jobName = 'asa-heimdall-${env}-${regionCode}'

resource asa 'Microsoft.StreamAnalytics/streamingjobs@2021-10-01-preview' = {
  name: jobName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    sku: { name: 'StandardV2' }
    eventsOutOfOrderPolicy: 'Adjust'
    outputErrorPolicy: 'Drop'
    eventsOutOfOrderMaxDelayInSeconds: 5
    eventsLateArrivalMaxDelayInSeconds: 16
    dataLocale: 'en-US'
    compatibilityLevel: '1.2'
    jobType: 'Cloud'
    inputs: [
      {
        name: 'txnInput'
        properties: {
          type: 'Stream'
          datasource: {
            type: 'Microsoft.ServiceBus/EventHub'
            properties: {
              serviceBusNamespace: eventHubsNamespaceName
              eventHubName: 'txn.events'
              consumerGroupName: 'asa'
              authenticationMode: 'Msi'
            }
          }
          serialization: {
            type: 'Json'
            properties: { encoding: 'UTF8' }
          }
        }
      }
    ]
    outputs: [
      {
        name: 'featuresHub'
        properties: {
          datasource: {
            type: 'Microsoft.ServiceBus/EventHub'
            properties: {
              serviceBusNamespace: eventHubsNamespaceName
              eventHubName: 'feature.events'
              authenticationMode: 'Msi'
            }
          }
          serialization: {
            type: 'Json'
            properties: { encoding: 'UTF8', format: 'LineSeparated' }
          }
        }
      }
      {
        name: 'featuresCosmos'
        properties: {
          datasource: {
            type: 'Microsoft.Storage/DocumentDB'
            properties: {
              accountId: cosmosAccountName
              database: cosmosDatabaseName
              collectionNamePattern: cosmosContainerName
              partitionKey: 'cardId'
              authenticationMode: 'Msi'
            }
          }
        }
      }
    ]
    transformation: {
      name: 'features'
      properties: {
        streamingUnits: streamingUnits
        query: '''
          WITH Enriched AS (
            SELECT
              t.transactionId,
              t.cardId,
              t.merchantId,
              t.amount,
              t.currency,
              t.eventTimestamp,
              System.Timestamp() AS processedAt
            FROM txnInput t
          ),
          Aggregated AS (
            SELECT
              cardId,
              System.Timestamp() AS windowEnd,
              COUNT(*) AS txnCount5m,
              SUM(amount) AS amountSum5m,
              AVG(amount) AS amountAvg5m,
              MAX(amount) AS amountMax5m
            FROM Enriched
            GROUP BY cardId, TumblingWindow(minute, 5)
          )
          SELECT * INTO featuresHub FROM Aggregated;
          SELECT * INTO featuresCosmos FROM Aggregated;
        '''
      }
    }
  }
}

resource asaDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: asa
  name: 'diag-${jobName}'
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

output asaId string = asa.id
output asaName string = asa.name
output asaPrincipalId string = asa.identity.principalId

// ---------------------------------------------------------------------------
// RBAC for the ASA managed identity (namespace has disableLocalAuth=true, so
// MSI data-plane roles are required for the txn.events input, feature.events
// output, and the Cosmos `features` output).
// ---------------------------------------------------------------------------
resource ehns 'Microsoft.EventHub/namespaces@2024-01-01' existing = {
  name: eventHubsNamespaceName
}

resource cosmosAcct 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosAccountName
}

@description('Azure Event Hubs Data Receiver')
var ehReceiverRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a638d3c7-ab3a-418d-83e6-5f17a39d4fde')
@description('Azure Event Hubs Data Sender')
var ehSenderRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '2b629674-e913-4c01-ae53-ef4638d8f975')
@description('DocumentDB Account Contributor (control plane, listKeys for ASA Cosmos output)')
var docdbContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5bd9cd88-fe45-4216-938b-f97437e15450')

resource asaEhReceiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ehns.id, asa.id, 'eh-data-receiver')
  scope: ehns
  properties: {
    principalId: asa.identity.principalId
    roleDefinitionId: ehReceiverRoleId
    principalType: 'ServicePrincipal'
  }
}

resource asaEhSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ehns.id, asa.id, 'eh-data-sender')
  scope: ehns
  properties: {
    principalId: asa.identity.principalId
    roleDefinitionId: ehSenderRoleId
    principalType: 'ServicePrincipal'
  }
}

resource asaCosmosControl 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cosmosAcct.id, asa.id, 'docdb-account-contributor')
  scope: cosmosAcct
  properties: {
    principalId: asa.identity.principalId
    roleDefinitionId: docdbContributorRoleId
    principalType: 'ServicePrincipal'
  }
}

resource asaCosmosData 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosAcct
  name: guid(cosmosAcct.id, asa.id, 'cosmos-data-contributor')
  properties: {
    principalId: asa.identity.principalId
    roleDefinitionId: '${cosmosAcct.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: cosmosAcct.id
  }
}
