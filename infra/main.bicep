targetScope = 'subscription'

// The main bicep module to provision Azure resources.
// For a more complete walkthrough to understand how this file works with azd,
// see https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/make-azd-compatible?pivots=azd-create

@minLength(1)
@maxLength(64)
@description('Name of the the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

// Optional parameters to override the default azd resource naming conventions.
// Add the following to main.parameters.json to provide values:
// "resourceGroupName": {
//      "value": "myGroupName"
// }
param resourceGroupName string = ''
param appServicePlanName string = ''
param backendFunctionName string = ''

param acrName string = ''
param acrImageName string = ''
//param acrImageTag string = ''


var abbrs = loadJsonContent('./abbreviations.json')

// tags that should be applied to all resources.
var tags = {
  // Tag all resources with the environment name.
  'azd-env-name': environmentName
}

// Generate a unique token to be used in naming resources.
// Remove linter suppression after using.
#disable-next-line no-unused-vars
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// Name of the service defined in azure.yaml
// A tag named azd-service-name with this value should be applied to the service host resource, such as:
//   Microsoft.Web/sites for appservice, function
// Example usage:
//   tags: union(tags, { 'azd-service-name': apiServiceName })
#disable-next-line no-unused-vars
var apiServiceName = 'python-api'

param storageAccountName string = ''
param storageResourceGroupName string = ''
param storageResourceGroupLocation string = location
param storageContainerName string = 'content'

// Optional: CLIENT_SECRET from an EXISTING Key Vault secret via Key Vault reference.
// NOTE (first deploy): the Function App identity is granted vault access by a role assignment created in this same
// deployment. RBAC propagation can take several minutes, so the CLIENT_SECRET reference may show as unresolved
// (red X under Configuration > Environment variables) after the first deploy. Restart the Function App once the
// role assignment has propagated; later deploys are not affected.
@description('Versionless secret URI, e.g. https://<vault>.vault.azure.net/secrets/<name>. Empty = feature off.')
param clientSecretKeyVaultSecretUri string = ''
@description('Existing Key Vault name (required when assignKeyVaultAccess is true).')
param keyVaultName string = ''
@description('Resource group of the existing Key Vault (defaults to the main resource group).')
param keyVaultResourceGroupName string = ''
@description('Opt-in: grant the Function App identity "Key Vault Secrets User" on the existing vault. The vault MUST use RBAC authorization; its authorization model is not changed. Otherwise grant access yourself (e.g. access policy).')
param assignKeyVaultAccess bool = false

// Optional: blob retention (OFF by default). Replaces any existing management policy on the account.
param enableRetention bool = false
@minValue(1)
param retentionDays int = 90
@description('Root path inside the container (STORAGE_ACCOUNT_CONTAINER_ROOT_PATH), no leading/trailing slash.')
param storageRetentionRootPath string = ''
@description('Allowlist of module folders to expire (e.g. ["activity"]). Required when enableRetention is true.')
param retentionModules array = []

var useKeyVaultSecret = !empty(clientSecretKeyVaultSecretUri)

// Deploy-time validation. Bicep has no assert/fail, and param values are unknown at compile time, so each
// "...Validated" variable below evaluates to its input when valid and otherwise indexes past the end of a one-element
// array (index = a param-derived value >= 1, so Bicep cannot reject it at compile time), which makes ARM fail the deployment; the variable name appears in the error. They must be consumed
// (see keyVaultAccess and storageRetention) or Bicep drops them.
var keyVaultAccessRequiresKeyVaultName_AndClientSecretKeyVaultSecretUri = assignKeyVaultAccess && (empty(keyVaultName) || !useKeyVaultSecret)
var keyVaultNameValidated = !keyVaultAccessRequiresKeyVaultName_AndClientSecretKeyVaultSecretUri ? keyVaultName : [ keyVaultName ][length(keyVaultName) + 1]

var validRetentionModules = filter(retentionModules, m => !empty(trim(string(m))) && !contains(string(m), '/') && !contains(string(m), '\\'))
var retentionRequiresNonEmptyRetentionModulesWithoutSlashes = enableRetention && (empty(retentionModules) || length(validRetentionModules) != length(retentionModules))
var retentionModulesValidated = !retentionRequiresNonEmptyRetentionModulesWithoutSlashes ? retentionModules : [ retentionModules ][length(retentionModules) + 1]

// Organize resources in a resource group

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

resource storageResourceGroup 'Microsoft.Resources/resourceGroups@2021-04-01' existing = if (!empty(storageResourceGroupName)) {
  name: !empty(storageResourceGroupName) ? storageResourceGroupName : rg.name
}

module acr 'core/host/container-registry.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    name: !empty(acrName) ? acrName : '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
    sku: {
      name: 'standard'
    }
    publicNetworkAccess: 'Enabled'
    anonymousPullEnabled: true
  }
}

// Create an App Service Plan to group applications under the same payment plan and SKU
module appServicePlan 'core/host/appserviceplan.bicep' = {
  name: appServicePlanName
  scope: rg
  params: {
    name: !empty(appServicePlanName) ? appServicePlanName : '${abbrs.webServerFarms}${resourceToken}'
    location: location
    tags: tags
    sku: {
      name: 'B1'
      capacity: 1
    }
    kind: 'linux'
  }
}

module functionApp 'core/host/functions.bicep' = {
  name: backendFunctionName
  scope: rg
  params: {
    name: !empty(backendFunctionName) ? backendFunctionName : '${abbrs.webSitesAppService}backend-${resourceToken}'
    location: location
    tags: tags
    appServicePlanId: appServicePlan.outputs.id
    managedIdentity: useKeyVaultSecret
    appSettings: union({
      CONTAINER_IMAGE_NAME: acrImageName
      REGISTRY_LOGIN_SERVER: acr.outputs.loginServer
    }, useKeyVaultSecret ? {
      CLIENT_SECRET: '@Microsoft.KeyVault(SecretUri=${clientSecretKeyVaultSecretUri})'
    } : {})
    runtimeName: 'python'
    runtimeVersion: '3.10'
    storageAccountName: storage.outputs.name
  }
}

module storage 'core/storage/storage-account.bicep' = {
  name: 'storage'
  scope: storageResourceGroup
  params: {
    name: !empty(storageAccountName) ? storageAccountName : '${abbrs.storageStorageAccounts}${resourceToken}'
    location: storageResourceGroupLocation
    tags: tags
    publicNetworkAccess: 'Enabled'
    sku: {
      name: 'Standard_ZRS'
    }
    deleteRetentionPolicy: {
      enabled: true
      days: 2
    }
    containers: [
      {
        name: storageContainerName
        publicAccess: 'None'
      }
    ]
  }
}

module keyVaultAccess 'core/security/keyvault-secrets-user.bicep' = if (assignKeyVaultAccess) {
  name: 'keyvault-secrets-user'
  scope: resourceGroup(!empty(keyVaultResourceGroupName) ? keyVaultResourceGroupName : rg.name)
  params: {
    keyVaultName: keyVaultNameValidated
    principalId: functionApp.outputs.identityPrincipalId
  }
}

module storageRetention 'core/storage/storage-lifecycle-policy.bicep' = if (enableRetention) {
  name: 'storage-retention'
  scope: storageResourceGroup
  params: {
    storageAccountName: storage.outputs.name
    containerName: storageContainerName
    rootPath: storageRetentionRootPath
    retentionDays: retentionDays
    modules: retentionModulesValidated
  }
}

// The Azure Function Docker image

// Add resources to be provisioned below.
// A full example that leverages azd bicep modules can be seen in the todo-python-mongo template:
// https://github.com/Azure-Samples/todo-python-mongo/tree/main/infra

// Add outputs from the deployment here, if needed.
//
// This allows the outputs to be referenced by other bicep deployments in the deployment pipeline,
// or by the local machine as a way to reference created resources in Azure for local development.
// Secrets should not be added here.
//
// Outputs are automatically saved in the local azd environment .env file.
// To see these outputs, run `azd env get-values`,  or `azd env get-values --output json` for json output.
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output BACKEND_URI string = functionApp.outputs.uri
output AZURE_STORAGE_ACCOUNT string = storage.outputs.name
output AZURE_CONTAINER_REGISTRY string = acr.outputs.name

