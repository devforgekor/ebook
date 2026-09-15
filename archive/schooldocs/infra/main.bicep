targetScope = 'resourceGroup'

var envSuffixFull = envShort == 't' ? 'test' : 'prod'
var cosmosDatabaseName = 'CertificateSystem_${envSuffixFull}'
var cosmosContainerName = 'records'
var storageContainerName = 'record-files'

param location string = 'koreacentral'
@minLength(3)
param schoolNameToken string = 'school'
param niceCode string = 'sen'
param schoolLevel string = 'es'
param envShort string = 't'
param deployNum string = '01'

param sharedResourceGroupName string
param sharedCosmosAccountName string
param sharedEnvironmentName string

param superAdminObjectId string
param adminGroupObjectId string
param superAdminGroupId string
param subAdminGroupId string

param configureRuntimeSecrets bool = false
param containerPort int = 80
#disable-next-line no-unused-params
param probePath string = '/'
param minReplicas int = 0
param maxReplicas int = 2
param storageSku string = 'Standard_LRS'
param enableIpRestriction bool = false
param allowedCidrs array = []
param corsAllowedOrigins array = []

// Azure OpenAI 리소스 정보 (배포 시 파라미터로 전달)
param openaiResourceGroupName string = ''
param openaiAccountName string = ''
#disable-next-line no-unused-params
param existingCosmosAccountId string = ''
#disable-next-line no-unused-params
param existingEnvironmentId string = ''

var baseName = '${schoolNameToken}${niceCode}${schoolLevel}${envShort}${deployNum}'
var kvName = 'kv-${baseName}'
var storageName = 'st${baseName}'
var acrName = 'acr${baseName}'
var logWorkspaceName = 'law-${baseName}'
var appName = 'app-${baseName}'
var identityName = 'id-${baseName}'
var functionAppName = 'func-${baseName}'
var functionPlanName = 'asp-${baseName}'
var functionStorageName = 'stfunc${baseName}'

// ------------------------------------------------------------
// 기존 공유 리소스 참조
// ------------------------------------------------------------
resource sharedCosmos 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' existing = {
  name: sharedCosmosAccountName
  scope: resourceGroup(sharedResourceGroupName)
}

resource sharedEnv 'Microsoft.App/managedEnvironments@2023-05-01' existing = {
  name: sharedEnvironmentName
  scope: resourceGroup(sharedResourceGroupName)
}

resource openaiAccount 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = if (!empty(openaiAccountName)) {
  name: openaiAccountName
  scope: resourceGroup(openaiResourceGroupName)
}

// ------------------------------------------------------------
// RBAC – Super Admin Owner, Admin Group Contributor (리소스 그룹)
// ------------------------------------------------------------
resource superAdminRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, superAdminObjectId, 'Owner')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8e3af657-a8ff-443c-a75c-2fe8c4bcb635')
    principalId: superAdminObjectId
    principalType: 'User'
  }
}

resource adminGroupRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, adminGroupObjectId, 'Contributor')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
    principalId: adminGroupObjectId
    principalType: 'Group'
  }
}

// ------------------------------------------------------------
// User Assigned Identity
// ------------------------------------------------------------
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

// ------------------------------------------------------------
// Log Analytics Workspace
// ------------------------------------------------------------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    retentionInDays: 730
  }
}

// ------------------------------------------------------------
// Key Vault
// ------------------------------------------------------------
resource keyVault 'Microsoft.KeyVault/vaults@2023-02-01' = {
  name: kvName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
  }
}

// ------------------------------------------------------------
// Storage Account (메인)
// ------------------------------------------------------------
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageName
  location: location
  sku: {
    name: storageSku
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 30
    }
  }
}

resource recordFilesContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: storageContainerName
}

// 수명 주기 정책
resource managementPolicy 'Microsoft.Storage/storageAccounts/managementPolicies@2023-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'archive-policy'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: [ 'blockBlob' ]
              prefixMatch: [ '${storageContainerName}/' ]
            }
            actions: {
              baseBlob: {
                tierToCool: {
                  daysAfterModificationGreaterThan: 1095
                }
                delete: {
                  daysAfterModificationGreaterThan: 3285
                }
              }
            }
          }
        }
      ]
    }
  }
}

// ------------------------------------------------------------
// Container Registry
// ------------------------------------------------------------
resource acr 'Microsoft.ContainerRegistry/registries@2023-01-01-preview' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {}
}

// -------- [추가] Cosmos DB 모듈 호출 ----------
module cosmosDb 'cosmos/cosmos.database.bicep' = {
  name: 'cosmosDatabaseDeploy'
  scope: resourceGroup(sharedResourceGroupName)
  params: {
    sharedCosmosAccountName: sharedCosmosAccountName
    cosmosDatabaseName: cosmosDatabaseName
    cosmosContainerName: cosmosContainerName
  }
}

// ------------------------------------------------------------
// Functions 리소스
// ------------------------------------------------------------
resource functionStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: functionStorageName
  location: location
  sku: {
    name: storageSku
  }
  kind: 'StorageV2'
}

resource functionPlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: functionPlanName
  location: location
  kind: 'linux'
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2022-09-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux' 
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${appIdentity.id}': {}
    }
  }
  properties: {
    serverFarmId: functionPlan.id
    siteConfig: {
      linuxFxVersion: 'NODE|20-lts'
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${functionStorage.name};AccountKey=${functionStorage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        }
        {
           name: 'FUNCTIONS_WORKER_RUNTIME'
           value: 'node'
        }
        { name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        { name: 'WEBSITE_NODE_DEFAULT_VERSION'
          value: '~20'
        }
        { name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
        { name: 'KEYVAULT_URI'
          value: keyVault.properties.vaultUri
        }
        { name: 'COSMOS_DATABASE'
          value: cosmosDatabaseName
        }
        { name: 'COSMOS_CONTAINER'
          value: cosmosContainerName
        }
        { name: 'COSMOS_ENDPOINT'
          value: sharedCosmos.properties.documentEndpoint
        }
        { name: 'STORAGE_ACCOUNT_NAME'
          value: storageAccount.name
        }
        { name: 'STORAGE_CONTAINER_NAME'
          value: storageContainerName
        }
        { name: 'SUPER_ADMIN_GROUP_ID'
          value: superAdminGroupId
        }
        { name: 'ADMIN_GROUP_ID'
          value: adminGroupObjectId
        }
        { name: 'SUB_ADMIN_GROUP_ID'
          value: subAdminGroupId
        }
      ]
      keyVaultReferenceIdentity: appIdentity.id
    }
  }
}

// ------------------------------------------------------------
// RBAC for Identity (Cross-RG)
// ------------------------------------------------------------

// OpenAI RBAC (OpenAI RG)
module openaiRbac 'rbac/rbac.roleAssignment.bicep' = if (!empty(openaiAccountName)) {
  name: 'openaiRbac'
  scope: resourceGroup(openaiResourceGroupName)
  params: {
    principalId: appIdentity.properties.principalId
    roleDefinitionId: '/subscriptions/${subscription().subscriptionId}/providers/Microsoft.Authorization/roleDefinitions/5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
  }
}

// ------------------------------------------------------------
// Key Vault Secrets (자동 생성)
// ------------------------------------------------------------
resource storageConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'connection-string-storage'
  properties: {
    value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
  }
}

resource cosmosConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-02-01' = {
  parent: keyVault
  name: 'connection-string-database'
  properties: {
    value: sharedCosmos.listConnectionStrings().connectionStrings[0].connectionString
  }
}

// ------------------------------------------------------------
// Container App 환경 변수 및 Secret 구성 (조건부 처리)
// ------------------------------------------------------------
var manualSecretNames = [
  'azure-openai-endpoint'
  'api-key-sms'
  'api-secret-sms'
  'sms-sender-phone'
  'encryption-key-aes'
  'encryption-key-hmac'
]

var containerSecrets = configureRuntimeSecrets
  ? [
      {
        name: 'azure-openai-endpoint'
        keyVaultUrl: '${keyVault.properties.vaultUri}secrets/azure-openai-endpoint'
        identity: appIdentity.id
      }
      {
        name: 'api-key-sms'
        keyVaultUrl: '${keyVault.properties.vaultUri}secrets/api-key-sms'
        identity: appIdentity.id
      }
      {
        name: 'api-secret-sms'
        keyVaultUrl: '${keyVault.properties.vaultUri}secrets/api-secret-sms'
        identity: appIdentity.id
      }
      {
        name: 'sms-sender-phone'
        keyVaultUrl: '${keyVault.properties.vaultUri}secrets/sms-sender-phone'
        identity: appIdentity.id
      }
      {
        name: 'encryption-key-aes'
        keyVaultUrl: '${keyVault.properties.vaultUri}secrets/encryption-key-aes'
        identity: appIdentity.id
      }
      {
        name: 'encryption-key-hmac'
        keyVaultUrl: '${keyVault.properties.vaultUri}secrets/encryption-key-hmac'
        identity: appIdentity.id
      }
    ]
  : []

var containerEnv = concat(
  [
    {
      name: 'COSMOS_DATABASE'
      value: cosmosDatabaseName
    }
    {
      name: 'COSMOS_CONTAINER'
      value: cosmosContainerName
    }
    {
      name: 'COSMOS_ENDPOINT'
      value: sharedCosmos.properties.documentEndpoint
    }
    {
      name: 'STORAGE_ACCOUNT_NAME'
      value: storageAccount.name
    }
    {
      name: 'STORAGE_CONTAINER_NAME'
      value: storageContainerName
    }
    {
      name: 'KEYVAULT_URI'
      value: keyVault.properties.vaultUri
    }
    {
      name: 'WEBSITES_INCLUDE_CLOUD_CERTS'
      value: 'true'
    }
    {
      name: 'SUPER_ADMIN_GROUP_ID'
      value: superAdminGroupId
    }
    {
      name: 'ADMIN_GROUP_ID'
      value: adminGroupObjectId
    }
    {
      name: 'SUB_ADMIN_GROUP_ID'
      value: subAdminGroupId
    }
  ],
  configureRuntimeSecrets
    ? [
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          secretRef: 'azure-openai-endpoint'
        }
      ]
    : []
)

var conditionalEnv = configureRuntimeSecrets
  ? [
      {
        name: 'ENCRYPTION_KEY_AES'
        secretRef: 'encryption-key-aes'
      }
      {
        name: 'ENCRYPTION_KEY_HMAC'
        secretRef: 'encryption-key-hmac'
      }
      {
        name: 'SMS_API_KEY'
        secretRef: 'api-key-sms'
      }
      {
        name: 'SMS_API_SECRET'
        secretRef: 'api-secret-sms'
      }
      {
        name: 'SMS_SENDER_PHONE'
        secretRef: 'sms-sender-phone'
      }
    ]
  : []

var finalContainerEnv = concat(containerEnv, conditionalEnv)

// -------------------------------
// IP 제한 리스트 (for 표현식 결과)
// -------------------------------
var ipSecurityRestrictionsList = [for (cidr, i) in allowedCidrs: {
  name: 'AllowCIDR${i}'
  ipAddressRange: cidr
  action: 'Allow'
}]

// Ingress 구성
var ingressConfig = {
  external: true
  targetPort: containerPort
  ipSecurityRestrictions: enableIpRestriction ? ipSecurityRestrictionsList : null
  corsPolicy: !empty(corsAllowedOrigins) ? {
    allowedOrigins: corsAllowedOrigins
    allowedMethods: [ 'GET', 'POST', 'OPTIONS' ]
    allowedHeaders: [ '*' ]
  } : null
}

// ------------------------------------------------------------
// Container App
// ------------------------------------------------------------
resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${appIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: sharedEnv.id
    configuration: {
      ingress: ingressConfig
      registries: []
      secrets: containerSecrets
    }
    template: {
      containers: [
        {
          name: appName
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          env: finalContainerEnv
          probes: []
          resources: {
            cpu: 1
            memory: '2Gi'
          }
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    storageConnectionSecret
    cosmosConnectionSecret
  ]
}

// ------------------------------------------------------------
// Outputs
// ------------------------------------------------------------
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output containerAppName string = containerApp.name
output containerEnvironmentName string = sharedEnv.name
output containerRegistryName string = acr.name
output userAssignedIdentityResourceId string = appIdentity.id
output requiredManualSecretNames array = manualSecretNames
output autoManagedSecretNames array = [
  'connection-string-storage'
  'connection-string-database'
]
output functionAppName string = functionApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'

output resourceIdsForRbac object = {
  keyVaultId: keyVault.id
  storageAccountId: storageAccount.id
  cosmosAccountId: sharedCosmos.id
  openaiAccountId: openaiAccount.id
  containerAppId: containerApp.id
  functionAppId: functionApp.id
  appIdentityId: appIdentity.id
}
