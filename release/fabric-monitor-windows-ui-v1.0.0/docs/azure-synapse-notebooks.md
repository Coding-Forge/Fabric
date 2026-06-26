# Running the Monitor from Azure Synapse Notebooks

This solution can be run from Azure Synapse notebooks when the notebook runtime has network access to the Power BI, Microsoft Graph, storage, and optional Synapse Dedicated SQL Pool endpoints for the selected cloud.

For GCC High, use Azure Synapse in Azure Government and set `CLOUD_ENVIRONMENT=GccHigh`. Fabric REST API modules and OneLake output are intentionally disabled outside `Commercial` until Fabric Gov becomes public preview.

## Recommended Architecture

Use a Synapse Spark notebook as the orchestration/runtime layer:

1. Install or attach this solution's Python package files to the notebook session.
2. Configure service principal credentials and cloud environment settings.
3. Run selected monitor modules.
4. Write output to one of the supported destinations:
   - Synapse workspace storage / ADLS Gen2
   - Azure Government Blob Storage
   - A mounted or copied local notebook path
   - Synapse Dedicated SQL Pool, if you add a notebook load step after the monitor writes files

Dedicated SQL Pools do not run notebooks directly. Notebooks run on Spark or another notebook runtime and can connect to Dedicated SQL Pools through JDBC, ODBC, or SQL client libraries to load/query data.

## Importing the Solution into Synapse

Choose one of these approaches.

### Option A - Upload the source as workspace files

1. Zip the solution folder from `C:\Projects\Fabric\monitor`.
2. Upload the zip to the Synapse workspace storage account, for example:
   `abfss://<container>@<account>.dfs.core.usgovcloudapi.net/fabric-monitor/monitor.zip`
3. In the notebook, unzip it into the Spark session's local filesystem:

```python
import os
import zipfile

zip_path = "/synfs/<path-to-uploaded>/monitor.zip"
target_path = "/tmp/fabric-monitor"

os.makedirs(target_path, exist_ok=True)
with zipfile.ZipFile(zip_path, "r") as archive:
    archive.extractall(target_path)
```

4. Add the solution to `sys.path`:

```python
import sys

solution_path = "/tmp/fabric-monitor"
if solution_path not in sys.path:
    sys.path.insert(0, solution_path)
```

### Option B - Use Git integration

If your Synapse workspace is connected to a Git repository:

1. Commit this solution to the approved repository.
2. Sync the repository into Synapse.
3. Open a notebook in the same workspace.
4. Add the checked-out solution folder to `sys.path`.

```python
import sys

solution_path = "/synfs/<workspace-git-path>/monitor"
if solution_path not in sys.path:
    sys.path.insert(0, solution_path)
```

### Option C - Install as a wheel or workspace package

For repeatable production runs, package the solution and attach it to the Spark pool as a workspace package. This is the cleanest approach when multiple notebooks or scheduled Synapse pipelines need the monitor.

## Install Python Dependencies

Install the dependencies from `requirements.txt` in the notebook session or attach them to the Spark pool.

```python
%pip install -r /tmp/fabric-monitor/requirements.txt
```

Restart the Python session if Synapse prompts you to do so after `%pip install`.

## Required Configuration

The monitor uses the same configuration keys in Synapse as it does locally. At minimum, configure:

| Setting | Required | Notes |
|---|---:|---|
| `TENANT_ID` | Yes | Entra tenant ID for the selected cloud. |
| `CLIENT_ID` | Yes | App registration / service principal client ID. |
| `CLIENT_SECRET` | Yes | Use Key Vault or Synapse linked services for production. |
| `CLOUD_ENVIRONMENT` | Yes | `Commercial`, `Gcc`, `GccHigh`, or `Dod`. |
| `APPLICATION_MODULES` | Yes | Comma-separated modules to run. |
| `OUTPUT_PATH` | Recommended | Local/session path or mounted storage path for file output. |
| `STORAGE_ACCOUNT_URL` | Optional | Blob output URL. For Azure Government, use `https://<account>.blob.core.usgovcloudapi.net`. |
| `STORAGE_ACCOUNT_CONTAINER_NAME` | Optional | Required with Blob output. |
| `KEY_VAULT_URL` | Optional | Recommended for secrets in production. |

Do not use Fabric Lakehouse / OneLake output for `Gcc`, `GccHigh`, or `Dod`. The solution blocks that path until Fabric Gov becomes public preview.

## Notebook Configuration Example

For GCC High with file output:

```python
import os

os.environ["TENANT_ID"] = "<tenant-id>"
os.environ["CLIENT_ID"] = "<client-id>"
os.environ["CLIENT_SECRET"] = "<client-secret>"
os.environ["CLOUD_ENVIRONMENT"] = "GccHigh"
os.environ["APPLICATION_MODULES"] = "Activity,Apps,Capacity,Catalog,Gateway,Graph,Refreshables,RefreshHistory"
os.environ["OUTPUT_PATH"] = "/tmp/fabric-monitor-output"
```

For GCC High with Azure Government Blob output:

```python
import os

os.environ["TENANT_ID"] = "<tenant-id>"
os.environ["CLIENT_ID"] = "<client-id>"
os.environ["CLIENT_SECRET"] = "<client-secret>"
os.environ["CLOUD_ENVIRONMENT"] = "GccHigh"
os.environ["APPLICATION_MODULES"] = "Activity,Apps,Capacity,Catalog,Gateway,Graph,Refreshables,RefreshHistory"
os.environ["STORAGE_ACCOUNT_URL"] = "https://<account>.blob.core.usgovcloudapi.net"
os.environ["STORAGE_ACCOUNT_CONTAINER_NAME"] = "<container>"
os.environ["STORAGE_ACCOUNT_CONTAINER_ROOT_PATH"] = "fabric-monitor"
```

## Running the Monitor from a Notebook

After the solution is on `sys.path` and configuration is set:

```python
from env.config import load_from_environment

audit = load_from_environment()
audit.start()
```

To build settings inline without environment variables:

```python
from env.config import build_audit

settings = {
    "TENANT_ID": "<tenant-id>",
    "CLIENT_ID": "<client-id>",
    "CLIENT_SECRET": "<client-secret>",
    "CLOUD_ENVIRONMENT": "GccHigh",
    "APPLICATION_MODULES": "Activity,Apps,Capacity,Catalog,Gateway,Graph,Refreshables,RefreshHistory",
    "OUTPUT_PATH": "/tmp/fabric-monitor-output",
}

audit = build_audit(settings)
audit.start()
```

## Reading Monitor Data from ADLS Gen2

Synapse notebooks can read monitor output or other source data directly from ADLS Gen2 using `abfss://` paths.

For Azure Government / GCC High, use the government DFS endpoint suffix:

```text
dfs.core.usgovcloudapi.net
```

For Commercial Azure, use:

```text
dfs.core.windows.net
```

JSON example:

```python
activity_path = (
    "abfss://<container>@<storage-account>.dfs.core.usgovcloudapi.net/"
    "fabric-monitor/activity/"
)

activity_df = spark.read.json(activity_path)
display(activity_df)
```

CSV example:

```python
catalog_path = (
    "abfss://<container>@<storage-account>.dfs.core.usgovcloudapi.net/"
    "fabric-monitor/catalog/"
)

catalog_df = (
    spark.read
    .option("header", "true")
    .option("inferSchema", "true")
    .csv(catalog_path)
)

display(catalog_df)
```

Parquet example:

```python
curated_path = (
    "abfss://<container>@<storage-account>.dfs.core.usgovcloudapi.net/"
    "fabric-monitor/curated/"
)

curated_df = spark.read.parquet(curated_path)
display(curated_df)
```

If hierarchical namespace ACLs are enabled, the Synapse workspace managed identity or Spark identity needs both Azure RBAC permissions and filesystem/path ACL access. Common RBAC roles are `Storage Blob Data Reader` for read-only notebooks or `Storage Blob Data Contributor` when notebooks write output.

## Module Selection for GCC High

These modules are the safest starting point in GCC High because they use classic Power BI REST APIs, Microsoft Graph, or local/blob output:

```text
Activity,Apps,Capacity,Catalog,Gateway,Graph,Refreshables,RefreshHistory
```

These modules are skipped automatically outside `Commercial` because they use Fabric REST APIs:

```text
Domains,FabricItems,Roles,Tenant,Workspaces
```

If you include those modules in `APPLICATION_MODULES` for `Gcc`, `GccHigh`, or `Dod`, the monitor logs a warning and continues with the supported modules.

## Loading Results into a Synapse Dedicated SQL Pool

Dedicated SQL Pools can be used as a downstream target after the notebook produces files. A common pattern is:

1. Run the monitor and write JSON/CSV output to ADLS Gen2 or Blob Storage.
2. Read the output files with Spark.
3. Write curated tables to Dedicated SQL Pool with JDBC or PolyBase/COPY.

Example JDBC connection shape for Azure Government:

```python
jdbc_url = (
    "jdbc:sqlserver://<workspace>.sql.azuresynapse.usgovcloudapi.net:1433;"
    "database=<dedicated-sql-pool>;"
    "encrypt=true;"
    "trustServerCertificate=false;"
    "hostNameInCertificate=*.sql.azuresynapse.usgovcloudapi.net;"
)
```

Example Spark write:

```python
df.write \
    .format("jdbc") \
    .option("url", jdbc_url) \
    .option("dbtable", "dbo.PowerBIActivity") \
    .option("user", "<sql-user>") \
    .option("password", "<sql-password>") \
    .mode("append") \
    .save()
```

For production, prefer managed identity, service principal, or Key Vault-backed secrets where supported by your Synapse and SQL configuration.

## Network and Security Requirements

Confirm these before scheduling notebooks:

1. The Synapse Spark pool can reach the selected Power BI API endpoint:
   - Commercial: `api.powerbi.com`
   - GCC: `api.powerbigov.us`
   - GCC High: `api.high.powerbigov.us`
   - DoD: `api.mil.powerbigov.us`
2. The Spark pool can reach the correct authority host:
   - Commercial/GCC: `login.microsoftonline.com`
   - GCC High/DoD: `login.microsoftonline.us`
3. The Spark pool can reach Microsoft Graph for the selected cloud.
4. Storage firewall rules allow the Synapse managed identity or private endpoint path.
5. The service principal has the required Power BI Admin API permissions and tenant settings enabled.
6. Secrets are stored in Key Vault or Synapse-linked secret management, not hard-coded in notebooks.

## Scheduling

Use Synapse pipelines to schedule notebooks:

1. Create a pipeline.
2. Add a Notebook activity.
3. Select the Spark pool and notebook.
4. Pass configuration as pipeline parameters or environment setup cells.
5. Schedule the pipeline trigger.

Keep module schedules in one place. If Synapse is orchestrating execution, prefer one notebook/pipeline schedule per module group instead of relying on long-running notebook sessions.

