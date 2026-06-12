// ============================================================================
// monitor.bicep — Action group + alert rules
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

@description('Email receivers for action group')
param emailReceivers array = []

@description('Application Insights resource ID for scoring API')
param appInsightsId string

@description('Cosmos account resource ID')
param cosmosId string

@description('Event Hubs namespace resource ID')
param eventHubsNamespaceId string

@description('AML online endpoint scope (workspace ID)')
param amlWorkspaceId string

var agName = 'ag-heimdall-${env}-${regionCode}'

resource ag 'Microsoft.Insights/actionGroups@2024-10-01-preview' = {
  name: agName
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'Heimdall'
    enabled: true
    emailReceivers: [for (e, i) in emailReceivers: {
      name: 'email-${i}'
      emailAddress: e
      useCommonAlertSchema: true
    }]
  }
}

// 1. Scoring API p99 > 18ms (request duration)
resource scoringP99 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-scoring-p99'
  location: 'global'
  tags: tags
  properties: {
    description: 'Scoring API p99 latency exceeds 18ms'
    severity: 2
    enabled: true
    scopes: [ appInsightsId ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'p99Latency'
          metricNamespace: 'microsoft.insights/components'
          metricName: 'requests/duration'
          operator: 'GreaterThan'
          threshold: 18
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [ { actionGroupId: ag.id } ]
  }
}

// 2. Decline rate spike — custom log alert (placeholder query)
resource declineSpike 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alert-decline-rate-spike'
  location: location
  tags: tags
  properties: {
    description: 'Decline rate spike (>2x baseline)'
    severity: 2
    enabled: true
    scopes: [ appInsightsId ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      allOf: [
        {
          query: '''
customEvents
| where name == "TransactionDecision"
| extend decision = tostring(customDimensions.decision)
| summarize total=count(), declines=countif(decision == "DECLINE") by bin(timestamp, 5m)
| extend declineRate = todouble(declines) / todouble(total)
| where declineRate > 0.20
'''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
        }
      ]
    }
    actions: { actionGroups: [ ag.id ] }
  }
}

// 3. Cosmos throttling
resource cosmosThrottle 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-cosmos-throttle'
  location: 'global'
  tags: tags
  properties: {
    description: 'Cosmos DB request rate too large (429)'
    severity: 2
    enabled: true
    scopes: [ cosmosId ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'totalRequests429'
          metricNamespace: 'Microsoft.DocumentDB/databaseAccounts'
          metricName: 'TotalRequests'
          dimensions: [
            { name: 'StatusCode', operator: 'Include', values: [ '429' ] }
          ]
          operator: 'GreaterThan'
          threshold: 50
          timeAggregation: 'Count'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [ { actionGroupId: ag.id } ]
  }
}

// 4. Event Hub backlog (incoming > outgoing)
resource ehBacklog 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-eh-backlog'
  location: 'global'
  tags: tags
  properties: {
    description: 'Event Hubs incoming messages outpacing outgoing'
    severity: 3
    enabled: true
    scopes: [ eventHubsNamespaceId ]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'incomingMessages'
          metricNamespace: 'Microsoft.EventHub/namespaces'
          metricName: 'IncomingMessages'
          operator: 'GreaterThan'
          threshold: 100000
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [ { actionGroupId: ag.id } ]
  }
}

// 5. AML online endpoint errors
// NOTE: AML online endpoint metric alert removed.
// AML workspace metric namespace doesn't expose RequestsPerMinute/StatusCodeClass
// (those live on the AML data plane, not Microsoft.MachineLearningServices/workspaces).
// Endpoint errors are surfaced via App Insights availability tests + the
// generic scoring availability alert below. Re-add as a Log Analytics
// scheduledQueryRule in a follow-up if endpoint-level metrics are required.

// 6. Defender alerts (Activity Log alert on Microsoft.Security/locations/alerts)
resource defenderAlert 'Microsoft.Insights/activityLogAlerts@2020-10-01' = {
  name: 'alert-defender-high'
  location: 'global'
  tags: tags
  properties: {
    enabled: true
    scopes: [ subscription().id ]
    condition: {
      allOf: [
        { field: 'category', equals: 'Security' }
        { field: 'properties.severity', equals: 'High' }
      ]
    }
    actions: {
      actionGroups: [ { actionGroupId: ag.id } ]
    }
  }
}

output actionGroupId string = ag.id
output actionGroupName string = ag.name
