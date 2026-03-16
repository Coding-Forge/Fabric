import os
import logging
from env.audit import Audits


def _get_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


async def main():
    audit = Audits()

    # --- Service Principal (required) ---
    audit.set_ServicePrincipal(
        tenant_id=os.environ["TENANT_ID"],
        client_id=os.environ["CLIENT_ID"],
        client_secret=os.environ["CLIENT_SECRET"],
    )

    # --- Modules to run (required) ---
    # Example: "Activity,Apps,Capacity,Catalog,Domains,FabricItems,Gateway,Graph,Refreshables,RefreshHistory,Roles,Tenant,Workspaces"
    audit.set_ApplicationModules(os.environ["APPLICATION_MODULES"])

    # --- Storage: prefer Blob Storage when STORAGE_ACCOUNT_CONN_STR or STORAGE_ACCOUNT_URL
    #     is set, otherwise fall back to Fabric Lakehouse.
    #     STORAGE_ACCOUNT_URL (e.g. https://<account>.blob.core.windows.net) uses
    #     credential-based auth (Managed Identity / service principal) and works even when
    #     shared key access is disabled on the storage account. ---
    storage_conn_str = os.environ.get("STORAGE_ACCOUNT_CONN_STR") or None
    storage_url = os.environ.get("STORAGE_ACCOUNT_URL") or None
    if storage_conn_str:
        audit.set_StorageAccountConnStr(storage_conn_str)
        audit.set_StorageAccountContainerName(os.environ["STORAGE_ACCOUNT_CONTAINER_NAME"])
        root_path = os.environ.get("STORAGE_ACCOUNT_CONTAINER_ROOT_PATH", "")
        if root_path:
            audit.set_StorageAccountContainerRootPath(root_path)
        audit.set_on_fabric(False)
    elif storage_url:
        audit.set_storage_url(storage_url)
        audit.set_StorageAccountContainerName(os.environ["STORAGE_ACCOUNT_CONTAINER_NAME"])
        root_path = os.environ.get("STORAGE_ACCOUNT_CONTAINER_ROOT_PATH", "")
        if root_path:
            audit.set_StorageAccountContainerRootPath(root_path)
        audit.set_on_fabric(False)
    else:
        audit.set_LakehouseName(os.environ["LAKEHOUSE_NAME"])
        audit.set_WorkspaceName(os.environ["WORKSPACE_NAME"])
        path_in_lakehouse = os.environ.get("PATH_IN_LAKEHOUSE", "")
        if path_in_lakehouse:
            audit.set_PathInLakehouse(path_in_lakehouse)
        audit.set_on_fabric(_get_bool("ON_FABRIC", True))

    # --- Optional: extract all workspaces ---
    audit.set_all_workspaces(_get_bool("ALL_WORKSPACES", False))

    # --- Optional: impersonated user ---
    impersonated_user = os.environ.get("IMPERSONATED_USER_NAME")
    if impersonated_user:
        audit.set_ImpersonatedUserName(impersonated_user)

    # --- Optional: Capacity Metrics dataset ---
    capacity_metrics_id = os.environ.get("CAPACITY_METRICS_DATASET_ID")
    if capacity_metrics_id:
        audit.set_capacity_metrics_dataset_id(capacity_metrics_id)

    # --- Optional: per-module cron overrides ---
    # These override the default cron schedule for each module.
    # Format: standard cron syntax, e.g. "0 */4 * * *"
    cron_map = {
        "ACTIVITY_CRON": audit.set_Activity_cron,
        "APPS_CRON": audit.set_Apps_cron,
        "CAPACITY_CRON": audit.set_Capacity_cron,
        "CATALOG_CRON": audit.set_Catalog_cron,
        "DOMAINS_CRON": audit.set_Domains_cron,
        "GATEWAY_CRON": audit.set_Gateway_cron,
        "GRAPH_CRON": audit.set_Graph_cron,
        "REFRESHABLES_CRON": audit.set_Refreshables_cron,
        "REFRESHHISTORY_CRON": audit.set_RefreshHistory_cron,
        "ROLES_CRON": audit.set_Roles_cron,
        "TENANT_CRON": audit.set_Tenant_cron,
    }
    for env_key, setter in cron_map.items():
        value = os.environ.get(env_key)
        if value:
            setter(value)

    logging.info("Starting Fabric Monitor run")
    await audit.run()
    logging.info("Fabric Monitor run complete")
