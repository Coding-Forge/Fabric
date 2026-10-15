metadata description = 'Grants "Key Vault Secrets User" on an EXISTING RBAC-enabled Key Vault. Does not change the vault authorization model.'
param keyVaultName string
param principalId string

// Built-in role: Key Vault Secrets User
var roleDefinitionId = '4633458b-17de-408a-b874-0e5e66a3c8f5'

resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' existing = {
  name: keyVaultName
}

resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, principalId, roleDefinitionId)
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
  }
}
