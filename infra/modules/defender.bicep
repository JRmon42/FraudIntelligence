// ============================================================================
// defender.bicep — Enable Defender for Cloud plans
// ============================================================================
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
}

resource keyVaults 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'KeyVaults'
  properties: { pricingTier: 'Standard', subPlan: 'PerKeyVault' }
}

resource storage 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'StorageAccounts'
  properties: {
    pricingTier: 'Standard'
    subPlan: 'DefenderForStorageV2'
  }
}

resource cosmos 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'CosmosDbs'
  properties: { pricingTier: 'Standard' }
}

resource appServices 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'AppServices'
  properties: { pricingTier: 'Standard' }
}

resource openAi 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'AI'
  properties: { pricingTier: 'Standard' }
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
