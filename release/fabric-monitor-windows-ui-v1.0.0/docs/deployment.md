# Deploying to Azure

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed and logged in (`az login`)
- Azure Functions Core Tools v4 (`func`)
- An Azure subscription with a resource group

---

## 1. Create Azure Resources

You need the following resources before deploying:

| Resource | Notes |
|---|---|
| Resource Group | Logical container for all resources |
| Storage Account | Required by the Function runtime (`AzureWebJobsStorage`) AND for output data |
| App Service Plan | Use **Consumption (Serverless)** or **Flex Consumption** for cost efficiency |
| Function App | Python 3.12, Linux |

### Using Azure CLI

```bash
RG="rg-fabric-monitor"
LOCATION="eastus"
STORAGE="fabricmonitorstor"   # must be globally unique, 3-24 lowercase alphanumeric
FUNCAPP="fabric-monitor-fn"   # must be globally unique
PLAN="fabric-monitor-plan"

# Resource group
az group create --name $RG --location $LOCATION

# Storage account (used by the Function runtime)
az storage account create \
  --name $STORAGE \
  --resource-group $RG \
  --location $LOCATION \
  --sku Standard_LRS \
  --allow-blob-public-access false

# App Service Plan (Consumption)
az functionapp plan create \
  --name $PLAN \
  --resource-group $RG \
  --location $LOCATION \
  --os-type Linux \
  --sku Y1

# Function App
az functionapp create \
  --name $FUNCAPP \
  --resource-group $RG \
  --storage-account $STORAGE \
  --plan $PLAN \
  --runtime python \
  --runtime-version 3.12 \
  --functions-version 4 \
  --os-type Linux
```

---

## 2. Configure Application Settings

Set environment variables on the Function App. **Do not include `DRY_RUN`, `AZURE_CLIENT_*` vars (Managed Identity handles auth in Azure).**

```bash
az functionapp config appsettings set \
  --name $FUNCAPP \
  --resource-group $RG \
  --settings \
    TENANT_ID="<your-tenant-id>" \
    CLIENT_ID="<your-app-client-id>" \
    CLIENT_SECRET="<your-app-client-secret>" \
    APPLICATION_MODULES="Activity,Apps,Capacity,Catalog,Domains,FabricItems,Gateway,Graph,Refreshables,RefreshHistory,Roles,Tenant,Workspaces" \
    STORAGE_ACCOUNT_URL="https://<your-data-storage-account>.blob.core.windows.net" \
    STORAGE_ACCOUNT_CONTAINER_NAME="monitor" \
    STORAGE_ACCOUNT_CONTAINER_ROOT_PATH="stage" \
    ALL_WORKSPACES="false"
```

> **Recommended:** Store `CLIENT_SECRET` in **Azure Key Vault** and reference it as:
> `CLIENT_SECRET=@Microsoft.KeyVault(SecretUri=https://<vault>.vault.azure.net/secrets/<name>/)`
> This requires the Function App's Managed Identity to have the `Key Vault Secrets User` role on the vault.

---

## 3. Deploy the Function Code

From the project root:

```bash
func azure functionapp publish $FUNCAPP
```

The CLI will package and upload everything not listed in `.funcignore`. On success you'll see:

```
Deployment successful.
Remote build succeeded!
Syncing triggers...
Functions in fabric-monitor-fn:
    Fabric_Monitor - [timerTrigger]
```

### Re-deploying after code changes

```bash
func azure functionapp publish $FUNCAPP
```

---

## 4. Deploy with Azure Developer CLI (azd)

The project includes an `azure.yaml` for `azd` deployments, which can also provision infrastructure via the Bicep templates in `infra/`.

```bash
# First time
azd up

# Subsequent deploys (code only, no infra changes)
azd deploy
```

> `azd up` provisions all infra defined in `infra/main.bicep` and then deploys the code.

---

## 5. Verify the Deployment

### Check logs in real time

```bash
func azure functionapp logstream $FUNCAPP
```

### Trigger the function manually (without waiting for the timer)

```bash
az rest \
  --method post \
  --uri "https://management.azure.com/subscriptions/<sub-id>/resourceGroups/$RG/providers/Microsoft.Web/sites/$FUNCAPP/functions/Fabric_Monitor/triggerUrl?api-version=2022-03-01" \
  --query value -o tsv | xargs -I{} curl -X POST {}
```

Or in the Azure Portal → Function App → Functions → `Fabric_Monitor` → **Test/Run**.

### Check Application Insights

If you deploy with `azd` (which provisions Application Insights via `infra/`), all logs and exceptions are automatically captured. Navigate to:

**Azure Portal → Application Insights → Logs → traces**

```kusto
traces
| where message contains "[API]" or message contains "[BLOB"
| order by timestamp desc
| take 50
```

---

## 6. Update the Timer Schedule

Edit the `schedule` parameter in `function_app.py` and redeploy:

```python
# Every 4 hours (default)
@app.schedule(schedule="0 0 */4 * * *", ...)

# Every day at 2am UTC
@app.schedule(schedule="0 0 2 * * *", ...)
```

---

## Clean Up

```bash
az group delete --name $RG --yes --no-wait
```
