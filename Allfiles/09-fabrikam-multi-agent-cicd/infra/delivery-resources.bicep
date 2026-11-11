param environmentName string
param location string
param suffix string
param githubPrincipalId string
param bootstrapImage string
param modelName string
param modelVersion string
param modelDeploymentName string

var registryName = 'acr${suffix}${take(uniqueString(resourceGroup().id), 8)}'
var foundryName = 'aif${suffix}${take(uniqueString(resourceGroup().id), 8)}'
var foundryProjectName = 'fabrikam-${take(environmentName, 24)}'
var dashboardName = 'fabrikam-release-${take(environmentName, 12)}'
var acrPullRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var acrPushRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8311e382-0749-4cb8-b61a-304f252e45ec')
var foundryUserRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${take(environmentName, 18)}-${suffix}'
  location: location
  properties: {
    retentionInDays: 30
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
    sku: { name: 'PerGB2018' }
  }
}

resource foundry 'Microsoft.CognitiveServices/accounts@2026-05-01' = {
  name: foundryName
  location: location
  identity: { type: 'SystemAssigned' }
  kind: 'AIServices'
  sku: { name: 'S0' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: foundryName
    publicNetworkAccess: 'Enabled'
    networkAcls: { defaultAction: 'Allow' }
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2026-05-01' = {
  parent: foundry
  name: foundryProjectName
  location: location
  identity: { type: 'SystemAssigned' }
  // Serialize child writes on the Foundry account; concurrent project and deployment PUTs return RequestConflict.
  dependsOn: [ modelDeployment ]
  properties: {
    displayName: 'Fabrikam agent review ${environmentName}'
    description: 'Foundry hosted-agent CI/CD training project.'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2026-05-01' = {
  parent: foundry
  name: modelDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource containerEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${take(environmentName, 18)}-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
  }
}

resource dashboard 'Microsoft.App/containerApps@2024-03-01' = {
  name: dashboardName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerEnvironment.id
    configuration: {
      activeRevisionsMode: 'Multiple'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'dashboard'
          image: bootstrapImage
          env: [
            { name: 'RELEASE_SET_ID', value: 'bootstrap' }
            { name: 'ORCHESTRATOR_AGENT_NAME', value: 'not-deployed' }
            { name: 'ORCHESTRATOR_AGENT_VERSION', value: 'not-deployed' }
            { name: 'ORCHESTRATOR_RESPONSES_ENDPOINT', value: 'https://example.invalid' }
          ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

resource dashboardPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, dashboard.id, acrPullRole)
  scope: registry
  properties: {
    principalId: dashboard.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRole
  }
}

resource dashboardFoundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryProject.id, dashboard.id, foundryUserRole)
  scope: foundryProject
  properties: {
    principalId: dashboard.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: foundryUserRole
  }
}

resource githubPushRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(githubPrincipalId)) {
  name: guid(registry.id, githubPrincipalId, acrPushRole)
  scope: registry
  properties: {
    principalId: githubPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPushRole
  }
}

resource githubFoundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(githubPrincipalId)) {
  name: guid(foundryProject.id, githubPrincipalId, foundryUserRole)
  scope: foundryProject
  properties: {
    principalId: githubPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: foundryUserRole
  }
}

output registryName string = registry.name
output foundryAccountName string = foundry.name
output registryEndpoint string = registry.properties.loginServer
output foundryProjectId string = foundryProject.id
output foundryProjectName string = foundryProject.name
output foundryProjectEndpoint string = 'https://${foundry.name}.services.ai.azure.com/api/projects/${foundryProject.name}'
output dashboardAppName string = dashboard.name
output dashboardEndpoint string = 'https://${dashboard.properties.configuration.ingress.fqdn}'
