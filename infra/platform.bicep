// ============================================================================
// platform.bicep — Per-region orchestrator (resource group scope)
// ============================================================================
targetScope = 'resourceGroup'

@description('Environment short (prod/dev)')
param env string

@description('Region short code (swc/neu)')
param regionCode string

@description('Azure region')
param location string

@description('If true, this is the primary region')
param isPrimary bool

@description('Common tags')
param tags object

@description('Secondary location for replication targets')
param secondaryLocation string

@description('Region code of partner region (for naming partner resources)')
param partnerRegionCode string

@description('Whether the DR region is being deployed alongside primary. Controls Cosmos multi-region writes and ACR geo-replication on the primary side.')
param enableDr bool = false

@description('RG that holds the private DNS zones consumed by this region. Defaults to the local RG so each region is independent.')
param dnsZoneResourceGroupName string = resourceGroup().name

// Identity / admin params
param kvAdminPrincipalIds array = []
param cosmosDataPrincipalIds array = []
param grafanaAdminPrincipalIds array = []
param fabricAdminMembers array = []
param amlAadAdminObjectId string
param amlAadAdminLogin string
@secure()
param synapseSqlAdminPassword string
param alertEmailReceivers array = []

@description('Seed the scoring API in-memory feature store with curated demo entities (APPROVE/SCA/DECLINE).')
param seedDemoFeatures bool = false

// Optional CMK URI (post-bootstrap; leave empty on first deploy)
param cmkKeyUri string = ''

// Cross-region partner namespace (passed in only on primary for EH geo-DR)
param partnerEventHubsNamespaceId string = ''

// Sub-modules
module logs 'modules/loganalytics.bicep' = {
  name: 'logs-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
  }
}

module net 'modules/network.bicep' = {
  name: 'net-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    isPrimary: isPrimary
  }
}

// Private DNS zones live in the primary RG (created by network.bicep when isPrimary)
var kvDnsZoneId     = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.vaultcore.azure.net')
var cosmosDnsZoneId = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.documents.azure.com')
var blobDnsZoneId   = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.blob.core.windows.net')
var ehDnsZoneId     = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.servicebus.windows.net')
var oaiDnsZoneId    = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.openai.azure.com')
var acrDnsZoneId    = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.azurecr.io')
var amlApiDnsZoneId = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.api.azureml.ms')
var amlNbDnsZoneId  = resourceId(dnsZoneResourceGroupName, 'Microsoft.Network/privateDnsZones', 'privatelink.notebooks.azure.net')

module kv 'modules/keyvault.bicep' = {
  name: 'kv-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    peSubnetId: net.outputs.subnetPeId
    privateDnsZoneId: kvDnsZoneId
    adminPrincipalIds: kvAdminPrincipalIds
  }
  dependsOn: [ net ]
}

module acr 'modules/acr.bicep' = if (isPrimary) {
  name: 'acr-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    peSubnetId: net.outputs.subnetPeId
    privateDnsZoneId: acrDnsZoneId
    enableReplica: enableDr
    replicaLocation: secondaryLocation
  }
  dependsOn: [ net ]
}

module cosmos 'modules/cosmos.bicep' = if (isPrimary) {
  name: 'cosmos-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    peSubnetId: net.outputs.subnetPeId
    privateDnsZoneId: cosmosDnsZoneId
    secondaryLocation: secondaryLocation
    enableSecondaryRegion: enableDr
    cmkKeyUri: cmkKeyUri
    keyVaultId: kv.outputs.keyVaultId
    dataPlanePrincipalIds: cosmosDataPrincipalIds
  }
}

module grafana 'modules/grafana.bicep' = if (isPrimary) {
  name: 'grafana-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    adminPrincipalIds: grafanaAdminPrincipalIds
  }
}

module eh 'modules/eventhubs.bicep' = {
  name: 'eh-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    peSubnetId: net.outputs.subnetPeId
    privateDnsZoneId: ehDnsZoneId
    enableGeoDr: isPrimary && !empty(partnerEventHubsNamespaceId)
    partnerNamespaceId: partnerEventHubsNamespaceId
  }
}

module asa 'modules/streamanalytics.bicep' = if (isPrimary) {
  name: 'asa-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    eventHubsNamespaceName: eh.outputs.namespaceName
    cosmosAccountName: cosmos.outputs.cosmosName
  }
}

module aml 'modules/aml.bicep' = if (isPrimary) {
  name: 'aml-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    keyVaultId: kv.outputs.keyVaultId
    appInsightsId: logs.outputs.appInsightsId
    acrId: acr.outputs.acrId
    peSubnetId: net.outputs.subnetPeId
    amlApiDnsZoneId: amlApiDnsZoneId
    amlNotebooksDnsZoneId: amlNbDnsZoneId
  }
}

module oai 'modules/openai.bicep' = if (isPrimary) {
  name: 'oai-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    peSubnetId: net.outputs.subnetPeId
    privateDnsZoneId: oaiDnsZoneId
    cmkKeyUri: cmkKeyUri
  }
}

module aca 'modules/containerapps.bicep' = {
  name: 'aca-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    logAnalyticsCustomerId: logs.outputs.workspaceCustomerId
    logAnalyticsSharedKey: logs.outputs.workspaceSharedKey
    acaSubnetId: net.outputs.subnetAcaId
    appInsightsConnectionString: logs.outputs.appInsightsConnectionString
    seedDemoFeatures: seedDemoFeatures
    redisHost: isPrimary ? redisHost : ''
    redisSeedAggregates: seedDemoFeatures
    serviceBusFqdn: isPrimary ? serviceBusFqdn : ''
  }
}

module afd 'modules/frontdoor.bicep' = if (isPrimary) {
  name: 'afd-${regionCode}'
  params: {
    env: env
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    scoringOriginHost: aca.outputs.scoringFqdn
    consoleOriginHost: aca.outputs.orchestratorFqdn
  }
}

module fab 'modules/fabric.bicep' = if (isPrimary) {
  name: 'fab-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    adminMembers: fabricAdminMembers
  }
}

module syn 'modules/synapse.bicep' = if (isPrimary) {
  name: 'syn-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    sqlAdminPassword: synapseSqlAdminPassword
    aadAdminObjectId: amlAadAdminObjectId
    aadAdminLogin: amlAadAdminLogin
  }
}

module pv 'modules/purview.bicep' = if (isPrimary) {
  name: 'pv-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    sourceResourceIds: [
      cosmos.outputs.cosmosId
      syn.outputs.synapseStorageId
      syn.outputs.synapseId
    ]
  }
}

module mon 'modules/monitor.bicep' = if (isPrimary) {
  name: 'mon-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    emailReceivers: alertEmailReceivers
    appInsightsId: logs.outputs.appInsightsId
    cosmosId: cosmos.outputs.cosmosId
    eventHubsNamespaceId: eh.outputs.namespaceId
    amlWorkspaceId: aml.outputs.amlId
  }
}

// ---------------------------------------------------------------------------
// Previously "reference-only" tiers, now provisioned (cost-optimised SKUs).
// APIM Developer, Redis Basic C0, Service Bus Standard, enforcement Function
// (Consumption) and Microsoft Sentinel. Override SKUs via the module params
// for a production deployment.
// ---------------------------------------------------------------------------
var serviceBusFqdn = 'sbns-heimdall-${env}-${regionCode}.servicebus.windows.net'
// Deterministic Managed Redis hostname (avoids a redis<->aca output cycle).
var redisHost = 'redis-heimdall-${env}-${regionCode}.${location}.redis.azure.net'

module redis 'modules/redis.bicep' = if (isPrimary) {
  name: 'redis-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    dataPrincipalIds: [ aca.outputs.scoringPrincipalId ]
  }
}

// Enforcement Function first — its identity is needed for the Service Bus
// receiver role assignment; it only needs the deterministic SB FQDN.
module fn 'modules/functions.bicep' = if (isPrimary) {
  name: 'fn-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    appInsightsConnectionString: logs.outputs.appInsightsConnectionString
    serviceBusFqdn: serviceBusFqdn
    functionSubnetId: net.outputs.subnetFuncId
    cosmosAccountName: cosmos.outputs.cosmosName
    cosmosEndpoint: cosmos.outputs.cosmosEndpoint
    privateEndpointSubnetId: net.outputs.subnetPeId
    blobDnsZoneId: net.outputs.blobDnsZoneId
    queueDnsZoneId: net.outputs.queueDnsZoneId
    tableDnsZoneId: net.outputs.tableDnsZoneId
  }
}

module sb 'modules/servicebus.bicep' = if (isPrimary) {
  name: 'sb-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    senderPrincipalIds: [ aca.outputs.scoringPrincipalId, aca.outputs.orchestratorPrincipalId ]
    receiverPrincipalIds: [ fn.outputs.functionPrincipalId ]
  }
}

module apim 'modules/apim.bicep' = if (isPrimary) {
  name: 'apim-${regionCode}'
  params: {
    env: env
    regionCode: regionCode
    location: location
    tags: tags
    logAnalyticsWorkspaceId: logs.outputs.workspaceId
    scoringBackendUrl: 'https://${aca.outputs.scoringFqdn}'
  }
}

module sentinel 'modules/sentinel.bicep' = if (isPrimary) {
  name: 'sentinel-${regionCode}'
  params: {
    location: location
    tags: tags
    workspaceName: logs.outputs.workspaceName
  }
}

// Outputs (best-effort — some are null in DR region)
output logAnalyticsId string = logs.outputs.workspaceId
output keyVaultName string = kv.outputs.keyVaultName
output keyVaultUri string = kv.outputs.keyVaultUri
output eventHubsNamespaceId string = eh.outputs.namespaceId
output eventHubsNamespaceName string = eh.outputs.namespaceName
output cosmosEndpoint string = isPrimary ? cosmos.outputs.cosmosEndpoint : ''
output grafanaEndpoint string = isPrimary ? grafana.outputs.grafanaEndpoint : ''
output acrLoginServer string = isPrimary ? acr.outputs.acrLoginServer : ''
output openAiEndpoint string = isPrimary ? oai.outputs.openAiEndpoint : ''
output amlName string = isPrimary ? aml.outputs.amlName : ''
output scoringFqdn string = aca.outputs.scoringFqdn
output orchestratorFqdn string = aca.outputs.orchestratorFqdn
output frontDoorScoringHost string = isPrimary ? afd.outputs.scoringEndpointHost : ''
output frontDoorConsoleHost string = isPrimary ? afd.outputs.consoleEndpointHost : ''
output synapseServerlessEndpoint string = isPrimary ? syn.outputs.synapseServerlessEndpoint : ''
output fabricCapacityName string = isPrimary ? fab.outputs.capacityName : ''
output purviewName string = isPrimary ? pv.outputs.purviewName : ''
output apimGatewayUrl string = isPrimary ? apim.outputs.apimGatewayUrl : ''
output redisHostName string = isPrimary ? redis.outputs.redisHostName : ''
output serviceBusNamespace string = isPrimary ? sb.outputs.namespaceName : ''
output enforcementFunctionName string = isPrimary ? fn.outputs.functionName : ''
