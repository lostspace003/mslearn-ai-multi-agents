targetScope = 'resourceGroup'

param environmentName string
param location string
param githubPrincipalId string = ''
param bootstrapImage string = 'mcr.microsoft.com/k8se/quickstart:latest'
param modelName string = 'gpt-5.4-mini'
param modelVersion string = '2026-03-17'
param modelDeploymentName string = 'gpt-5.4-mini'

var suffix = take(uniqueString(subscription().id, resourceGroup().id, environmentName), 8)

module deliveryResources 'delivery-resources.bicep' = {
  name: 'delivery-resources-${suffix}'
  params: {
    environmentName: environmentName
    location: location
    suffix: suffix
    githubPrincipalId: githubPrincipalId
    bootstrapImage: bootstrapImage
    modelName: modelName
    modelVersion: modelVersion
    modelDeploymentName: modelDeploymentName
  }
}

output AZURE_RESOURCE_GROUP_NAME string = resourceGroup().name
output AZURE_CONTAINER_REGISTRY_NAME string = deliveryResources.outputs.registryName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = deliveryResources.outputs.registryEndpoint
output FOUNDRY_PROJECT_ID string = deliveryResources.outputs.foundryProjectId
output FOUNDRY_PROJECT_NAME string = deliveryResources.outputs.foundryProjectName
output FOUNDRY_PROJECT_ENDPOINT string = deliveryResources.outputs.foundryProjectEndpoint
output AZURE_AI_PROJECT_ID string = deliveryResources.outputs.foundryProjectId
output AZURE_AI_PROJECT_NAME string = deliveryResources.outputs.foundryProjectName
output AZURE_AI_PROJECT_ENDPOINT string = deliveryResources.outputs.foundryProjectEndpoint
output AZURE_AI_ACCOUNT_NAME string = deliveryResources.outputs.foundryAccountName
output FOUNDRY_MODEL_NAME string = modelDeploymentName
output FOUNDRY_MODEL_VERSION string = modelVersion
output DASHBOARD_APP_NAME string = deliveryResources.outputs.dashboardAppName
output DASHBOARD_ENDPOINT string = deliveryResources.outputs.dashboardEndpoint
