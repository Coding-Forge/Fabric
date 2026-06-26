# Enterprise Deployment Best Practices

This guide describes the recommended enterprise deployment model for the Fabric / Power BI Monitor across supported cloud environments:

- `Commercial`
- `Gcc`
- `GccHigh`
- `Dod`

The solution should be treated as a governed data collection service. Use Azure Functions for scheduled API collection, ADLS Gen2 or Blob Storage for durable raw output, and Synapse or SQL-based processing for enterprise reporting and curation.

## Recommended Enterprise Architecture

Use this architecture for all cloud environments:

1. **Azure Function App**
   - Runs the monitor modules on timer triggers.
   - Uses managed identity or Key Vault-backed service principal secrets.
   - Writes raw output to storage.

2. **ADLS Gen2 / Blob Storage**
   - Stores raw monitor output by module and run date.
   - Uses lifecycle policies and immutable retention if required.
   - Is the system of record for collected API responses.

3. **Azure Synapse Pipelines / Notebooks**
   - Reads raw output from storage.
   - Curates, validates, joins, and reshapes data.
   - Loads Synapse Dedicated SQL Pool or other approved reporting stores when needed.

4. **Power BI / Fabric Reports**
   - Reads curated data or generated PBIP semantic models.
   - Uses separate reports for Catalog and Activity/Audit workloads.

Do not use Synapse Spark notebooks as the primary runtime for simple REST API collection unless the customer has standardized on Synapse pipelines for all orchestration. Azure Functions are lighter, cheaper, easier to schedule, and better suited for daily/monthly API extraction.

## Recommended Schedules

| Workload | Recommended runtime | Recommended schedule | Notes |
|---|---|---:|---|
| Activity | Azure Function timer | Daily | Collects audit/activity data incrementally. |
| Catalog | Azure Function timer | Monthly | Captures slower-changing workspace, model, report, and capacity metadata. |
| Gateway / Refresh history | Azure Function timer | Daily or weekly | Depends on operational monitoring needs. |
| Synapse curation | Synapse pipeline/notebook | After collection | Reads raw storage output and loads curated tables. |
| PBIP/report refresh | Power BI scheduled refresh or pipeline | After curation | Keep reporting separate from collection. |

## Cloud Environment Matrix

| Environment | `CLOUD_ENVIRONMENT` | Collection runtime | Storage endpoint | Fabric REST / OneLake support |
|---|---|---|---|---|
| Commercial | `Commercial` | Azure Functions or Container Apps | `blob.core.windows.net`, `dfs.core.windows.net` | Enabled |
| GCC | `Gcc` | Azure Functions in supported cloud boundary | `blob.core.usgovcloudapi.net`, `dfs.core.usgovcloudapi.net` when using Azure Gov storage | Disabled until Fabric Gov public preview |
| GCC High | `GccHigh` | Azure Functions in Azure Government | `blob.core.usgovcloudapi.net`, `dfs.core.usgovcloudapi.net` | Disabled until Fabric Gov public preview |
| DoD | `Dod` | Azure Functions in Azure Government / DoD-approved boundary | `blob.core.usgovcloudapi.net`, `dfs.core.usgovcloudapi.net` | Disabled until Fabric Gov public preview |

The solution automatically skips Fabric REST API modules outside `Commercial`:

```text
Domains,FabricItems,Roles,Tenant,Workspaces
```

Use classic Power BI REST modules in government clouds:

```text
Activity,Apps,Capacity,CapacityMetrics,Catalog,Gateway,Graph,Refreshables,RefreshHistory
```

## Commercial Deployment

Use the full solution capability in Commercial.

### Recommended configuration

```text
CLOUD_ENVIRONMENT=Commercial
APPLICATION_MODULES=Activity,Apps,Capacity,CapacityMetrics,Catalog,Domains,FabricItems,Gateway,Graph,Refreshables,RefreshHistory,Roles,Tenant,Workspaces
```

### Recommended storage

Use ADLS Gen2 or Blob Storage:

```text
STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
STORAGE_ACCOUNT_CONTAINER_NAME=<container>
STORAGE_ACCOUNT_CONTAINER_ROOT_PATH=fabric-monitor
```

Use Fabric Lakehouse / OneLake only when the customer wants native Fabric storage and governance:

```text
LAKEHOUSE_NAME=<lakehouse-name>
WORKSPACE_NAME=<workspace-name>
```

### Best practices

1. Use Azure Functions for scheduled collection.
2. Use Key Vault references for `CLIENT_SECRET`.
3. Use a dedicated service principal for monitor collection.
4. Store raw API output before transformation.
5. Use Synapse, Fabric Data Engineering, or Data Factory for downstream processing.
6. Separate Activity and Catalog outputs into different folders or containers.

## GCC Deployment

GCC is not the same as GCC High. Validate customer boundary requirements before deployment. If the customer requires Azure Government-only infrastructure, deploy runtime and storage in Azure Government and use the government storage suffixes.

### Recommended configuration

```text
CLOUD_ENVIRONMENT=Gcc
APPLICATION_MODULES=Activity,Apps,Capacity,CapacityMetrics,Catalog,Gateway,Graph,Refreshables,RefreshHistory
```

### Best practices

1. Avoid Fabric REST API modules until Fabric Gov is public preview.
2. Use Blob/ADLS storage in the approved customer boundary.
3. Validate Power BI API endpoint allowlists with the customer's network team.
4. Keep secrets in Key Vault.
5. Use Synapse notebooks only for downstream processing.

## GCC High Deployment

For GCC High, deploy the collection runtime and storage in Azure Government. Use government authority, Power BI, Graph, and storage endpoints through `CLOUD_ENVIRONMENT=GccHigh`.

### Recommended configuration

```text
CLOUD_ENVIRONMENT=GccHigh
APPLICATION_MODULES=Activity,Apps,Capacity,CapacityMetrics,Catalog,Gateway,Graph,Refreshables,RefreshHistory
STORAGE_ACCOUNT_URL=https://<account>.blob.core.usgovcloudapi.net
STORAGE_ACCOUNT_CONTAINER_NAME=<container>
STORAGE_ACCOUNT_CONTAINER_ROOT_PATH=fabric-monitor
```

### Recommended ADLS Gen2 path shape

```text
abfss://<container>@<account>.dfs.core.usgovcloudapi.net/fabric-monitor/<module>/<run-date>/
```

### Best practices

1. Deploy Azure Function App, Storage Account, Key Vault, and Synapse in Azure Government.
2. Use `login.microsoftonline.us` through the `GccHigh` cloud profile.
3. Use `api.high.powerbigov.us` through the `GccHigh` cloud profile.
4. Use `graph.microsoft.us` through the `GccHigh` cloud profile.
5. Use private endpoints where required by the customer security baseline.
6. Disable OneLake/Fabric Lakehouse output.
7. Run Synapse notebooks in Azure Government only when processing GCC High data.
8. Load curated data into Synapse Dedicated SQL Pool only after raw collection succeeds.

## DoD Deployment

DoD deployments should follow the customer's accredited boundary and approval process. Treat this as the most restrictive profile.

### Recommended configuration

```text
CLOUD_ENVIRONMENT=Dod
APPLICATION_MODULES=Activity,Apps,Capacity,CapacityMetrics,Catalog,Gateway,Graph,Refreshables,RefreshHistory
STORAGE_ACCOUNT_URL=https://<account>.blob.core.usgovcloudapi.net
STORAGE_ACCOUNT_CONTAINER_NAME=<container>
STORAGE_ACCOUNT_CONTAINER_ROOT_PATH=fabric-monitor
```

### Best practices

1. Validate all endpoints against the customer's DoD allowlist.
2. Use approved Azure Government / DoD regions and services only.
3. Use private endpoints and restricted outbound networking where required.
4. Keep all secrets in Key Vault or approved secret-management services.
5. Do not use Fabric REST API or OneLake output until explicitly supported in DoD.
6. Prefer file-based raw collection plus separate curated load pipelines.

## Identity and Permissions

Use a dedicated service principal or managed identity pattern approved by the customer.

Minimum enterprise recommendations:

1. Create a dedicated app registration for monitor collection.
2. Grant only the required Power BI Admin API permissions.
3. Enable required Power BI tenant settings for service principal API access.
4. Use security groups to scope API access where supported.
5. Store client secrets in Key Vault.
6. Rotate secrets on a defined schedule.
7. Log all collection runs and failures to Application Insights.

For storage:

1. Grant the Function App identity `Storage Blob Data Contributor` if it writes output.
2. Grant Synapse identities `Storage Blob Data Reader` or `Storage Blob Data Contributor` depending on pipeline needs.
3. Configure filesystem ACLs when hierarchical namespace is enabled.

## Storage Layout

Use a consistent partitioned folder layout:

```text
fabric-monitor/
  raw/
    activity/yyyy=2026/mm=06/dd=25/
    catalog/yyyy=2026/mm=06/
    refresh-history/yyyy=2026/mm=06/dd=25/
  curated/
    activity/
    catalog/
  logs/
```

Keep raw data immutable where possible. Curated data can be overwritten or merged by downstream processing jobs.

## Azure Functions Deployment Pattern

Use separate timer triggers for independent workloads:

| Function | Modules | Example cadence |
|---|---|---|
| `CollectActivityDaily` | `Activity` | Daily |
| `CollectCatalogMonthly` | `Catalog` | Monthly |
| `CollectOperationalDaily` | `Gateway,Refreshables,RefreshHistory` | Daily |

Each function should call the same codebase with a module-specific `APPLICATION_MODULES` value.

Example app settings:

```text
CLOUD_ENVIRONMENT=GccHigh
APPLICATION_MODULES=Activity
STORAGE_ACCOUNT_URL=https://<account>.blob.core.usgovcloudapi.net
STORAGE_ACCOUNT_CONTAINER_NAME=<container>
STORAGE_ACCOUNT_CONTAINER_ROOT_PATH=fabric-monitor/raw/activity
```

For monthly catalog collection:

```text
CLOUD_ENVIRONMENT=GccHigh
APPLICATION_MODULES=Catalog
STORAGE_ACCOUNT_URL=https://<account>.blob.core.usgovcloudapi.net
STORAGE_ACCOUNT_CONTAINER_NAME=<container>
STORAGE_ACCOUNT_CONTAINER_ROOT_PATH=fabric-monitor/raw/catalog
```

## Synapse Deployment Pattern

Use Synapse after collection:

1. Read raw data from ADLS Gen2 or Blob Storage.
2. Apply schema normalization.
3. Join activity, catalog, refresh, and gateway data as needed.
4. Write curated tables to ADLS Gen2, Dedicated SQL Pool, or another approved reporting store.

Use the Synapse guide for notebook examples:

```text
docs/azure-synapse-notebooks.md
```

## Monitoring and Operations

Enterprise deployments should include:

1. Application Insights for Azure Function execution logs.
2. Storage lifecycle policies for raw and curated output.
3. Alerting for failed API calls, empty outputs, or delayed collection.
4. Run metadata with module name, cloud environment, start time, end time, status, and output path.
5. Separate dev/test/prod configuration and storage accounts.
6. Change control for module additions, cloud profile changes, and permission changes.

## Deployment Checklist

Before production:

1. Confirm the customer cloud environment and compliance boundary.
2. Select `CLOUD_ENVIRONMENT`.
3. Confirm supported modules for that environment.
4. Create app registration / service principal.
5. Configure Power BI tenant settings and API permissions.
6. Deploy Function App, Storage, Key Vault, and Application Insights.
7. Configure private endpoints/firewall allowlists if required.
8. Store secrets in Key Vault or app settings with Key Vault references.
9. Run Activity module with a one-day test window.
10. Run Catalog module once and validate output.
11. Configure Synapse curation only after raw collection is validated.
12. Configure monitoring, alerts, and retention.

