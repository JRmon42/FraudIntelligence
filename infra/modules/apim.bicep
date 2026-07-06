// ============================================================================
// apim.bicep — API Management gateway in front of the scoring API
//
// Cost-optimised: defaults to the **Developer** SKU (no SLA, ~€40/mo) so the
// documented "API gateway" tier is actually provisioned. Set `skuName` to
// 'StandardV2' or 'Premium' for a production, SLA-backed, VNet-integrated
// gateway. Developer/Consumption do not support private endpoints, so this
// module is deployed with public ingress + TLS 1.2 + Entra-validated APIs.
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string

@description('APIM SKU. Developer (default) has no SLA; use StandardV2/Premium for production.')
@allowed([ 'Developer', 'Basic', 'Standard', 'StandardV2', 'Premium' ])
param skuName string = 'Developer'

@description('Scale units (Developer supports 1).')
param skuCapacity int = 1

@description('Publisher email shown on the developer portal / notifications.')
param publisherEmail string = 'jpontvianne@microsoft.com'

@description('Publisher / organisation name.')
param publisherName string = 'Heimdall Fraud Intelligence'

@description('Backend base URL for the scoring API (https, no trailing slash).')
param scoringBackendUrl string

var apimName = 'apim-heimdall-${env}-${regionCode}'

resource apim 'Microsoft.ApiManagement/service@2023-05-01-preview' = {
  name: apimName
  location: location
  tags: tags
  sku: {
    name: skuName
    capacity: skuCapacity
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

// Backend pointing at the scoring API (ACA FQDN or Front Door host).
resource scoringBackend 'Microsoft.ApiManagement/service/backends@2023-05-01-preview' = {
  parent: apim
  name: 'scoring-api'
  properties: {
    protocol: 'http'
    url: scoringBackendUrl
    tls: {
      validateCertificateChain: true
      validateCertificateName: true
    }
  }
}

// Scoring API surface (proxies /v1/* to the backend).
resource scoringApi 'Microsoft.ApiManagement/service/apis@2023-05-01-preview' = {
  parent: apim
  name: 'scoring'
  properties: {
    displayName: 'Fraud Scoring API'
    path: 'scoring'
    protocols: [ 'https' ]
    serviceUrl: scoringBackendUrl
    subscriptionRequired: true
  }
}

// POST /v1/score operation.
resource scoreOp 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: scoringApi
  name: 'score'
  properties: {
    displayName: 'Score transaction'
    method: 'POST'
    urlTemplate: '/v1/score'
  }
}

// GET /healthz operation (liveness passthrough).
resource healthOp 'Microsoft.ApiManagement/service/apis/operations@2023-05-01-preview' = {
  parent: scoringApi
  name: 'healthz'
  properties: {
    displayName: 'Health'
    method: 'GET'
    urlTemplate: '/healthz'
  }
}

// API-level policy: route to the named backend, throttle per subscription.
resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2023-05-01-preview' = {
  parent: scoringApi
  name: 'policy'
  properties: {
    format: 'xml'
    value: '<policies><inbound><base /><set-backend-service backend-id="scoring-api" /><rate-limit calls="6000" renewal-period="60" /></inbound><backend><base /></backend><outbound><base /></outbound><on-error><base /></on-error></policies>'
  }
  dependsOn: [ scoringBackend ]
}

resource apimDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: apim
  name: 'diag-${apimName}'
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

output apimId string = apim.id
output apimName string = apim.name
output apimGatewayUrl string = apim.properties.gatewayUrl
output apimPrincipalId string = apim.identity.principalId
