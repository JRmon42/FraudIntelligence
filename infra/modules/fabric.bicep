// ============================================================================
// fabric.bicep — Microsoft.Fabric capacity (F2)
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

@description('SKU name (e.g., F2, F4)')
param skuName string = 'F2'

@description('AAD object IDs of capacity admins')
param adminMembers array

var capacityName = replace('fab-fraudintel-${env}-${regionCode}', '-', '')

resource cap 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: capacityName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: adminMembers
    }
  }
}

output capacityId string = cap.id
output capacityName string = cap.name
