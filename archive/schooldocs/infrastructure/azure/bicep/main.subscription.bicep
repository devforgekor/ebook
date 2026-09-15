targetScope = 'subscription'

param location string
param schoolNameToken string
param niceCode string
param schoolLevel string
param envShort string
param deployNum string
param resourceGroupName string
param sharedResourceGroupName string
param sharedCosmosAccountName string
param sharedEnvironmentName string
param superAdminObjectId string
param adminGroupObjectId string
param superAdminGroupId string
param subAdminGroupId string
param openaiResourceGroupName string = ''
param openaiAccountName string = ''
param existingCosmosAccountId string = ''
param existingEnvironmentId string = ''
param configureRuntimeSecrets bool = false
param containerPort int = 80
param probePath string = '/'
param minReplicas int = (envShort == 't') ? 0 : 0
param maxReplicas int = (envShort == 't') ? 1 : 2
param storageSku string = (envShort == 't') ? 'Standard_LRS' : 'Standard_LRS'
param enableIpRestriction bool = false
param allowedCidrs array = []
param corsAllowedOrigins array = []

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
}

resource openaiRg 'Microsoft.Resources/resourceGroups@2024-03-01' = if (!empty(openaiResourceGroupName) && openaiResourceGroupName != resourceGroupName) {
  name: openaiResourceGroupName
  location: location
}

module appDeployment 'main.bicep' = {
  name: 'app-deployment-${deployNum}'
  scope: rg
  dependsOn: [
    openaiRg
  ]
  params: {
    location: location
    schoolNameToken: schoolNameToken
    niceCode: niceCode
    schoolLevel: schoolLevel
    envShort: envShort
    deployNum: deployNum
    sharedResourceGroupName: sharedResourceGroupName
    sharedCosmosAccountName: sharedCosmosAccountName
    sharedEnvironmentName: sharedEnvironmentName
    superAdminObjectId: superAdminObjectId
    adminGroupObjectId: adminGroupObjectId
    superAdminGroupId: superAdminGroupId
    subAdminGroupId: subAdminGroupId
    openaiResourceGroupName: openaiResourceGroupName
    openaiAccountName: openaiAccountName
    existingCosmosAccountId: existingCosmosAccountId
    existingEnvironmentId: existingEnvironmentId
    configureRuntimeSecrets: configureRuntimeSecrets
    containerPort: containerPort
    probePath: probePath
    minReplicas: minReplicas
    maxReplicas: maxReplicas
    storageSku: storageSku
    enableIpRestriction: enableIpRestriction
    allowedCidrs: allowedCidrs
    corsAllowedOrigins: corsAllowedOrigins
  }
}

output containerAppFqdn string = appDeployment.outputs.containerAppFqdn
output functionAppUrl string = appDeployment.outputs.functionAppUrl
output keyVaultName string = appDeployment.outputs.keyVaultName
output keyVaultUri string = appDeployment.outputs.keyVaultUri
output containerAppName string = appDeployment.outputs.containerAppName
output containerEnvironmentName string = appDeployment.outputs.containerEnvironmentName
output containerRegistryName string = appDeployment.outputs.containerRegistryName
output userAssignedIdentityResourceId string = appDeployment.outputs.userAssignedIdentityResourceId
output requiredManualSecretNames array = appDeployment.outputs.requiredManualSecretNames
output autoManagedSecretNames array = appDeployment.outputs.autoManagedSecretNames
output functionAppName string = appDeployment.outputs.functionAppName

