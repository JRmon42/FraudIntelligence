// ============================================================================
// policy.bicep — Policy assignments (residency, PE, TLS, diagnostics)
// ============================================================================
targetScope = 'subscription'

param tags object

@description('Allowed locations')
param allowedLocations array = [ 'swedencentral', 'northeurope', 'francecentral' ]

// Built-in policy definition IDs
var allowedLocationsPolicyId = '/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c'
var requireDiagSettingsInitiativeId = '/providers/Microsoft.Authorization/policySetDefinitions/0884adba-2312-4468-abeb-5422caed1038' // Audit diagnostic setting (initiative)
var storagePeId = '/providers/Microsoft.Authorization/policyDefinitions/6edd7eda-6dd8-40f7-810d-67160c639cd9' // Storage should use private link
var cosmosPeId = '/providers/Microsoft.Authorization/policyDefinitions/58440f8a-10c5-4151-bdce-dfbaad4a20b7' // Cosmos should use private link
var kvPeId = '/providers/Microsoft.Authorization/policyDefinitions/a6abeaec-4d90-4a02-805f-6b26c4d3fbe9' // Key Vaults should use private link
var storageTlsId = '/providers/Microsoft.Authorization/policyDefinitions/fe83a0eb-a853-422d-aac2-1bffd182c5d0' // Secure transfer
var minTlsId = '/providers/Microsoft.Authorization/policyDefinitions/32a6bbec-4be9-474f-b829-bd47cb957b76' // Storage min TLS

resource allowedLocs 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'fraudintel-allowed-locations'
  properties: {
    displayName: 'FraudIntel — Allowed locations (EU only)'
    policyDefinitionId: allowedLocationsPolicyId
    parameters: {
      listOfAllowedLocations: { value: allowedLocations }
    }
    enforcementMode: 'Default'
  }
}

resource storagePe 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'fraudintel-storage-pe'
  properties: {
    displayName: 'FraudIntel — Storage requires private link'
    policyDefinitionId: storagePeId
    enforcementMode: 'Default'
  }
}

resource cosmosPe 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'fraudintel-cosmos-pe'
  properties: {
    displayName: 'FraudIntel — Cosmos requires private link'
    policyDefinitionId: cosmosPeId
    enforcementMode: 'Default'
  }
}

resource kvPe 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'fraudintel-kv-pe'
  properties: {
    displayName: 'FraudIntel — Key Vault requires private link'
    policyDefinitionId: kvPeId
    enforcementMode: 'Default'
  }
}

resource storageTls 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'fraudintel-storage-tls'
  properties: {
    displayName: 'FraudIntel — Secure transfer required'
    policyDefinitionId: storageTlsId
    enforcementMode: 'Default'
  }
}

resource minTls 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'fraudintel-storage-min-tls12'
  properties: {
    displayName: 'FraudIntel — Storage minimum TLS 1.2'
    policyDefinitionId: minTlsId
    parameters: {
      minimumTlsVersion: { value: 'TLS1_2' }
    }
    enforcementMode: 'Default'
  }
}

resource diagInit 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'fraudintel-diag-audit'
  properties: {
    displayName: 'FraudIntel — Audit diagnostic settings'
    policyDefinitionId: requireDiagSettingsInitiativeId
    enforcementMode: 'Default'
  }
}

output allowedLocationsAssignmentId string = allowedLocs.id
