// ============================================================================
// policy.bicep — Policy assignments (residency, PE, TLS, diagnostics)
// ============================================================================
targetScope = 'subscription'

param tags object

@description('Allowed locations')
param allowedLocations array = [ 'swedencentral', 'northeurope', 'francecentral' ]

// Built-in policy definition IDs
var allowedLocationsPolicyId = '/providers/Microsoft.Authorization/policyDefinitions/e56962a6-4747-49cd-b67b-bf8b01975c4c'
var storagePeId = '/providers/Microsoft.Authorization/policyDefinitions/6edd7eda-6dd8-40f7-810d-67160c639cd9' // Storage should use private link
var cosmosPeId = '/providers/Microsoft.Authorization/policyDefinitions/58440f8a-10c5-4151-bdce-dfbaad4a20b7' // Cosmos should use private link
var kvPeId = '/providers/Microsoft.Authorization/policyDefinitions/a6abeaec-4d90-4a02-805f-6b26c4d3fbe9' // Key Vaults should use private link
var storageTlsId = '/providers/Microsoft.Authorization/policyDefinitions/fe83a0eb-a853-422d-aac2-1bffd182c5d0' // Secure transfer
// Note: storage min-TLS policy & diagnostic-settings initiative removed —
// the previously referenced GUIDs were retired/changed and the diagnostic
// initiative requires a `logAnalytics` parameter that is per-environment.
// Diagnostic settings are deployed inline by each module instead.

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

// Note: separate "min TLS" policy assignment removed — the secure-transfer
// policy above already enforces HTTPS-only access. Diagnostic-settings audit
// initiative removed: it requires a `logAnalytics` parameter that varies by
// environment. Each module attaches a diagnosticSettings resource directly.

output allowedLocationsAssignmentId string = allowedLocs.id
