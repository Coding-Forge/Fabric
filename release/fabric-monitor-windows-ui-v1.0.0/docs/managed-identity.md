# Managed Identity & RBAC Setup

Managed Identity allows the Function App to authenticate to Azure services (Blob Storage, Key Vault) without storing credentials. This is the recommended approach for production.

---

## 1. Enable System-Assigned Managed Identity

### Azure Portal

1. Go to your **Function App** in the Azure Portal
2. Left menu → **Settings** → **Identity**
3. On the **System assigned** tab, switch Status to **On**
4. Click **Save** → confirm

### Azure CLI

```bash
az functionapp identity assign \
  --name $FUNCAPP \
  --resource-group $RG
```

The command outputs the `principalId` (Object ID) of the identity — save it for the next steps.

```bash
# Get the principal ID if you need it later
PRINCIPAL_ID=$(az functionapp identity show \
  --name $FUNCAPP \
  --resource-group $RG \
  --query principalId -o tsv)
```

---

## 2. Grant Blob Storage Access (RBAC)

The Function App needs to read and write to your data storage account (the one holding monitor output, **not** the one used by `AzureWebJobsStorage`).

### Role required

**Storage Blob Data Contributor** — allows read, write, and delete on blobs.

If the function only needs to read state and write output (standard use), this role is sufficient.

### Assign via Azure Portal

1. Go to your **data storage account** (e.g. `fabricdemosg`)
2. Left menu → **Access Control (IAM)**
3. Click **+ Add** → **Add role assignment**
4. Role: search for and select **Storage Blob Data Contributor**
5. Click **Next**
6. Assign access to: **Managed identity**
7. Click **+ Select members** → select your Function App → click **Select**
8. Click **Review + assign**

### Assign via Azure CLI

```bash
DATA_STORAGE="fabricdemosg"   # your data storage account name

STORAGE_RESOURCE_ID=$(az storage account show \
  --name $DATA_STORAGE \
  --resource-group $RG \
  --query id -o tsv)

az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Storage Blob Data Contributor" \
  --scope $STORAGE_RESOURCE_ID
```

> Role assignments can take **1–5 minutes** to propagate.

---

## 3. Grant Key Vault Access (optional but recommended)

If you store `CLIENT_SECRET` in Key Vault, grant the Function App read access to secrets.

### Assign via Azure CLI

```bash
KV_NAME="<your-keyvault-name>"

KV_RESOURCE_ID=$(az keyvault show \
  --name $KV_NAME \
  --resource-group $RG \
  --query id -o tsv)

az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role "Key Vault Secrets User" \
  --scope $KV_RESOURCE_ID
```

Then reference the secret in your Function App settings:

```
CLIENT_SECRET=@Microsoft.KeyVault(SecretUri=https://<vault>.vault.azure.net/secrets/ClientSecret/)
```

---

## 4. Remove AZURE_CLIENT_* Settings from Azure

Once Managed Identity is active in Azure, the `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, and `AZURE_TENANT_ID` settings should **not** be present in the Azure Function App configuration. `DefaultAzureCredential` will automatically use the Managed Identity.

Remove them if previously set:

```bash
az functionapp config appsettings delete \
  --name $FUNCAPP \
  --resource-group $RG \
  --setting-names AZURE_CLIENT_ID AZURE_CLIENT_SECRET AZURE_TENANT_ID
```

> These settings only belong in `local.settings.json` for local development, where Managed Identity is not available.

---

## 5. Power BI / Fabric API Permissions

The service principal (`CLIENT_ID`) used for Power BI and Fabric API calls needs separate permissions — these are **not** handled by Managed Identity.

### Required Azure AD App Registration permissions

In **Azure Portal → Entra ID → App registrations → your app → API permissions**:

| API | Permission | Type |
|---|---|---|
| Power BI Service | `Tenant.Read.All` | Application |

Click **Grant admin consent** after adding.

### Required Power BI Admin role

The service principal must be assigned the **Power BI Administrator** role to access admin APIs (activity log, catalog, tenant settings, etc.).

**Option A — Via Microsoft 365 Admin Center:**
1. Go to [admin.microsoft.com](https://admin.microsoft.com)
2. Users → Active users → find your service principal
3. Assign **Power BI Administrator** role

**Option B — Via Entra ID:**
1. Azure Portal → Entra ID → Roles and administrators
2. Find **Power BI Administrator**
3. Add assignment → select your service principal

**Option C — Via Power BI tenant settings (service principal profiles):**
1. Power BI Admin portal → Tenant settings
2. Find **Allow service principals to use read-only Power BI admin APIs**
3. Enable and add the security group containing your service principal

---

## 6. How Authentication Works in This Project

```
Local development
─────────────────
Function reads AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID
  → DefaultAzureCredential uses ClientSecretCredential
  → Authenticates to Blob Storage as the service principal

Azure (production)
──────────────────
No AZURE_CLIENT_* env vars present
  → DefaultAzureCredential uses ManagedIdentityCredential
  → Authenticates to Blob Storage as the Function App's system identity
  → No secrets needed for blob auth

Power BI / Fabric API (both environments)
──────────────────────────────────────────
MSAL uses CLIENT_ID + CLIENT_SECRET + TENANT_ID
  → Acquires token for https://analysis.windows.net/powerbi/api/.default
  → Used for all Power BI and Fabric REST API calls
```

> The service principal credentials (`CLIENT_ID`, `CLIENT_SECRET`) are still required in Azure for the Power BI API calls. Only the blob storage auth benefits from Managed Identity.

---

## Summary Checklist

- [ ] System-assigned Managed Identity enabled on Function App
- [ ] **Storage Blob Data Contributor** assigned on the data storage account to the Function App identity
- [ ] (Optional) **Key Vault Secrets User** assigned if using Key Vault references
- [ ] `AZURE_CLIENT_*` variables removed from Azure Function App settings
- [ ] `Tenant.Read.All` permission added and admin consent granted on app registration
- [ ] **Power BI Administrator** role assigned to the service principal
