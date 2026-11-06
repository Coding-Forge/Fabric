# Fabric Monitor

Fabric Monitor collects selected Power BI, Fabric and Microsoft Graph metadata
using Python API collectors. It preserves raw JSON in local files, Blob Storage
or a Fabric Lakehouse, with Power BI reports and a separate Fabric notebook
analytics layer for exploring that evidence.

| Layer | Purpose | Guide |
|---|---|---|
| Collection | Run explicitly enabled modules against authorized APIs and preserve raw observations | [Configuration and API boundaries](docs/configuration-reference.md), [local operation](docs/local-development.md) |
| Analytics | Transform existing Lakehouse files into curated Delta tables, charts and validation reports without calling the collection APIs again | [Notebook walkthrough](notebooks/notebook-guide.md), [table contracts and coverage](notebooks/README.md) |
| Consumption | Use Power BI or notebook views; optionally design KQL access or external delivery | [MonitorRaw report](pbip-local/MonitorRaw/README.md), [Eventhouse, Event Hubs and Splunk](docs/analytics-integration.md) |

**NOTE**  
The application was written using Python 3.10.13 and has successfully been tested up through Python 3.12.2. It is recommended that you install Python 3.12 however you may use Python 3.10.13. 

## Getting Started

**API scope:** Fabric Monitor is **not Admin-API-only**. Catalog uses the Admin
Scanner APIs, but definitions, job history and several existing collectors use
non-Admin APIs with separate resource or Microsoft Graph permissions. Review the
[API scope and authorization boundaries](docs/configuration-reference.md#api-scope-and-authorization-boundaries)
before customer deployment. Every new or changed non-Admin API use must explicitly
document its scope, permissions, coverage, side effects and limitations.

Four additional **opt-in** collectors are available: `FabricItemAccessPermissions`, `FabricItemJobHistory`, `FabricConnections` and `FabricDeploymentPipelineOperations`. By default, configure explicit item scopes for permissions/jobs and check caller/resource permissions before enabling them. See [settings and API limits](docs/configuration-reference.md#scoped-fabric-collectors) and [scheduling, output and recovery guidance](docs/local-development.md#operating-the-four-fabric-collectors). [MonitorRaw](pbip-local/MonitorRaw/README.md) can read these outputs without enabling the collectors; offline tests do not establish live API/storage validation.

Permissions also support **opt-in tenant-wide discovery** with
`FABRIC_ITEM_ACCESS_MODE=tenant`, using only preview Admin APIs. This attempts
access collection for every active item returned by tenant inventory, not just
an explicit list; unsupported/denied items remain failed coverage. Scoped mode
is unchanged by default. See [scope, authorization, quotas and separate JSON
output](docs/configuration-reference.md#tenant-wide-permission-collection-opt-in).
MonitorRaw can read tenant output by selecting `ItemPermissionMode=Tenant` in
Desktop's Manage Parameters; its default stays `Scoped`, with no automatic
mode fallback or cycle merging. See the [report guide](pbip-local/MonitorRaw/README.md).

`FabricItemDefinitions` is a separate **opt-in** collector for tenant-discovered
notebooks and Fabric Data Factory pipelines. It preserves definitions and decoded
pipeline JSON, and infers supported notebook table/file reads and writes plus
static pipeline calls and Copy source/sink references without executing code.
These are potential dependencies, not runtime evidence. See
[enablement, permissions, sensitive output and resumable collection](docs/configuration-reference.md#notebook-and-data-pipeline-definitions).

### Fabric analytics notebooks

The **21 numbered notebooks** in `notebooks/` define **48 managed Delta
datasets**, with selected-field coverage for all **23 registered collectors**.
Nineteen notebooks transform existing raw evidence; 05 visualizes core results,
and 06 validates reruns. Missing collection is not treated as an empty successful
estate, and historical snapshots are not automatically current state.

| Notebooks | Purpose |
|---|---|
| 01-04 | Inventory/health, Scoped/Tenant permissions, job history and scanner/static lineage |
| 05-06 | Core visualizations and persistent rerun validation |
| 07-11 | Activity events, estate catalog/semantic-model schema, connections, gateways and dataset refresh history |
| 12-21 | Apps, capacity/performance, directory/licensing, workspace roles, tenant/delegated settings, domains, Git, tags, broad sharing and deployment operations |

Start with the [notebook walkthrough and run order](notebooks/notebook-guide.md).
Upload the `.ipynb` files, attach your default Lakehouse, preview, then explicitly
enable insert-only Delta writes. No repository/helper upload or collection
credentials are required by these analytics notebooks. The example workspace
and Lakehouse are **FabricMonitor / lh_monitor**.

See the [technical notebook reference](notebooks/README.md) for all output
tables, safety limits, privacy exclusions and validation scopes (10, 25 or 48
tables). Local verification is not Fabric runtime or private-network acceptance.
The initial 01-05 execution was operator-reported successful; acceptance of the
expanded suite remains separate.

The suite currently has **no Event Hub publisher or Splunk export notebook**.
Eventhouse/KQL is optional, not a prerequisite for the proposed
Delta-to-Event-Hubs-to-Splunk path. See
[integration options and outstanding decisions](docs/analytics-integration.md).

### Collector setup

What you need to do to use this application
1.	Create a Service Principal
2.	Grant permissions to the Service Principal  
    a. Fabric Admin Portal  
    b. Service Principal API permissions
3.	Create your .env file  
    a. Set the cron time for each module  
    b. Select which modules you would like the monitor application to use  
    c. Set `CLOUD_ENVIRONMENT` to `Commercial`, `Gcc`, `GccHigh`, or `Dod`  
4.	Using the application  
    a. Native Python Application  
    b. Docker Container  
    c. Notebooks  
    d. Arguments  
5.  Build and Test
    a. Local Testing  
        i. use Azureite for storage  
        ii. 
6.  Function Timer Trigger  
    a. Set Cron  
    b. Deploy  
7. Consuming Data  
    a. FabricMonitor-BlobStorage.PBIT  
    b. pbimonitorwithflow.pbit  
8. DataFlow  
    a. FabricFlow.json

## Create a Service Principal  
To use this application you will need to [create a service principal](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app) in Microsoft Entra. This service principal will need to be granted specific permissions within the [Fabric Admin Portal](https://app.fabric.microsoft.com/admin-portal) and for those that would also like to capture information about users licenses and other privileged information will have to grant permissions to Microsoft Graph.

## Grant Permissions to the Service Principal
The service principal can have several permissions granted depending upon how much information you want to extract from the Fabric estate. The following will outline the what can be done and which permissions need to be granted  

### Fabric Admin Portal Settings  
You can grant specific permissions to service principals to use Fabric APIs including getting metadata of your Power BI semantic models. To enable this the service principal must be put into a group and that group will then be given permission to access the Fabric APIs

<img src="images/admin-portal-settings.png" heigth="500px" width="500px"></img>

### Service Principal API permissions  
For app-only Power BI/Fabric access, tenant settings and resource grants are
distinct from delegated API scopes. The legacy delegated `Tenant.Read.All` entry
below is **not** an application permission to add to the Monitor SPN, and does not
grant workspace access. Follow the
[API scope and authorization guidance](docs/configuration-reference.md#api-scope-and-authorization-boundaries)
for the selected modules; Microsoft Graph application permissions are separate.

In order for the service principal to leverage all of the functionality of the Fabric Montior application you will will need to grant specific API permissions for the service principal. The following can be granted when editing the Service Principal in Microsoft Entra under the Apps section and API permissions.

#### Graph Permissions  
|API/Permissions Name|Type|Description|  
|---|---|---|
|Directory.Read.All|Application|Read Directory Data|
|User.Read|Delegated|Sign in and read user profile|  
|User.Read.All|Application|Read all user's full profile

#### Power BI  
|API/Permissions Name|Type|Description|  
|---|---|---|
|Tenant.Read.All|Delegated|View all content in tenant|

<img src="images/Service-Principal-API-Permissions.png" height="400px" width="1500px"></img>

## Create your .env  
Your `.env` file will file will hold your information about what operations you want the appliction to undertake and will also include configuration for the service principal of which includes the client_id, client_secret, tenant_id, and environment. This code repository specifically prohibits the uploading of the `.env` file to your code repository as this will expose secrets. There is work currently underway to add Managed Identity **STAY TUNED**

> NOTE: USE the enclosed .env.exmple file to build your `.env` file

## Storing your Data  
You can determine where your data will be stored. In your `.env` you need to fill in information for a blob container if you want to store information to blob. If you would like to use a **FABRIC** Lakehouse then fill in the name of the Lakehouse and its required information and lastly, if you would like your data saved locally you can fill in a location in the local directory value. If you would like more storage capabilities then submit an issue and it can be placed on the backlog for consideration

## Using the Application  
This repository has three ways of using the application for gathering information from the Power BI and Fabric APIs. Every module in the application can be assigned a specific time to execute using the `cron syntax`. After executing the `Monitor.py` module the application will determine if the module should be executed. The application will then update the `State.yaml` file with a timestamp that will be used for further updates. If you would like to deploy your application to a container then you can leverage the Dockerfiles in the containers folders. There are two Dockerfiles, one will execute the application upon startup and the other is set up to be run as a `CRON` job. Both of these images are built from the latest version of Ubuntu.

### Understanding CRON
The `cron` statement is consists of 5 groups if time indicated by the asterisk. The syntax supports the use of commas or dashes to indicate more than one value. The following is the grouping for a `cron` statement. [Understanding cron](https://linuxhandbook.com/crontab/) and how to write simple to complex statements.  
```
* * * * *    Script/Command
| | | | |
| | | | |__ Day of the week (0-6) Sunday == 0  
| | | |____ Month of the year (1-12)  
| | |______ Day of the month (1-31)  
| |________ Hour of the day (0-23)  
|__________ Minute of the hour (0-59)  

```

The following will set the module to run every day of the week
```
* * * * 0-6
```

### Scanner lineage (opt-in)

Set `CATALOG_LINEAGE_ENABLED=true` with `Catalog` included in `APPLICATION_MODULES`
to extract upstream/downstream report, semantic-model, dataflow and datasource
relationships from existing scan responses. No additional API calls are made.
Versioned JSON observations are saved under `lineage_edges/YYYY/MM/DD/`, including
workspace/item coverage and successful empty results. This is relationship
collection, not change detection or a complete Fabric lineage graph.
See [configuration and limits](docs/configuration-reference.md#scanner-lineage).
The [Catalog PBIP Lineage page](pbip-local/Catalog/README.md) can display these
saved observations with workspace/item selectors, upstream/downstream tables,
and coverage diagnostics.

### Arguments

The application can accept one argument that will retrieve all workspaces for the catalog that have been modified. This should be run at the beginning use of the Fabric Monitor and from that point on should be updated daily or monthly depending upon your needs. The following argument will cause the catalog to scan all modified workspaces.
```
python -m app.monitor --base True
```
or to run just the catalog module
```
python -m env.modules.catalog --base True
```

### Running as an Application  
You can run the code by using the following command from the root of this code to execute all the modules or you can run them singly:  
```
# to run the application
python -m app.monitor 

# run with a saved JSON profile
python -m app.monitor --profile .\profiles\local-monitor.json

# run with a specific .env file
python -m app.monitor --env-file .\.env

# full catalog workspace scan for this execution
python -m app.monitor --base

# run a subset of modules for this execution
python -m app.monitor --modules Activity,Catalog

# to run individual modules
python -m env.modules.<module name>
```

The standalone application loads `.env` automatically. The same configuration builder supports both current upper-case environment variable names and the older names from `env/.env.examples`.

Set `CLOUD_ENVIRONMENT` to choose the cloud endpoint profile. `Commercial` is the default. `Gcc`, `GccHigh`, and `Dod` switch Power BI, Graph, authority, and Azure Storage authentication endpoints to government cloud profiles. Fabric REST API and OneLake output modules are automatically skipped outside Commercial until Fabric Gov becomes public preview.

## Azure Synapse Notebooks

The monitor can also be run from Azure Synapse notebooks, including Synapse in Azure Government for GCC High scenarios. Notebooks run the Python monitor code and can write output to files, Blob Storage, or a downstream Synapse Dedicated SQL Pool load step.

See [Running the Monitor from Azure Synapse Notebooks](docs/azure-synapse-notebooks.md) for import options, notebook setup, required configuration, GCC High notes, and Dedicated SQL Pool loading patterns.

## Enterprise Deployment

Choose hosting, storage and curation for the target cloud and network policy.
Azure Functions with Blob/ADLS Gen2 and downstream Synapse is one deployment
option; Fabric Lakehouse storage with the numbered analytics notebooks is another
analytics path where supported. Neither path removes API authorization or
private-network acceptance requirements.

See [Enterprise Deployment Best Practices](docs/enterprise-deployment-best-practices.md) for cloud-specific guidance across Commercial, GCC, GCC High, and DoD.

## Windows UI Launcher

For a simple end-user experience on Windows, use:

```text
Run Fabric Monitor UI.cmd
```

The launcher creates a local virtual environment, installs dependencies on first run, and opens the Windows UI. Users can also run:

```text
Create Desktop Shortcut.cmd
```

to create a desktop icon.

See [Windows UI Release and Launcher](docs/windows-ui-release.md) for release zip and enterprise packaging guidance.

The following helper is for **running API collectors inside a Fabric notebook**.
It is not needed by the self-contained numbered analytics notebooks, which read
existing files instead. For collector execution, keep the repository files
available in the notebook environment and call the helper from a setup cell.
Resolve credentials from an approved secret store rather than saving secret
values in notebook source or executed outputs:

```python
from env.notebook import run

await run({
    "TENANT_ID": "<tenant-id>",
    "CLIENT_ID": "<client-id>",
    "CLIENT_SECRET": "<client-secret>",
    "APPLICATION_MODULES": "Activity,Catalog,Tenant",
    "LAKEHOUSE_NAME": "<lakehouse-name>",
    "WORKSPACE_NAME": "<workspace-name>",
    "PATH_IN_LAKEHOUSE": "FabricMonitor",
    "ON_FABRIC": True,
})
```

For local Python, use `OUTPUT_PATH` for local files or configure Blob Storage with either `STORAGE_ACCOUNT_CONNECTION_STRING` or `STORAGE_ACCOUNT_URL` plus `STORAGE_ACCOUNT_CONTAINER_NAME`.

### Running the Windows Desktop UI

For non-developer desktop use on Windows, create the virtual environment first. If this command fails:

```powershell
.\.venv\Scripts\Activate.ps1
```

then `.venv` has not been created yet.

Run the UI setup script from the repository root:

```powershell
cd C:\Projects\Fabric\monitor
.\setup-windows-ui.ps1
```

The setup script checks for Python 3.12, creates `.venv`, and installs `requirements.txt`. If only `3.12-arm64` is installed, the script uses ARM64-compatible dependency markers and skips packages that do not have Windows ARM64 wheels. If Python 3.12 is missing, install Python 3.12 from [python.org](https://www.python.org/downloads/) and rerun the script.

After setup succeeds, start the UI:

```powershell
.\.venv\Scripts\Activate.ps1
python -m app.windows_ui
```

If PowerShell blocks activation scripts, run this once:

```powershell
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

The UI lets users enter service principal settings, choose output storage, select modules, save/load JSON profiles, and run the monitor while viewing logs. See [docs/windows-ui.md](docs/windows-ui.md).

### Build Docker Image  
from the root of the application you can type the following commands to build your image  
```
docker build -t monitor/fabric:1.0 -f ./containers/Dockerfile2
```
> To build a CRON job that can execute based on schedules use the following to build

```
docker build -t monitor/fabric:cron -f ./containers/Dockerfile
```

### Using your Docker Image
Once you have your docker image created you can do several things with it. The first thing you can do is run the container from your local compute. Running the image locally gives the ability to see the application run and connect to the container to analyze the performance. Secondly, you could register your image with a container registry. Follow the link for publishing your image to [Azure Container Registry](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-get-started-docker-cli?tabs=azure-cli). At this point you can now use that image in multiple services that host container images.

#### Register your image with Azure Container Registry

```
docker tag <localimage> <acr name>.azurecr.io/<image name>
docker push <acr name>.azurecr.io/<image name>
```

Learn how to use [Azure Kubernetes Service](https://learn.microsoft.com/en-us/azure/aks/tutorial-kubernetes-prepare-app) with your image  
Learn how to publish to [Azure Container Instance](https://learn.microsoft.com/en-us/azure/container-instances/container-instances-tutorial-prepare-app)  with your image  
Use [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull?tabs=azure-cli&pivots=azure-portal) with your published container image


### Running notebooks

For curated Fabric analytics, use **01-21** and follow the
[notebook guide](notebooks/notebook-guide.md). These are generated, uploadable
artifacts; do not edit their embedded implementation or use the legacy
`environment.yml` as their Fabric runtime configuration.

The older `activity.ipynb`, `catalog.ipynb`, `Deconstruct.ipynb` and `nbk.ipynb`
are experiments, not prerequisites or replacements for the numbered suite.
For running the Python collector from a notebook runtime, use the helper above
or the [Synapse collector guide](docs/azure-synapse-notebooks.md).


### Reports  
The power bi reports are templates that have parameters to fill in to populate the data. The simplest process is to set up a Dataflow Gen 1 in the Power BI Service and then use the Power BI template with flow. There is a defined flow where you will neeed to change the following in the json file  
```
<your account here> => the name of the storage account
<your container name here> => the name of the container in the storage account

you may not have to change the <capacity> but if you do you can find the capacity section of the url and replace it
```
You can also use the FabricMonitor and provide the name of the Storage account and the container name plus the UTC offset, RangeStart and RangeEnd along with your SAS or Account Key.

A third option is the Power BI Project in [pbip-local/MonitorRaw/](pbip-local/MonitorRaw/README.md). It reads the raw JSON output directly, from a local folder (`LOCAL_OUTPUT_PATH`) or from Blob Storage, and includes the four optional Fabric collectors. Basic Desktop checks and Scoped/Tenant permission views have been verified; detailed fixture checks and Local/Blob parity remain unconfirmed. Read its README for validation status, historical warnings and the acceptance checklist.

# Build and Test
Run the unit tests from the repository root:
```
python3 -m unittest discover -s tests -t .
```

See [docs/changelog.md](docs/changelog.md) for recent bug fixes (B1–B16), behaviour notes (state/`lastRun`, 7-day first run, 30-day Activity limit, catalog polling caps) and known gaps, the opt-in E5 modules (`GitConnections`, `Tags`, `DelegatedSettings`, `WidelySharedLinks`), and [docs/configuration-reference.md](docs/configuration-reference.md) for environment variables.

To check your version and upgrade, see [docs/updating.md](docs/updating.md). The version is in the top-level `VERSION` file and is logged at startup.

The `CapacityMetrics` module was rewritten (plan item E7). It reads the Capacity Metrics app semantic model through the `executeQueries` REST API and writes a new output format, which is a breaking change for consumers of the old files. See the [changelog](docs/changelog.md) and [Capacity Metrics settings](docs/configuration-reference.md#capacity-metrics-capacitymetrics).

# Contribute
TODO: Explain how other users and developers can contribute to make your code better. 

If you want to learn more about creating good readme files then refer the following [guidelines](https://docs.microsoft.com/en-us/azure/devops/repos/git/create-a-readme?view=azure-devops). You can also seek inspiration from the below readme files:
- [ASP.NET Core](https://github.com/aspnet/Home)
- [Visual Studio Code](https://github.com/Microsoft/vscode)
- [Chakra Core](https://github.com/Microsoft/ChakraCore)
