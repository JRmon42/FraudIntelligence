// ============================================================================
// network.bicep — VNet, subnets, NSGs, Private DNS Zones
// ============================================================================
targetScope = 'resourceGroup'

@description('Environment short name (e.g., prod, dev)')
param env string

@description('Region short code (e.g., swc, neu)')
param regionCode string

@description('Azure region for the VNet')
param location string = resourceGroup().location

@description('VNet address space')
param vnetAddressSpace string = '10.50.0.0/16'

@description('Subnet CIDRs')
param subnetCidrs object = {
  aca:  '10.50.0.0/21'   // Container Apps (needs /21 minimum)
  pe:   '10.50.8.0/24'   // Private Endpoints
  agw:  '10.50.9.0/24'   // App Gateway / FD origin (reserved)
  mgmt: '10.50.10.0/24'  // Mgmt / jumpbox / build agents
}

@description('Common tags')
param tags object

@description('Log Analytics workspace ID for diagnostic settings')
param logAnalyticsWorkspaceId string

@description('If true this is the primary region; private DNS zones live here')
param isPrimary bool = true

var vnetName = 'vnet-heimdall-${env}-${regionCode}'

// ---------------------------------------------------------------------------
// NSGs
// ---------------------------------------------------------------------------
resource nsgAca 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-aca-${env}-${regionCode}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'Allow-Https-Inbound'
        properties: {
          priority: 100
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

resource nsgPe 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-pe-${env}-${regionCode}'
  location: location
  tags: tags
  properties: {}
}

resource nsgAgw 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-agw-${env}-${regionCode}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'Allow-AzureFrontDoor-Inbound'
        properties: {
          priority: 100
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'AzureFrontDoor.Backend'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
      {
        name: 'Allow-GwManager-Inbound'
        properties: {
          priority: 110
          protocol: 'Tcp'
          access: 'Allow'
          direction: 'Inbound'
          sourceAddressPrefix: 'GatewayManager'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '65200-65535'
        }
      }
    ]
  }
}

resource nsgMgmt 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: 'nsg-mgmt-${env}-${regionCode}'
  location: location
  tags: tags
  properties: {}
}

// ---------------------------------------------------------------------------
// VNet
// ---------------------------------------------------------------------------
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [vnetAddressSpace]
    }
    subnets: [
      {
        name: 'snet-aca'
        properties: {
          addressPrefix: subnetCidrs.aca
          networkSecurityGroup: { id: nsgAca.id }
          delegations: [
            {
              name: 'aca-delegation'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'snet-pe'
        properties: {
          addressPrefix: subnetCidrs.pe
          networkSecurityGroup: { id: nsgPe.id }
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: 'snet-agw'
        properties: {
          addressPrefix: subnetCidrs.agw
          networkSecurityGroup: { id: nsgAgw.id }
        }
      }
      {
        name: 'snet-mgmt'
        properties: {
          addressPrefix: subnetCidrs.mgmt
          networkSecurityGroup: { id: nsgMgmt.id }
        }
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Diagnostic Settings
// ---------------------------------------------------------------------------
resource vnetDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: vnet
  name: 'diag-${vnetName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

// ---------------------------------------------------------------------------
// Private DNS Zones (only in primary region — linked from both)
// ---------------------------------------------------------------------------
var dnsZoneNames = [
  'privatelink.vaultcore.azure.net'
  'privatelink.documents.azure.com'
  'privatelink.blob.core.windows.net'
  'privatelink.servicebus.windows.net' // Event Hubs
  'privatelink.search.windows.net'
  'privatelink.openai.azure.com'
  'privatelink.azurecr.io'
  'privatelink.monitor.azure.com'
  'privatelink.oms.opinsights.azure.com'
  'privatelink.ods.opinsights.azure.com'
  'privatelink.agentsvc.azure-automation.net'
  'privatelink.api.azureml.ms'
  'privatelink.notebooks.azure.net'
]

// Private DNS zones — created locally in EACH region's RG so that
// region failures don't block private endpoint resolution in the other.
resource dnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zone in dnsZoneNames: {
  name: zone
  location: 'global'
  tags: tags
}]

// Azure Monitor private DNS zones must NOT be linked to the VNet unless an
// Azure Monitor Private Link Scope (AMPLS) + private endpoint actually backs
// them. Linking the empty zones shadows the public CNAME chain for the App
// Insights ingestion endpoint (*.in.applicationinsights.azure.com ->
// *.privatelink.monitor.azure.com) and makes DNS return NXDOMAIN, so telemetry
// export silently fails. Since there is no AMPLS, skip linking these until one
// is introduced. (App Insights ingestion is public-network-access Enabled.)
var monitorZones = [
  'privatelink.monitor.azure.com'
  'privatelink.oms.opinsights.azure.com'
  'privatelink.ods.opinsights.azure.com'
]

resource dnsLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zone, i) in dnsZoneNames: if (!contains(monitorZones, zone)) {
  name: '${zone}/link-${vnetName}'
  location: 'global'
  dependsOn: [ dnsZones[i] ]
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet.id }
  }
}]

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------
output vnetId string = vnet.id
output vnetName string = vnet.name
output subnetAcaId string = '${vnet.id}/subnets/snet-aca'
output subnetPeId string = '${vnet.id}/subnets/snet-pe'
output subnetAgwId string = '${vnet.id}/subnets/snet-agw'
output subnetMgmtId string = '${vnet.id}/subnets/snet-mgmt'
output dnsZoneNames array = dnsZoneNames
