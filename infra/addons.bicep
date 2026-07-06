// ============================================================================
// addons.bicep — Incremental deploy of the previously "reference-only" tiers
//
// Deploys APIM (Developer), Redis (Basic C0), Service Bus (Standard), the
// enforcement Function (Consumption) and Microsoft Sentinel into the EXISTING
// heimdall_rg, wiring them to the already-deployed Log Analytics workspace,
// App Insights and Container Apps. This lets us add the tiers without
// redeploying the whole platform (Fabric/Synapse/Cosmos/etc.).
//
//   az deployment group create -g heimdall_rg -f infra/addons.bicep \
//     -p env=prod regionCode=swc
// ============================================================================
targetScope = 'resourceGroup'

param env string = 'prod'
param regionCode string = 'swc'
param location string = resourceGroup().location

param tags object = {
  project: 'Heimdall'
  env: 'prod'
  costCenter: 'AMA-Capstone'
  dataClass: 'PII-Restricted'
  owner: 'JRmon42'
}

@description('Existing Log Analytics workspace name.')
param logAnalyticsName string = 'log-heimdall-${env}-${regionCode}'

@description('Existing App Insights component name.')
param appInsightsName string = 'appi-heimdall-${env}-${regionCode}'

@description('Existing scoring-api Container App name.')
param scoringAppName string = 'ca-scoring-${env}-${regionCode}'

@description('Existing orchestrator Container App name.')
param orchestratorAppName string = 'ca-orchestrator-${env}-${regionCode}'

// ---- Existing resources (already deployed) --------------------------------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsName
}

resource appi 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource scoringApp 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: scoringAppName
}

resource orchestratorApp 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: orchestratorAppName
}

var scoringFqdn = scoringApp.properties.configuration.ingress.fqdn
var scoringPrincipalId = scoringApp.identity.principalId
var orchestratorPrincipalId = orchestratorApp.identity.principalId
// Deterministic Service Bus FQDN (namespace name is fixed inside servicebus.bicep).
var serviceBusFqdn = 'sbns-heimdall-${env}-${regionCode}.servicebus.windows.net'

// ---- New tiers -------------------------------------------------------------
module redis 'modules/redis.bicep' = {
  name: 'redis-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: law.id
    dataPrincipalIds: [ scoringPrincipalId ]
  }
}

// Enforcement Function first: its managed identity is needed for the Service
// Bus receiver role assignment. It only needs the (deterministic) SB FQDN.
module fn 'modules/functions.bicep' = {
  name: 'fn-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    appInsightsConnectionString: appi.properties.ConnectionString
    serviceBusFqdn: serviceBusFqdn
  }
}

module sb 'modules/servicebus.bicep' = {
  name: 'sb-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: law.id
    senderPrincipalIds: [ scoringPrincipalId, orchestratorPrincipalId ]
    receiverPrincipalIds: [ fn.outputs.functionPrincipalId ]
  }
}

module apim 'modules/apim.bicep' = {
  name: 'apim-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: law.id
    scoringBackendUrl: 'https://${scoringFqdn}'
  }
}

module sentinel 'modules/sentinel.bicep' = {
  name: 'sentinel-${regionCode}'
  params: {
    location: location
    tags: tags
    workspaceName: logAnalyticsName
  }
}

output redisHostName string = redis.outputs.redisHostName
output serviceBusNamespace string = sb.outputs.namespaceName
output serviceBusQueue string = sb.outputs.queueName
output enforcementFunctionName string = fn.outputs.functionName
output apimGatewayUrl string = apim.outputs.apimGatewayUrl
