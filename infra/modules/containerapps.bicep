// ============================================================================
// containerapps.bicep — ACA env (Consumption + D8 Dedicated) + 2 apps
// ============================================================================
targetScope = 'resourceGroup'

param env string
param regionCode string
param location string = resourceGroup().location
param tags object

param logAnalyticsWorkspaceId string
@description('Workspace customerId (for ACA env)')
param logAnalyticsCustomerId string
@description('Workspace primary shared key — pulled at deploy time via listKeys')
@secure()
param logAnalyticsSharedKey string

param acaSubnetId string
param appInsightsConnectionString string

@description('User-assigned identity resource ID OR empty to use system-assigned')
param userAssignedIdentityId string = ''

@description('Container image for orchestrator (e.g., acr.azurecr.io/orchestrator:tag)')
param orchestratorImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Container image for scoring API')
param scoringImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

var envName = 'cae-heimdall-${env}-${regionCode}'

resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
      {
        name: 'd8-dedicated'
        workloadProfileType: 'D8'
        minimumCount: 1
        maximumCount: 3
      }
    ]
    vnetConfiguration: {
      internal: false
      infrastructureSubnetId: acaSubnetId
    }
    zoneRedundant: true
    // Note: openTelemetryConfiguration removed — not supported in current ACA
    // ManagedEnvironment ARM API. OTel collectors are deployed as a sidecar
    // ContainerApp (see ops/otel/) which scrapes app endpoints and forwards
    // to Application Insights via the Connection String env var.
  }
}

resource orchestrator 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-orchestrator-${env}-${regionCode}'
  location: location
  tags: tags
  identity: empty(userAssignedIdentityId) ? {
    type: 'SystemAssigned'
  } : {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: { '${userAssignedIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'appinsights-connection'
          value: appInsightsConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'orchestrator'
          image: orchestratorImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
            { name: 'OTEL_SERVICE_NAME', value: 'orchestrator' }
          ]
          // Liveness/readiness/startup probes let ACA evict and reschedule an
          // unhealthy replica automatically (resilience: pod-level failure).
          probes: [
            { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 10, failureThreshold: 3 }
            { type: 'Readiness', httpGet: { path: '/readyz', port: 8080 }, periodSeconds: 5, failureThreshold: 3, timeoutSeconds: 3 }
            { type: 'Startup', httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 5, failureThreshold: 30 }
          ]
        }
      ]
      scale: {
        // Case-work is bursty: autoscale on HTTP concurrency so a surge of
        // alerts after a fraud spike is absorbed without a backlog.
        minReplicas: 1
        maxReplicas: 30
        rules: [
          {
            name: 'orchestrator-http'
            http: { metadata: { concurrentRequests: '50' } }
          }
        ]
      }
    }
  }
}

resource scoring 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-scoring-${env}-${regionCode}'
  location: location
  tags: tags
  identity: empty(userAssignedIdentityId) ? {
    type: 'SystemAssigned'
  } : {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: { '${userAssignedIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    workloadProfileName: 'd8-dedicated'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
        // Note: ACA ipSecurityRestrictions only accepts CIDR ranges, not
        // service tags. Front Door origin lock-down is enforced inside
        // the app by validating the X-Azure-FDID header against the
        // expected Front Door instance ID.
      }
      secrets: [
        {
          name: 'appinsights-connection'
          value: appInsightsConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'scoring'
          image: scoringImage
          resources: { cpu: json('2'), memory: '4Gi' }
          env: [
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
            { name: 'OTEL_SERVICE_NAME', value: 'scoring' }
          ]
          // Health probes drive zero-downtime rolling updates and automatic
          // eviction of a degraded replica. /readyz reports Cosmos+Redis+model.
          probes: [
            { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 10, failureThreshold: 3 }
            { type: 'Readiness', httpGet: { path: '/readyz', port: 8080 }, periodSeconds: 5, failureThreshold: 3, timeoutSeconds: 2 }
            { type: 'Startup', httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 3, failureThreshold: 40 }
          ]
        }
      ]
      scale: {
        // Elastic hot path: 3 replicas baseline (one per zone) up to 60 to
        // absorb a transaction spike. KEDA adds replicas on HTTP concurrency
        // within seconds; falls back to 3 off-peak to keep cost near-zero.
        minReplicas: 3
        maxReplicas: 60
        rules: [
          {
            name: 'http-rule'
            http: { metadata: { concurrentRequests: '100' } }
          }
        ]
      }
    }
  }
}

resource envDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: acaEnv
  name: 'diag-${envName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
  }
}

output environmentId string = acaEnv.id
output environmentName string = acaEnv.name
output environmentDefaultDomain string = acaEnv.properties.defaultDomain
output orchestratorFqdn string = orchestrator.properties.configuration.ingress.fqdn
output scoringFqdn string = scoring.properties.configuration.ingress.fqdn
output scoringPrincipalId string = scoring.identity.principalId
output orchestratorPrincipalId string = orchestrator.identity.principalId
