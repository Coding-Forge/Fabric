import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from env.audit import Audits
from env.cloud import get_cloud_profile

DEFAULT_APPLICATION_MODULES = (
    "Activity,Apps,Catalog,Graph,Tenant,RefreshHistory,Gateway"
)


def _normalize_key(key: str) -> str:
    return key.replace("_", "").lower()


def _settings_lookup(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    if not settings:
        return {}
    return {_normalize_key(key): value for key, value in settings.items()}


def _get_value(
    settings: Mapping[str, Any] | None,
    *names: str,
    default: Any = None,
    required: bool = False,
) -> Any:
    lookup = _settings_lookup(settings)
    for name in names:
        normalized = _normalize_key(name)
        if normalized in lookup and lookup[normalized] not in (None, ""):
            return lookup[normalized]
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    for name in names:
        normalized = _normalize_key(name)
        for env_name, env_value in os.environ.items():
            if _normalize_key(env_name) == normalized and env_value != "":
                return env_value
    if required:
        raise KeyError(names[0])
    return default


def _get_bool(
    settings: Mapping[str, Any] | None, *names: str, default: bool = False
) -> bool:
    value = _get_value(settings, *names, default=default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _set_if_present(
    settings: Mapping[str, Any] | None, names: tuple[str, ...], setter
) -> None:
    value = _get_value(settings, *names)
    if value not in (None, ""):
        setter(value)


def load_profile(profile_path: str | os.PathLike[str]) -> dict[str, Any]:
    path = Path(profile_path)
    with path.open("r", encoding="utf-8") as profile_file:
        profile = json.load(profile_file)

    if not isinstance(profile, dict):
        raise RuntimeError(f"Profile must contain a JSON object: {path}")
    return profile


def _resolve_local_output_path(raw_path: str) -> str:
    path = os.path.abspath(os.path.expanduser(raw_path))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"LOCAL_OUTPUT_PATH is unusable ({path}): {exc}") from exc
    if not os.path.isdir(path) or not os.access(path, os.W_OK | os.X_OK):
        raise RuntimeError(f"LOCAL_OUTPUT_PATH is not a writable directory: {path}")
    return path


def build_audit(
    settings: Mapping[str, Any] | None = None,
    *,
    load_env_file: bool = False,
    env_file: str | os.PathLike[str] | None = None,
    audit: Audits | None = None,
) -> Audits:
    if load_env_file:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=env_file)

    if audit is None:
        audit = Audits()
    cloud = get_cloud_profile(
        _get_value(settings, "CLOUD_ENVIRONMENT", "ENVIRONMENT", default="Commercial")
    )
    local_output = _get_value(settings, "LOCAL_OUTPUT_PATH")

    def credential(canonical: str, legacy: str) -> str:
        names = (canonical, legacy)
        if local_output and cloud.is_commercial:
            names = (f"COMMERCIAL_{canonical}", *names)
        return _get_value(settings, *names, required=True)

    credentials = {
        "tenant_id": credential("TENANT_ID", "TenantId"),
        "client_id": credential("CLIENT_ID", "ClientId"),
        "client_secret": credential("CLIENT_SECRET", "ClientSecret"),
    }
    if not cloud.is_commercial:
        credentials["environment"] = cloud.name
    audit.set_ServicePrincipal(**credentials)
    audit.set_ApplicationModules(
        _get_value(
            settings,
            "APPLICATION_MODULES",
            "ApplicationModules",
            default=DEFAULT_APPLICATION_MODULES,
        )
    )

    audit.set_all_workspaces(
        _get_bool(settings, "ALL_WORKSPACES", "Base", default=False)
    )
    if (
        _get_value(settings, "EXCLUDE_PERSONAL_WORKSPACES", "ExcludePersonalWorkspaces")
        is not None
    ):
        audit.exclude_personal_workspaces(
            _get_bool(
                settings, "EXCLUDE_PERSONAL_WORKSPACES", "ExcludePersonalWorkspaces"
            )
        )
    if (
        _get_value(settings, "EXCLUDE_INACTIVE_WORKSPACES", "ExcludeInactiveWorkspaces")
        is not None
    ):
        audit.exclude_inactive_workspaces(
            _get_bool(
                settings, "EXCLUDE_INACTIVE_WORKSPACES", "ExcludeInactiveWorkspaces"
            )
        )
    if _get_value(settings, "GRAPH_EXTRACT_GROUPS", "GraphExtractGroups") is not None:
        audit.set_GraphExtractGroups(
            _get_bool(settings, "GRAPH_EXTRACT_GROUPS", "GraphExtractGroups")
        )

    _set_if_present(
        settings,
        ("IMPERSONATED_USER_NAME", "ImpersonatedUserName"),
        audit.set_ImpersonatedUserName,
    )
    _set_if_present(
        settings,
        ("POWER_BI_AUDIENCE_GROUP_IDS", "PowerBIAudienceGroupIds"),
        audit.set_PowerBIAudienceGroupIds,
    )
    _set_if_present(
        settings,
        ("CAPACITY_METRICS_DATASET_ID", "CapacityMetricsDatasetId"),
        audit.set_capacity_metrics_dataset_id,
    )
    _set_if_present(
        settings,
        ("CATALOG_GET_INFO_PARAMETERS", "CatalogGetInfoParameters"),
        audit.set_CatalogGetInfoParameters,
    )
    _set_if_present(
        settings,
        ("CATALOG_GET_MODIFIED_PARAMETERS", "CatalogGetModifiedParameters"),
        audit.set_CatalogGetModifiedParameters,
    )
    output = _get_value(settings, "OUTPUT_PATH")
    connection_string = _get_value(
        settings,
        "STORAGE_ACCOUNT_CONN_STR",
        "STORAGE_ACCOUNT_CONNECTION_STRING",
    )
    storage_url = _get_value(settings, "STORAGE_ACCOUNT_URL", "storage_url")
    lakehouse = _get_value(settings, "LAKEHOUSE_NAME")
    if local_output or output:
        audit.set_OutputPath(
            _resolve_local_output_path(local_output) if local_output else output
        )
        audit.set_on_fabric(False)
    elif connection_string or storage_url:
        if connection_string:
            audit.set_StorageAccountConnStr(connection_string)
        else:
            audit.set_storage_url(storage_url)
        audit.set_StorageAccountContainerName(
            _get_value(
                settings,
                "STORAGE_ACCOUNT_CONTAINER_NAME",
                "container_name",
                required=True,
            )
        )
        _set_if_present(
            settings,
            ("STORAGE_ACCOUNT_CONTAINER_ROOT_PATH",),
            audit.set_StorageAccountContainerRootPath,
        )
        audit.set_on_fabric(False)
    elif lakehouse:
        if not cloud.supports_onelake:
            raise RuntimeError(
                f"Fabric Lakehouse / OneLake output is not enabled for CLOUD_ENVIRONMENT={cloud.name}. "
                "Use OUTPUT_PATH or Blob Storage until Fabric Gov is available."
            )
        audit.set_LakehouseName(lakehouse)
        audit.set_WorkspaceName(_get_value(settings, "WORKSPACE_NAME", required=True))
        _set_if_present(settings, ("PATH_IN_LAKEHOUSE",), audit.set_PathInLakehouse)
        audit.set_on_fabric(_get_bool(settings, "ON_FABRIC", default=True))
    else:
        audit.set_OutputPath("Data")
        audit.set_on_fabric(False)

    cron_map = {
        ("ACTIVITY_CRON", "Activity_cron"): audit.set_Activity_cron,
        ("APPS_CRON", "Apps_cron"): audit.set_Apps_cron,
        ("CAPACITY_CRON", "Capacity_cron"): audit.set_Capacity_cron,
        (
            "CAPACITYMETRICS_CRON",
            "CAPACITY_METRICS_CRON",
        ): audit.set_CapacityMetrics_cron,
        ("CATALOG_CRON", "Catalog_cron"): audit.set_Catalog_cron,
        ("DOMAINS_CRON", "Domains_cron"): audit.set_Domains_cron,
        ("FABRICITEMS_CRON", "FabricItems_cron"): audit.set_FabricItems_cron,
        ("GATEWAY_CRON", "Gateway_cron"): audit.set_Gateway_cron,
        ("GRAPH_CRON", "Graph_cron"): audit.set_Graph_cron,
        ("REFRESHABLES_CRON", "Refreshables_cron"): audit.set_Refreshables_cron,
        ("REFRESHHISTORY_CRON", "RefreshHistory_cron"): audit.set_RefreshHistory_cron,
        ("ROLES_CRON", "Roles_cron"): audit.set_Roles_cron,
        ("TENANT_CRON", "Tenant_cron"): audit.set_Tenant_cron,
        ("WORKSPACES_CRON", "Workspaces_cron"): audit.set_Workspaces_cron,
        ("GITCONNECTIONS_CRON",): audit.set_GitConnections_cron,
        ("TAGS_CRON",): audit.set_Tags_cron,
        ("DELEGATEDSETTINGS_CRON",): audit.set_DelegatedSettings_cron,
        ("WIDELYSHAREDLINKS_CRON",): audit.set_WidelySharedLinks_cron,
        (
            "FABRICITEMACCESSPERMISSIONS_CRON",
        ): audit.set_FabricItemAccessPermissions_cron,
        ("FABRICITEMJOBHISTORY_CRON",): audit.set_FabricItemJobHistory_cron,
        ("FABRICITEMDEFINITIONS_CRON",): audit.set_FabricItemDefinitions_cron,
        ("FABRICCONNECTIONS_CRON",): audit.set_FabricConnections_cron,
        (
            "FABRICDEPLOYMENTPIPELINEOPERATIONS_CRON",
        ): audit.set_FabricDeploymentPipelineOperations_cron,
    }
    for names, setter in cron_map.items():
        _set_if_present(settings, names, setter)

    return audit


async def run_monitor(
    settings: Mapping[str, Any] | None = None,
    *,
    load_env_file: bool = False,
    env_file: str | os.PathLike[str] | None = None,
) -> None:
    audit = build_audit(
        settings=settings, load_env_file=load_env_file, env_file=env_file
    )
    if await audit.run() is False:
        raise RuntimeError("Fabric Monitor run failed; see module and storage errors.")
