// ============================================================================
// frontdoor.bicep — Front Door Premium + WAF (OWASP 3.2 + Bot Manager)
// ============================================================================
targetScope = 'resourceGroup'

param env string
param tags object
param logAnalyticsWorkspaceId string

@description('Origin host for scoring API (ACA FQDN)')
param scoringOriginHost string

@description('Origin host for agentic console (ACA FQDN)')
param consoleOriginHost string

var profileName = 'afd-heimdall-${env}'
var wafName = 'wafHeimdall${env}'

resource afd 'Microsoft.Cdn/profiles@2024-02-01' = {
  name: profileName
  location: 'global'
  tags: tags
  sku: { name: 'Premium_AzureFrontDoor' }
  identity: { type: 'SystemAssigned' }
  properties: {
    originResponseTimeoutSeconds: 60
  }
}

resource waf 'Microsoft.Network/FrontDoorWebApplicationFirewallPolicies@2024-02-01' = {
  name: wafName
  location: 'global'
  tags: tags
  sku: { name: 'Premium_AzureFrontDoor' }
  properties: {
    policySettings: {
      enabledState: 'Enabled'
      mode: 'Prevention'
      requestBodyCheck: 'Enabled'
    }
    managedRules: {
      managedRuleSets: [
        {
          ruleSetType: 'Microsoft_DefaultRuleSet'
          ruleSetVersion: '2.1'
          ruleSetAction: 'Block'
        }
        {
          ruleSetType: 'Microsoft_BotManagerRuleSet'
          ruleSetVersion: '1.0'
        }
      ]
    }
  }
}

// ---------- Scoring API endpoint ----------
resource scoringEp 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' = {
  parent: afd
  name: 'scoring-${env}'
  location: 'global'
  tags: tags
  properties: { enabledState: 'Enabled' }
}

resource scoringOg 'Microsoft.Cdn/profiles/originGroups@2024-02-01' = {
  parent: afd
  name: 'og-scoring'
  properties: {
    loadBalancingSettings: {
      sampleSize: 4
      successfulSamplesRequired: 3
      additionalLatencyInMilliseconds: 50
    }
    healthProbeSettings: {
      probePath: '/health'
      probeRequestType: 'GET'
      probeProtocol: 'Https'
      probeIntervalInSeconds: 30
    }
  }
}

resource scoringOrigin 'Microsoft.Cdn/profiles/originGroups/origins@2024-02-01' = {
  parent: scoringOg
  name: 'scoring-origin'
  properties: {
    hostName: scoringOriginHost
    originHostHeader: scoringOriginHost
    httpPort: 80
    httpsPort: 443
    priority: 1
    weight: 1000
    enabledState: 'Enabled'
    enforceCertificateNameCheck: true
  }
}

resource scoringRoute 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-02-01' = {
  parent: scoringEp
  name: 'route-scoring'
  properties: {
    originGroup: { id: scoringOg.id }
    supportedProtocols: [ 'Https' ]
    patternsToMatch: [ '/*' ]
    forwardingProtocol: 'HttpsOnly'
    linkToDefaultDomain: 'Enabled'
    httpsRedirect: 'Enabled'
  }
  dependsOn: [ scoringOrigin ]
}

// AFD only permits one security policy per WAF policy on a profile.
// Combine both endpoints (scoring + console) into a single security policy
// with multiple associations rather than two policies referencing the same WAF.
resource afdSecurity 'Microsoft.Cdn/profiles/securityPolicies@2024-02-01' = {
  parent: afd
  name: 'sp-heimdall'
  properties: {
    parameters: {
      type: 'WebApplicationFirewall'
      wafPolicy: { id: waf.id }
      associations: [
        {
          domains: [ { id: scoringEp.id } ]
          patternsToMatch: [ '/*' ]
        }
        {
          domains: [ { id: consoleEp.id } ]
          patternsToMatch: [ '/*' ]
        }
      ]
    }
  }
  dependsOn: [ consoleEp ]
}

// ---------- Agentic console endpoint ----------
resource consoleEp 'Microsoft.Cdn/profiles/afdEndpoints@2024-02-01' = {
  parent: afd
  name: 'console-${env}'
  location: 'global'
  tags: tags
  properties: { enabledState: 'Enabled' }
}

resource consoleOg 'Microsoft.Cdn/profiles/originGroups@2024-02-01' = {
  parent: afd
  name: 'og-console'
  properties: {
    loadBalancingSettings: {
      sampleSize: 4
      successfulSamplesRequired: 3
      additionalLatencyInMilliseconds: 50
    }
    healthProbeSettings: {
      probePath: '/'
      probeRequestType: 'GET'
      probeProtocol: 'Https'
      probeIntervalInSeconds: 60
    }
  }
}

resource consoleOrigin 'Microsoft.Cdn/profiles/originGroups/origins@2024-02-01' = {
  parent: consoleOg
  name: 'console-origin'
  properties: {
    hostName: consoleOriginHost
    originHostHeader: consoleOriginHost
    httpPort: 80
    httpsPort: 443
    priority: 1
    weight: 1000
    enabledState: 'Enabled'
    enforceCertificateNameCheck: true
  }
}

resource consoleRoute 'Microsoft.Cdn/profiles/afdEndpoints/routes@2024-02-01' = {
  parent: consoleEp
  name: 'route-console'
  properties: {
    originGroup: { id: consoleOg.id }
    supportedProtocols: [ 'Https' ]
    patternsToMatch: [ '/*' ]
    forwardingProtocol: 'HttpsOnly'
    linkToDefaultDomain: 'Enabled'
    httpsRedirect: 'Enabled'
  }
  dependsOn: [ consoleOrigin ]
}

// (consoleSecurity merged into the unified afdSecurity policy above)

resource afdDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: afd
  name: 'diag-${profileName}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
  }
}

output afdProfileId string = afd.id
output afdProfileName string = afd.name
output scoringEndpointHost string = scoringEp.properties.hostName
output consoleEndpointHost string = consoleEp.properties.hostName
output wafPolicyId string = waf.id
