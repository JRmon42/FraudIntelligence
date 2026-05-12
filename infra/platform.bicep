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

@description('RG that holds the private DNS zones consumed by this region. Defaults to the local RG so each region is independent.')
param dnsZoneResourceGroupName string = resourceGroup().name

// Identity / admin params
param kvAdminPrincipalIds array = []
param fabricAdminMembers array = []
param amlAadAdminObjectId string
param amlAadAdminLogin string
@secure()
param synapseSqlAdminPassword string
param alertEmailReceivers array = []

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
    cmkKeyUri: cmkKeyUri
    keyVaultId: kv.outputs.keyVaultId
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

// Outputs (best-effort — some are null in DR region)
output logAnalyticsId string = logs.outputs.workspaceId
output keyVaultName string = kv.outputs.keyVaultName
output keyVaultUri string = kv.outputs.keyVaultUri
output eventHubsNamespaceId string = eh.outputs.namespaceId
output eventHubsNamespaceName string = eh.outputs.namespaceName
output cosmosEndpoint string = isPrimary ? cosmos.outputs.cosmosEndpoint : ''
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
