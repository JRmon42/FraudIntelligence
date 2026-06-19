// ============================================================================
// main.bicep — Subscription scope: creates RGs + per-region platform
// ============================================================================
targetScope = 'subscription'

@description('Environment short (prod/dev)')
param env string = 'prod'

@description('Primary location')
param primaryLocation string = 'swedencentral'

@description('Disaster recovery location')
param drLocation string = 'northeurope'

@description('Short code for the primary region, used in resource names (e.g. swc)')
param primaryRegionCode string = 'swc'

@description('Short code for the DR region, used in resource names (e.g. neu)')
param drRegionCode string = 'neu'

@description('Name of the primary resource group')
param primaryResourceGroupName string = 'heimdall_rg'

@description('Name of the DR resource group')
param drResourceGroupName string = 'heimdall_dr_rg'

@description('Deploy the secondary (DR) region. When false, only the primary region is built. Set true later to add cross-region active/active without redeploying primary.')
param enableDr bool = false

@description('Common tags applied to every resource')
param tags object = {
  project: 'Heimdall'
  env: 'prod'
  costCenter: 'AMA-Capstone'
  dataClass: 'PII-Restricted'
  owner: 'JRmon42'
}

@description('Object IDs of Key Vault administrators')
param kvAdminPrincipalIds array = []

@description('Fabric capacity admin members (UPNs or object IDs)')
param fabricAdminMembers array = []

@description('AAD admin object ID for Synapse')
param synapseAadAdminObjectId string

@description('AAD admin login name for Synapse')
param synapseAadAdminLogin string

@secure()
@description('Synapse SQL admin password (required by API even when using AAD)')
param synapseSqlAdminPassword string

@description('Email receivers for monitor alerts')
param alertEmailReceivers array = []

@description('Optional CMK URI for OpenAI/Cosmos. Leave empty for first deploy.')
param cmkKeyUri string = ''

// ---------------------------------------------------------------------------
// Resource groups
// ---------------------------------------------------------------------------
resource primaryRg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: primaryResourceGroupName
  location: primaryLocation
  tags: tags
}

resource drRg 'Microsoft.Resources/resourceGroups@2024-03-01' = if (enableDr) {
  name: drResourceGroupName
  location: drLocation
  tags: tags
}

// ---------------------------------------------------------------------------
// Subscription-scope: Defender + Policy
// ---------------------------------------------------------------------------
module defender 'modules/defender.bicep' = {
  name: 'defender-plans'
}

module policy 'modules/policy.bicep' = {
  name: 'policy-baseline'
  params: { tags: tags }
}

// ---------------------------------------------------------------------------
// Per-region platform
// ---------------------------------------------------------------------------
module primary 'platform.bicep' = {
  name: 'platform-primary'
  scope: primaryRg
  params: {
    env: env
    regionCode: primaryRegionCode
    location: primaryLocation
    isPrimary: true
    tags: tags
    secondaryLocation: drLocation
    partnerRegionCode: drRegionCode
    enableDr: enableDr
    kvAdminPrincipalIds: kvAdminPrincipalIds
    fabricAdminMembers: fabricAdminMembers
    amlAadAdminObjectId: synapseAadAdminObjectId
    amlAadAdminLogin: synapseAadAdminLogin
    synapseSqlAdminPassword: synapseSqlAdminPassword
    alertEmailReceivers: alertEmailReceivers
    cmkKeyUri: cmkKeyUri
    // partnerEventHubsNamespaceId is deliberately NOT set to avoid a circular
    // dependency with the DR region. The geo-DR alias can be created in a
    // follow-up deployment once both regions have provisioned successfully.
  }
}

module dr 'platform.bicep' = if (enableDr) {
  name: 'platform-dr'
  scope: drRg
  params: {
    env: env
    regionCode: drRegionCode
    location: drLocation
    isPrimary: false
    tags: tags
    secondaryLocation: primaryLocation
    partnerRegionCode: primaryRegionCode
    enableDr: true
    kvAdminPrincipalIds: kvAdminPrincipalIds
    fabricAdminMembers: fabricAdminMembers
    amlAadAdminObjectId: synapseAadAdminObjectId
    amlAadAdminLogin: synapseAadAdminLogin
    synapseSqlAdminPassword: synapseSqlAdminPassword
    alertEmailReceivers: alertEmailReceivers
    cmkKeyUri: cmkKeyUri
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
output primaryResourceGroup string = primaryRg.name
output drResourceGroup string = enableDr ? drRg.name : ''
output primaryKeyVaultUri string = primary.outputs.keyVaultUri
output primaryAcrLoginServer string = primary.outputs.acrLoginServer
output primaryCosmosEndpoint string = primary.outputs.cosmosEndpoint
output primaryOpenAiEndpoint string = primary.outputs.openAiEndpoint
output primaryEventHubsNamespace string = primary.outputs.eventHubsNamespaceName
output drEventHubsNamespace string = enableDr ? dr.outputs.eventHubsNamespaceName : ''
output scoringFrontDoorHost string = primary.outputs.frontDoorScoringHost
output consoleFrontDoorHost string = primary.outputs.frontDoorConsoleHost
output synapseServerlessEndpoint string = primary.outputs.synapseServerlessEndpoint
output fabricCapacityName string = primary.outputs.fabricCapacityName
output purviewName string = primary.outputs.purviewName
output amlWorkspaceName string = primary.outputs.amlName
