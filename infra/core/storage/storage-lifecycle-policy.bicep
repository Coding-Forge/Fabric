metadata description = 'Optional retention: deletes monitor output blobs older than N days under an allowlist of module folders.'
// Notes:
// - Lifecycle rules use the blob last-modified time and run asynchronously (typically within ~24h, not immediately).
// - Only base blobs are deleted; versions and snapshots are NOT handled by this rule.
// - A storage account has exactly ONE management policy ('default'). Deploying this REPLACES any existing policy,
//   which is why it is disabled by default in main.bicep.
// - Prefixes are always '<container>/<root>/<module>/', so state.yaml (at the root path) and the
//   azure-webjobs* containers are never matched.
param storageAccountName string
param containerName string
@description('Root path inside the container (no leading/trailing slash). May be empty.')
param rootPath string = ''
@minValue(1)
param retentionDays int
@minLength(1)
@description('Allowlist of module folder names (e.g. activity) to expire. Must not be empty.')
param modules array

var root = trim(rootPath)
var normalizedRoot = empty(root) ? '' : '${root}/'
var prefixes = [for m in modules: '${containerName}/${normalizedRoot}${trim(m)}/']

resource storage 'Microsoft.Storage/storageAccounts@2022-05-01' existing = {
  name: storageAccountName
}

resource policy 'Microsoft.Storage/storageAccounts/managementPolicies@2022-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'monitor-output-retention'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: [ 'blockBlob' ]
              prefixMatch: prefixes
            }
            actions: {
              baseBlob: {
                delete: { daysAfterModificationGreaterThan: retentionDays }
              }
            }
          }
        }
      ]
    }
  }
}

output prefixMatch array = prefixes
