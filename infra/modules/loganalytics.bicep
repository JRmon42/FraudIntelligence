// ============================================================================
// loganalytics.bicep — Log Analytics workspace + workspace-based App Insights
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

@description('LA SKU')
param sku string = 'PerGB2018'

@description('Retention days')
param retentionDays int = 90

var laName = 'log-heimdall-${env}-${regionCode}'
var aiName = 'appi-heimdall-${env}-${regionCode}'

resource la 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: laName
  location: location
  tags: tags
  properties: {
    sku: { name: sku }
    retentionInDays: retentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource ai 'Microsoft.Insights/components@2020-02-02' = {
  name: aiName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: la.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output workspaceId string = la.id
output workspaceName string = la.name
output workspaceCustomerId string = la.properties.customerId
@secure()
output workspaceSharedKey string = la.listKeys().primarySharedKey
output appInsightsId string = ai.id
output appInsightsName string = ai.name
output appInsightsConnectionString string = ai.properties.ConnectionString
output appInsightsInstrumentationKey string = ai.properties.InstrumentationKey
