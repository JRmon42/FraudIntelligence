// ============================================================================
// defender.bicep — Enable Defender for Cloud plans
// ============================================================================
// NOTE: Defender pricing PUTs are serialized server-side at the subscription
// scope. Parallel deployment by ARM produces 'Conflict: Another update
// operation in progress' on all but one. We chain them with dependsOn to
// force sequential execution.
targetScope = 'subscription'

resource servers 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'VirtualMachines'
  properties: {
    pricingTier: 'Standard'
    subPlan: 'P2'
  }
}

resource containers 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'Containers'
  properties: { pricingTier: 'Standard' }
  dependsOn: [ servers ]
}

resource keyVaults 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'KeyVaults'
  properties: { pricingTier: 'Standard', subPlan: 'PerKeyVault' }
  dependsOn: [ containers ]
}

resource storage 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'StorageAccounts'
  properties: {
    pricingTier: 'Standard'
    subPlan: 'DefenderForStorageV2'
  }
  dependsOn: [ keyVaults ]
}

resource cosmos 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'CosmosDbs'
  properties: { pricingTier: 'Standard' }
  dependsOn: [ storage ]
}

resource appServices 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'AppServices'
  properties: { pricingTier: 'Standard' }
  dependsOn: [ cosmos ]
}

resource openAi 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'AI'
  properties: { pricingTier: 'Standard' }
  dependsOn: [ appServices ]
}

output enabledPlans array = [
  servers.name
  containers.name
  keyVaults.name
  storage.name
  cosmos.name
  appServices.name
  openAi.name
]
