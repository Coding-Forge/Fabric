# Azure Government Synapse Runbook

This runbook describes how to run Fabric Monitor from Azure Synapse notebooks in Azure Government and publish PBIP reports against the storage output.

## Target architecture

Use this pattern for GCC High or DoD customers:

1. **Azure Synapse workspace in Azure Government**
   - Runs Spark notebooks on a schedule.
   - Uses Git integration or an uploaded package copy of this monitor solution.
2. **Azure Government Storage / ADLS Gen2**
   - Stores raw JSON monitor output under a stable root path.
   - Recommended endpoint shape: `https://<storage-account>.blob.core.usgovcloudapi.net`.
3. **Service principal**
   - Authenticates to Power BI / Microsoft Graph APIs.
   - Also authenticates to Storage through `DefaultAzureCredential` when using URL-based storage auth.
4. **PBIP reports**
   - Use the `pbip-synapse-gov` copies.
   - Read from ADLS Gen2 with parameterized `AzureStorage.DataLake` queries.

## Azure resources to create

Create or identify these resources in the customer Azure Government tenant:

| Resource | Purpose |
|---|---|
| Synapse workspace | Notebook authoring, Spark execution, and pipeline scheduling |
| Spark pool | Runtime for monitor notebooks |
| Storage account with ADLS Gen2 | Raw monitor output |
| Blob container | Example: `monitor` |
| Key Vault | Store service principal secret |
| App registration / service principal | Power BI, Graph, and Storage authentication |

## Network and identity checklist

Confirm these before scheduling the notebooks:

1. Synapse Spark can reach the correct Power BI API endpoint:
   - GCC High: `api.high.powerbigov.us`
   - DoD: `api.mil.powerbigov.us`
2. Synapse Spark can reach the correct authority:
   - GCC High / DoD: `login.microsoftonline.us`
3. Synapse Spark can reach Graph:
   - GCC High / DoD: `graph.microsoft.us`
4. Storage firewall/private endpoint rules allow Synapse access.
5. The monitor identity has Storage Blob Data Contributor on the output container.
6. If hierarchical namespace is enabled, grant filesystem/path ACLs as well as RBAC.
7. Power BI tenant settings allow the service principal/security group to call admin APIs.
8. The identity has the required Power BI / Graph permissions for selected modules.

## Recommended storage layout

Set:

```text
STORAGE_ACCOUNT_CONTAINER_ROOT_PATH=fabric-monitor
```

The monitor writes module folders under that root:

```text
fabric-monitor/
  activity/yyyy/mm/dd/*.json
  apps/yyyy/mm/dd/apps.json
  capacity/yyyy/mm/dd/*.capacity.json
  catalog/scans/yyyy/mm/dd/*.scanResults.json
  catalog/snapshots/yyyy/mm/dd/*.json
  gateways/yyyy/mm/dd/*.json
  graph/yyyy/mm/dd/*.json
  refreshables/yyyy/mm/dd/*.json
  refresh_history/yyyy/mm/dd/*.json
```

The PBIP copies in `pbip-synapse-gov` assume this same root path by default.

## Notebook files

Use these notebook templates:

| Notebook | Purpose |
|---|---|
| `notebooks/synapse-gov/00_setup_synapse_gov.ipynb` | Adds the monitor source to `sys.path` and installs dependencies |
| `notebooks/synapse-gov/01_run_monitor_all_to_storage.ipynb` | Runs collection modules and writes output to Azure Government storage |
| `notebooks/synapse-gov/02_validate_storage_output.ipynb` | Reads output with Spark to confirm the files are accessible |

## Notebook setup

If using Synapse Git integration, update this cell in each notebook:

```python
solution_path = "/synfs/<workspace-git-path>/monitor"
```

If uploading a zip instead, upload `monitor.zip` to workspace storage and use the zip extraction cell in `00_setup_synapse_gov.ipynb`.

Install dependencies in the notebook session:

```python
%pip install -r /synfs/<workspace-git-path>/monitor/requirements.txt
```

For production, attach dependencies as Spark pool packages instead of installing during every run.

## Run collection

In `01_run_monitor_all_to_storage.ipynb`, set:

```python
settings = {
    "TENANT_ID": "<tenant-id>",
    "CLIENT_ID": "<client-id>",
    "CLIENT_SECRET": "<client-secret-or-keyvault-value>",
    "CLOUD_ENVIRONMENT": "GccHigh",
    "APPLICATION_MODULES": "Activity,Apps,Capacity,Catalog,Gateway,Graph,Refreshables,RefreshHistory",
    "STORAGE_ACCOUNT_URL": "https://<storage-account>.blob.core.usgovcloudapi.net",
    "STORAGE_ACCOUNT_CONTAINER_NAME": "<container-name>",
    "STORAGE_ACCOUNT_CONTAINER_ROOT_PATH": "fabric-monitor",
    "ALL_WORKSPACES": True,
}
```

Then run:

```python
from env.notebook import run

await run(settings)
```

Use `ALL_WORKSPACES=True` for the first catalog baseline. Use `False` for regular incremental runs.

## Schedule with Synapse pipelines

Recommended schedule:

| Pipeline | Modules | Cadence |
|---|---|---|
| `CollectPowerBIActivity` | `Activity` | Daily |
| `CollectCatalogBaseline` | `Catalog` with `ALL_WORKSPACES=True` | Monthly or before major governance reviews |
| `CollectCatalogIncremental` | `Catalog` with `ALL_WORKSPACES=False` | Daily or weekly |
| `CollectOperations` | `Capacity,Gateway,Refreshables,RefreshHistory` | Daily |
| `CollectGraph` | `Graph` | Daily or weekly |

In Synapse Studio:

1. Create a pipeline.
2. Add a Notebook activity.
3. Select the Spark pool.
4. Parameterize the notebook settings where appropriate.
5. Add a schedule trigger.

## PBIP reports for the storage output

Use the Azure Government PBIP copies:

```text
pbip-synapse-gov/
  Audits/Activities.pbip
  Catalog/Schema.pbip
  Capacity_Gateways/CapacityGateways.pbip
```

Each semantic model has these Power Query parameters:

| Parameter | Example |
|---|---|
| `MonitorStorageAccountName` | `mystorageacct` |
| `MonitorStorageContainerName` | `monitor` |
| `MonitorStorageRootPath` | `fabric-monitor` |
| `MonitorDfsEndpointSuffix` | `core.usgovcloudapi.net` |

The reports use:

```powerquery
AzureStorage.DataLake("https://" & MonitorStorageAccountName & ".dfs." & MonitorDfsEndpointSuffix)
```

and filter files under:

```text
/<container>/<root>/<module>/
```

For GCC High / DoD, keep `MonitorDfsEndpointSuffix` as:

```text
core.usgovcloudapi.net
```

For Commercial Azure, change it to:

```text
core.windows.net
```

## Report usage

1. Open the PBIP from `pbip-synapse-gov`.
2. Update the four storage parameters.
3. Sign in to the correct Azure Government account when prompted by Power BI Desktop.
4. Refresh.
5. Publish to the approved Power BI workspace.

## Common troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No files found | Wrong storage account/container/root path | Check the PBIP parameters and storage layout |
| Storage auth fails | User/identity lacks Storage Blob Data Reader | Grant RBAC and ADLS ACLs |
| Gateway files are empty | Identity is not gateway admin or VNet gateways are in use | Validate gateway admin visibility and API limitations |
| Catalog scan missing datasource details | Catalog scan settings or admin API settings are incomplete | Ensure `datasourceDetails=true` and tenant settings are enabled |
| Fabric REST modules are skipped | Running in GCC/GCC High/DoD | Expected until Fabric Gov REST support is available |

