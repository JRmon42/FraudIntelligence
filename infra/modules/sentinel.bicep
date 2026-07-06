// ============================================================================
// sentinel.bicep — Onboard the Log Analytics workspace to Microsoft Sentinel
//
// Enabling Sentinel (SIEM/SOAR) is free; cost is driven by data ingestion.
// This onboards the existing workspace and enables the SecurityInsights
// solution so the analytics/hunting/incident experience is available.
// ============================================================================
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param tags object

@description('Name of the existing Log Analytics workspace to onboard.')
param workspaceName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

// Modern onboarding state (idempotent).
resource onboarding 'Microsoft.SecurityInsights/onboardingStates@2024-03-01' = {
  scope: workspace
  name: 'default'
  properties: {}
}

// Legacy solution registration keeps the classic Sentinel blade wired up.
resource sentinelSolution 'Microsoft.OperationsManagement/solutions@2015-11-01-preview' = {
  name: 'SecurityInsights(${workspaceName})'
  location: location
  tags: tags
  plan: {
    name: 'SecurityInsights(${workspaceName})'
    product: 'OMSGallery/SecurityInsights'
    publisher: 'Microsoft'
    promotionCode: ''
  }
  properties: {
    workspaceResourceId: workspace.id
  }
  dependsOn: [ onboarding ]
}

output sentinelWorkspaceId string = workspace.id
