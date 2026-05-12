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

var jobName = 'asa-fraudintel-${env}-${regionCode}'

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
