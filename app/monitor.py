import logging
import os

from env.audit import Audits
from env.version import get_version

logger = logging.getLogger(__name__)


def _get_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


# Canonical credential variable -> alias honoured only in local output mode.
_COMMERCIAL_ALIASES = {
    "TENANT_ID": "COMMERCIAL_TENANT_ID",
    "CLIENT_ID": "COMMERCIAL_CLIENT_ID",
    "CLIENT_SECRET": "COMMERCIAL_CLIENT_SECRET",
}


def _resolve_local_output_path(raw_path: str) -> str:
    """Resolve and prepare the local output folder for a proof-of-concept run.

    :param raw_path: Value of ``LOCAL_OUTPUT_PATH`` (``~`` is expanded).
    :return: The absolute path of the existing, writable directory.
    :raises RuntimeError: If the folder cannot be created or is not writable.
    """
    path = os.path.abspath(os.path.expanduser(raw_path))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"LOCAL_OUTPUT_PATH is unusable ({path}): {e}") from e
    if not os.path.isdir(path) or not os.access(path, os.W_OK | os.X_OK):
        raise RuntimeError(f"LOCAL_OUTPUT_PATH is not a writable directory: {path}")
    return path


def _get_env(*names: str) -> str:
    """Return the first non-empty environment variable among ``names``.

    The first name is canonical; later names are legacy aliases kept so that
    existing ``.env`` files (``TenantId``/``ClientId``/``ClientSecret``) still work.

    Precedence for the service principal credentials:

    * Default: ``TENANT_ID`` > ``TenantId`` (likewise for CLIENT_ID/CLIENT_SECRET).
    * Only when ``LOCAL_OUTPUT_PATH`` is set (local proof-of-concept mode):
      ``COMMERCIAL_TENANT_ID`` / ``COMMERCIAL_CLIENT_ID`` /
      ``COMMERCIAL_CLIENT_SECRET`` come first, then ``TENANT_ID`` etc., then the
      legacy ``TenantId`` etc. These aliases are never used for storage credentials.

    Values are never logged.

    :param names: Environment variable names in priority order.
    :return: The value of the first variable that is set and non-empty.
    :raises KeyError: If none of the variables is set.
    """
    if (
        os.environ.get("LOCAL_OUTPUT_PATH")
        and names
        and names[0] in _COMMERCIAL_ALIASES
    ):
        names = (_COMMERCIAL_ALIASES[names[0]], *names)
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    raise KeyError(names[0])


async def main():
    audit = Audits()

    # --- Service Principal (required) ---
    audit.set_ServicePrincipal(
        tenant_id=_get_env("TENANT_ID", "TenantId"),
        client_id=_get_env("CLIENT_ID", "ClientId"),
        client_secret=_get_env("CLIENT_SECRET", "ClientSecret"),
    )

    # --- Modules to run (required) ---
    # Example: "Activity,Apps,Capacity,Catalog,Domains,FabricItems,Gateway,Graph,Refreshables,RefreshHistory,Roles,Tenant,Workspaces"
    audit.set_ApplicationModules(os.environ["APPLICATION_MODULES"])

    # --- Storage: prefer Blob Storage when STORAGE_ACCOUNT_CONN_STR or STORAGE_ACCOUNT_URL
    #     is set, otherwise fall back to Fabric Lakehouse.
    #     STORAGE_ACCOUNT_URL (e.g. https://<account>.blob.core.windows.net) uses
    #     credential-based auth (Managed Identity / service principal) and works even when
    #     shared key access is disabled on the storage account. ---
    storage_conn_str = (
        os.environ.get("STORAGE_ACCOUNT_CONN_STR")
        or os.environ.get("STORAGE_ACCOUNT_CONNECTION_STRING")
        or None
    )
    storage_url = os.environ.get("STORAGE_ACCOUNT_URL") or None
    local_output_path = os.environ.get("LOCAL_OUTPUT_PATH") or None
    if local_output_path:
        # Explicit opt-in local mode: takes precedence over Blob/Lakehouse settings
        # (which are ignored) so a PoC run cannot write to production storage.
        resolved_path = _resolve_local_output_path(local_output_path)
        audit.set_OutputPath(resolved_path)
        audit.set_on_fabric(False)
        logger.info("Local output mode enabled; writing to %s", resolved_path)
    elif storage_conn_str:
        audit.set_StorageAccountConnStr(storage_conn_str)
        audit.set_StorageAccountContainerName(
            os.environ["STORAGE_ACCOUNT_CONTAINER_NAME"]
        )
        root_path = os.environ.get("STORAGE_ACCOUNT_CONTAINER_ROOT_PATH", "")
        if root_path:
            audit.set_StorageAccountContainerRootPath(root_path)
        audit.set_on_fabric(False)
    elif storage_url:
        audit.set_storage_url(storage_url)
        audit.set_StorageAccountContainerName(
            os.environ["STORAGE_ACCOUNT_CONTAINER_NAME"]
        )
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
        "FABRICITEMS_CRON": audit.set_FabricItems_cron,
        "WORKSPACES_CRON": audit.set_Workspaces_cron,
        "CAPACITYMETRICS_CRON": audit.set_CapacityMetrics_cron,
        "GITCONNECTIONS_CRON": audit.set_GitConnections_cron,
        "TAGS_CRON": audit.set_Tags_cron,
        "DELEGATEDSETTINGS_CRON": audit.set_DelegatedSettings_cron,
        "WIDELYSHAREDLINKS_CRON": audit.set_WidelySharedLinks_cron,
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

    logger.info("Starting Fabric Monitor run (version %s)", get_version())
    await audit.run()
    logger.info("Fabric Monitor run complete")
