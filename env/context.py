import asyncio
import json
import logging
import os
import platform
import re
import socket
import sys
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import aiohttp

from env.cloud import get_cloud_profile
from env.utility import http_retry
from env.utility.file_management import File_Management

# Format of the timestamps stored in state.yaml; the values are always UTC
STATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime (matches parsed state timestamps)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_stamp(moment: datetime | None = None) -> str:
    """Format a UTC moment as a state timestamp.

    :param moment: Naive UTC datetime; defaults to now.
    :return: A ``%Y-%m-%dT%H:%M:%S.%fZ`` string.
    """
    return (moment or utc_now()).strftime(STATE_TIME_FORMAT)


def log_validation_failure(
    logger: logging.Logger,
    label: str,
    field: str,
    expected: str,
    value: object,
    *,
    missing: bool = False,
    ordinal: int | None = None,
) -> None:
    """Log a rejected shape without exposing values or arbitrary type names.

    :param logger: Existing runtime logger.
    :param label: Static collector or response context, never a resource identity.
    :param field: Hardcoded schema field path, never a response-supplied key.
    :param expected: Static description of the required shape.
    :param value: Rejected value; only a fixed type/empty label is emitted.
    :param missing: Whether the field was absent rather than explicitly null.
    :param ordinal: One-based record position, if applicable.
    """
    if missing:
        observed = "missing"
    elif value is None:
        observed = "null"
    elif isinstance(value, bool):
        observed = "boolean"
    elif isinstance(value, str):
        observed = "string" if value else "empty string"
    elif isinstance(value, dict):
        observed = "object"
    elif isinstance(value, list):
        observed = "list"
    elif isinstance(value, (int, float)):
        observed = "number"
    else:
        observed = "other"
    logger.error(
        "%s validation failed: record=%s field=%s expected=%s observed=%s",
        label,
        ordinal if ordinal is not None else "-",
        field,
        expected,
        observed,
    )


# On Linux/WSL, aiohttp tries IPv6 first which causes SSL handshake timeouts.
# Force IPv4 on Linux. On Windows, aiohttp resolves correctly without this constraint.
_CONNECTOR_KWARGS = {"family": socket.AF_INET} if platform.system() != "Windows" else {}
_TIMEOUT = aiohttp.ClientTimeout(total=300, connect=60)

# Documented by Fabric Admin List Item Access Details and Core Get Item.
_FABRIC_ERROR_CODES = frozenset({"ItemNotFound", "InvalidItemType"})
_FABRIC_ERROR_BODY_LIMIT = 16 * 1024


def _safe_http_status(status: object) -> int | None:
    """Return an exact integer HTTP status in range, excluding booleans."""
    return status if type(status) is int and 100 <= status <= 599 else None


def safe_fabric_error_code(payload: object) -> str:
    """Return only a documented static Fabric error code or a fixed safe label.

    :param payload: Untrusted error object. A nonempty string errorCode takes
        precedence; a missing or malformed value falls back to error.code.
    :return: An allowlisted code, ``unrecognized`` for an unknown nonempty
        string, or ``unavailable`` when both candidates are missing or malformed.
        Fixed diagnostic labels survive re-sanitization. No server text is retained.
    """
    if not isinstance(payload, dict):
        return "unavailable"
    code = payload.get("errorCode")
    if type(code) is not str or not code:
        error = payload.get("error")
        code = error.get("code") if isinstance(error, dict) else None
    if type(code) is not str or not code:
        return "unavailable"
    if code in _FABRIC_ERROR_CODES:
        return code
    # Preserve safe labels when a gated error is sanitized again for persistence.
    if code in ("unrecognized", "unavailable"):
        return code
    return "unrecognized"


async def _fabric_response_error_code(response: aiohttp.ClientResponse) -> str:
    """Inspect a failed response within fixed byte and one-second read limits.

    Content type is ignored. Invalid, oversized, unreadable or excessively nested
    JSON yields a fixed label, preserving the original HTTP failure. Cancellation
    propagates. JSON-only response adapters remain supported.
    """

    async def read_payload() -> object:
        content = getattr(response, "content", None)
        if content is None:
            return await response.json(content_type=None)
        try:
            await content.readexactly(_FABRIC_ERROR_BODY_LIMIT + 1)
        except asyncio.IncompleteReadError as exc:
            return json.loads(exc.partial)
        return None

    try:
        payload = await asyncio.wait_for(read_payload(), timeout=1.0)
    except (
        ValueError,
        UnicodeError,
        RecursionError,
        aiohttp.ClientError,
        asyncio.TimeoutError,
    ):
        return "unavailable"
    return safe_fabric_error_code(payload)


async def _error_result(response: aiohttp.ClientResponse) -> dict[str, Any]:
    """Build the error payload returned by ``Context.invokeAPI`` for a non-OK response.

    :param response: The non-OK HTTP response.
    :return: A dict with ``ERROR`` (status description), ``status`` (HTTP code),
        ``retryAfter`` (header value or ``None``) and ``message`` (response body text).
    """
    try:
        body = await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError):
        body = ""
    return {
        "ERROR": f"HTTP {response.status}",
        "status": response.status,
        "retryAfter": response.headers.get("Retry-After"),
        "message": body,
    }


class Context:
    def __init__(self):
        self.cloud = get_cloud_profile(None)
        self.PowerBIAudienceGroupIds = None
        self.CatalogGetInfoParameters = "lineage=true&datasourceDetails=true&getArtifactUsers=true&datasetSchema=true&datasetExpressions=true"
        self.CatalogGetModifiedParameters = (
            "excludePersonalWorkspaces=false&excludeInActiveWorkspaces=true"
        )
        self.ServicePrincipal = {}
        self.LakehouseName = None
        self.PathInLakehouse = None
        self.Activity_cron = None
        self.Apps_cron = None
        self.Capacity_cron = None
        self.Catalog_cron = None
        self.Domains_cron = None
        self.FabricItems_cron = None
        self.Gateway_cron = None
        self.Graph_cron = None
        self.Refreshables_cron = None
        self.RefreshHistory_cron = None
        self.Roles_cron = None
        self.Tenant_cron = None
        self.Workspaces_cron = None
        self.CapacityMetrics_cron = None
        self.GitConnections_cron = None
        self.Tags_cron = None
        self.DelegatedSettings_cron = None
        self.WidelySharedLinks_cron = None
        self.FabricItemAccessPermissions_cron = None
        self.FabricItemJobHistory_cron = None
        self.FabricItemDefinitions_cron = None
        self.FabricConnections_cron = None
        self.FabricDeploymentPipelineOperations_cron = None
        self.ApplicationModules = None
        self.storage_url = None
        self.StorageAccountConnStr = None
        self.StorageAccountContainerName = None
        self.StorageAccountContainerRootPath = None
        self.OutputPath = None
        # Opt-in; GRAPH_EXTRACT_GROUPS=true|1|yes|on enables groups/groupmembers extraction
        graph_groups_flag = os.environ.get("GRAPH_EXTRACT_GROUPS", "").strip().lower()
        self.GraphExtractGroups = (
            True if graph_groups_flag in ("1", "true", "yes", "on") else None
        )
        self.WorkspaceName = None
        self.clients = {}
        self.fm = File_Management()
        self.current_state = None
        # False still means incomplete; only explicit, healthy pauses are nonfatal.
        self.deferred_modules: set[str] = set()
        self.collection_coverage_logged: set[str] = set()
        self.logging_level = logging.ERROR
        self.logger = logging.getLogger(__name__)
        self.all_workspaces = False
        self.exclude_personal_workspaces = True
        self.exclude_inactive_workspaces = True
        self.on_fabric = True
        self.capacity_metrics_dataset_id = None
        self.impersonatedUserName = None
        self._api_semaphore: asyncio.Semaphore | None = None
        self._api_cooldowns = http_retry.RetryCooldowns()

    def __set_log_level(self, level):
        """
        Set the logging level
        """
        # Set the logging level for the Azure SDK
        azure_logger = "azure.core.pipeline.policies.http_logging_policy"
        logging.getLogger(azure_logger).setLevel(logging.WARNING)

        # Basic logging levels
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return levels[level]

    def set_log_config(self, log_level, log_file):
        """
        Set the logging configuration
        """
        stdoutHandler = logging.StreamHandler(sys.stdout)
        errHandler = logging.FileHandler(log_file)

        stdoutHandler.setLevel(logging.DEBUG)
        errHandler.setLevel(self.__set_log_level(log_level))

        fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        stdoutHandler.setFormatter(fmt)
        errHandler.setFormatter(fmt)

        logging.basicConfig(
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            force=True,
            handlers=[stdoutHandler, errHandler],
        )

    def set_on_fabric(self, on_fabric):
        self.on_fabric = on_fabric

    def set_all_workspaces(self, all_workspaces):
        self.all_workspaces = all_workspaces

    def set_current_state(self, current_state):
        self.current_state = current_state

    def set_FileManagement(self, fm):
        self.fm = fm

    def set_WorkspaceName(self, WorkspaceName):
        self.WorkspaceName = WorkspaceName

    def set_StorageAccountConnStr(self, StorageAccountConnStr):
        self.StorageAccountConnStr = StorageAccountConnStr

    def set_storage_url(self, storage_url):
        self.storage_url = storage_url

    def set_StorageAccountContainerName(self, StorageAccountContainerName):
        self.StorageAccountContainerName = StorageAccountContainerName

    def set_StorageAccountContainerRootPath(self, StorageAccountContainerRootPath):
        self.StorageAccountContainerRootPath = StorageAccountContainerRootPath

    def get_StorageAccountContainerName(self):
        return self.StorageAccountContainerName

    def set_OutputPath(self, OutputPath):
        self.OutputPath = OutputPath

    def set_CatalogGetInfoParameters(self, CatalogGetInfoParameters):
        self.CatalogGetInfoParameters = CatalogGetInfoParameters

    def set_CatalogGetModifiedParameters(self, CatalogGetModifiedParameters):
        self.CatalogGetModifiedParameters = CatalogGetModifiedParameters

    def set_ServicePrincipal(self, AppId, AppSecret, TenantId, Environment):
        self.cloud = get_cloud_profile(Environment)
        self.ServicePrincipal = {
            "AppId": AppId,
            "AppSecret": AppSecret,
            "TenantId": TenantId,
            "Environment": self.cloud.name,
        }

    def get_powerbi_url(self, rest_api: str) -> str:
        return urljoin(self.cloud.powerbi_api_root, rest_api)

    def get_fabric_url(self, rest_api: str) -> str:
        if not self.cloud.supports_fabric_api:
            raise RuntimeError(
                f"Fabric REST APIs are not enabled for CLOUD_ENVIRONMENT={self.cloud.name}"
            )
        return urljoin(self.cloud.fabric_api_root, rest_api)

    def set_ImpersonatedUserName(self, impersonatedUserName):
        self.impersonatedUserName = impersonatedUserName

    def set_capacity_metrics_dataset_id(self, capacity_metrics_dataset_id):
        self.capacity_metrics_dataset_id = capacity_metrics_dataset_id

    def set_Domains_cron(self, Domains_cron):
        self.Domains_cron = Domains_cron

    def set_FabricItems_cron(self, FabricItems_cron):
        self.FabricItems_cron = FabricItems_cron

    def set_Workspaces_cron(self, Workspaces_cron):
        self.Workspaces_cron = Workspaces_cron

    def set_GitConnections_cron(self, GitConnections_cron):
        self.GitConnections_cron = GitConnections_cron

    def set_Tags_cron(self, Tags_cron):
        self.Tags_cron = Tags_cron

    def set_DelegatedSettings_cron(self, DelegatedSettings_cron):
        self.DelegatedSettings_cron = DelegatedSettings_cron

    def set_WidelySharedLinks_cron(self, WidelySharedLinks_cron):
        self.WidelySharedLinks_cron = WidelySharedLinks_cron

    def set_FabricItemAccessPermissions_cron(self, cron: str) -> None:
        """Set the opt-in item access collector's UTC cron expression."""
        self.FabricItemAccessPermissions_cron = cron

    def set_FabricItemJobHistory_cron(self, cron: str) -> None:
        """Set the opt-in item job history collector's UTC cron expression."""
        self.FabricItemJobHistory_cron = cron

    def set_FabricItemDefinitions_cron(self, cron: str) -> None:
        """Set the opt-in definition collector's UTC cron expression."""
        self.FabricItemDefinitions_cron = cron

    def set_FabricConnections_cron(self, cron: str) -> None:
        """Set the opt-in connection inventory collector's UTC cron expression."""
        self.FabricConnections_cron = cron

    def set_FabricDeploymentPipelineOperations_cron(self, cron: str) -> None:
        """Set the opt-in deployment operation collector's UTC cron expression."""
        self.FabricDeploymentPipelineOperations_cron = cron

    def set_CapacityMetrics_cron(self, CapacityMetrics_cron):
        self.CapacityMetrics_cron = CapacityMetrics_cron

    def set_LakehouseName(self, LakehouseName):
        self.LakehouseName = LakehouseName

    def set_PathInLakehouse(self, PathInLakehouse):
        self.PathInLakehouse = PathInLakehouse

    def set_Activity_cron(self, Activity_cron):
        self.Activity_cron = Activity_cron

    def set_Apps_cron(self, Apps_cron):
        self.Apps_cron = Apps_cron

    def set_Catalog_cron(self, Catalog_cron):
        self.Catalog_cron = Catalog_cron

    def set_Graph_cron(self, Graph_cron):
        self.Graph_cron = Graph_cron

    def set_Tenant_cron(self, Tenant_cron):
        self.Tenant_cron = Tenant_cron

    def set_RefreshHistory_cron(self, RefreshHistory_cron):
        self.RefreshHistory_cron = RefreshHistory_cron

    def set_Refreshables_cron(self, Refreshables_cron):
        self.Refreshables_cron = Refreshables_cron

    def set_Gateway_cron(self, Gateway_cron):
        self.Gateway_cron = Gateway_cron

    def set_Capacity_cron(self, Capacity_cron):
        self.Capacity_cron = Capacity_cron

    def set_Roles_cron(self, Roles_cron):
        self.Roles_cron = Roles_cron

    def set_ApplicationModules(self, ApplicationModules):
        self.ApplicationModules = ApplicationModules

    def set_GraphExtractGroups(self, GraphExtractGroups):
        self.GraphExtractGroups = GraphExtractGroups

    def set_PowerBIAudienceGroupIds(self, PowerBIAudienceGroupIds):
        self.PowerBIAudienceGroupIds = PowerBIAudienceGroupIds

    def get_ServicePrincipal(self):
        return self.ServicePrincipal

    def get_LakehouseName(self):
        return self.LakehouseName

    def get_PathInLakehouse(self):
        return self.PathInLakehouse

    def set_exclude_personal_workspaces(self, exclude_personal_workspaces):
        self.exclude_personal_workspaces = exclude_personal_workspaces

    def set_exclude_inactive_workspaces(self, exclude_inactive_workspaces):
        self.exclude_inactive_workspaces = exclude_inactive_workspaces

    def get_cron(self, cron_name):
        if cron_name == "Activity":
            return self.Activity_cron
        elif cron_name == "Apps":
            return self.Apps_cron
        elif cron_name == "Catalog":
            return self.Catalog_cron
        elif cron_name == "Graph":
            return self.Graph_cron
        elif cron_name == "Tenant":
            return self.Tenant_cron
        elif cron_name == "RefreshHistory":
            return self.RefreshHistory_cron
        elif cron_name == "Refreshables":
            return self.Refreshables_cron
        elif cron_name == "Gateway":
            return self.Gateway_cron
        elif cron_name == "Capacity":
            return self.Capacity_cron
        elif cron_name == "Roles":
            return self.Roles_cron
        elif cron_name == "Domains":
            return self.Domains_cron
        elif cron_name == "FabricItems":
            return self.FabricItems_cron
        elif cron_name == "Workspaces":
            return self.Workspaces_cron
        elif cron_name == "CapacityMetrics":
            return self.CapacityMetrics_cron
        elif cron_name == "GitConnections":
            return self.GitConnections_cron
        elif cron_name == "Tags":
            return self.Tags_cron
        elif cron_name == "DelegatedSettings":
            return self.DelegatedSettings_cron
        elif cron_name == "WidelySharedLinks":
            return self.WidelySharedLinks_cron
        elif cron_name == "FabricItemAccessPermissions":
            return self.FabricItemAccessPermissions_cron
        elif cron_name == "FabricItemJobHistory":
            return self.FabricItemJobHistory_cron
        elif cron_name == "FabricItemDefinitions":
            return self.FabricItemDefinitions_cron
        elif cron_name == "FabricConnections":
            return self.FabricConnections_cron
        elif cron_name == "FabricDeploymentPipelineOperations":
            return self.FabricDeploymentPipelineOperations_cron
        else:
            return None

    def get_ApplicationModules(self):
        return self.ApplicationModules

    def convert_dt_str(self, date_time):
        """Convert a state timestamp string (or datetime) to a datetime.

        :param date_time: A ``%Y-%m-%dT%H:%M:%S.%fZ`` string (UTC) or a datetime;
            offset-aware datetimes are converted to UTC.
        :return: The parsed datetime as naive UTC.
        :raises ValueError: If the value cannot be parsed.
        """
        format = "%Y-%m-%dT%H:%M:%S.%fZ"

        if isinstance(date_time, datetime):
            if date_time.tzinfo is not None:
                # Normalise offset-aware values to naive UTC before formatting
                date_time = date_time.astimezone(timezone.utc).replace(tzinfo=None)
            date_time = date_time.strftime(format)

        try:
            datetime_str = datetime.strptime(date_time, format)
            return datetime_str
        except (ValueError, TypeError) as ve:
            self.logger.error(
                f"An exception occurred while converting the datetime value {date_time!r}: {ve}"
            )
            raise ValueError(f"Invalid datetime value {date_time!r}: {ve}") from ve

    @asynccontextmanager
    async def legacy_api_slot(self, url):
        """Wait outside concurrency slots; recheck cooldown after queued admission."""
        if self._api_semaphore is None:
            self._api_semaphore = asyncio.Semaphore(http_retry.max_concurrency())
        while True:
            await self._api_cooldowns.wait(url)
            await self._api_semaphore.acquire()
            if self._api_cooldowns.remaining(url) > 0:
                self._api_semaphore.release()
                continue
            try:
                yield
            finally:
                self._api_semaphore.release()
            return

    async def invokeAPI(
        self,
        rest_api: str,
        headers: http_retry.RequestHeaders | None = None,
        json: dict[str, Any] | None = None,
        request_gate: Callable[[], Awaitable[None]] | None = None,
        response_gate: Callable[[dict[str, Any], int], Awaitable[bool]] | None = None,
        definition_method: str | None = None,
    ) -> dict[str, Any]:
        """Invoke a REST API, honouring throttling.

        Requests share a concurrency cap (``API_MAX_CONCURRENCY``, default 16). Responses
        with HTTP 429, 503 or 504 are retried up to ``API_MAX_RETRIES`` times (default 3),
        waiting for ``Retry-After`` when present and exponential backoff otherwise. When
        retries are exhausted the last error dict is returned.

        :param rest_api: Relative (Power BI root) or absolute URL.
        :param headers: Static headers or a synchronous provider called before
            every attempt, after cooldown. Providers accept force_refresh=True
            for one cache-bypassing retry after HTTP 401.
        :param json: Optional JSON body; when set the request is a POST.
        :param request_gate: Optional asynchronous gate called before every HTTP
            attempt, including retries. Enables safe response handling, GET-only
            unless definition_method selects the restricted export transport.
        :param response_gate: Optional gated-response observer, called even on the
            final attempt. It must reserve any cooldown before returning; False
            defers retries to a later collection. Legacy requests instead share
            full server cooldowns per origin within this Context.
        :param definition_method: GET/POST for the allowlisted, retrieval-only
            definition/LRO transport. Requires a request gate and no JSON body.
        :return: The decoded JSON, or an error dict (see ``_error_result``).
        :raises ValueError: If a response observer lacks a request gate or a
            gated request contains a POST body.
        """
        if response_gate is not None and request_gate is None:
            raise ValueError("A response gate requires a request gate")
        if definition_method is not None and (
            definition_method not in ("GET", "POST")
            or request_gate is None
            or json is not None
        ):
            raise ValueError(
                "Definition retrieval requires a gated GET/POST without a body"
            )
        if self._api_semaphore is None:
            self._api_semaphore = asyncio.Semaphore(http_retry.max_concurrency())

        retries = http_retry.max_retries()
        attempt = 0
        auth_retried = False
        force_refresh = False
        url = self.get_powerbi_url(rest_api)
        while True:
            slot = (
                self._api_semaphore
                if request_gate is not None
                else self.legacy_api_slot(url)
            )
            async with slot:
                if request_gate is not None:
                    if json is not None:
                        raise ValueError("Gated requests must be GET requests")
                    await request_gate()
                request_headers = await http_retry.resolve_headers(
                    headers, force_refresh=force_refresh
                )
                force_refresh = False
                if request_gate is None and self._api_cooldowns.remaining(url) > 0:
                    continue
                if request_gate is not None:
                    if definition_method is None:
                        result = await self._safe_get(rest_api, request_headers)
                    else:
                        result = await self._safe_definition_request(
                            rest_api, request_headers, definition_method
                        )
                else:
                    result = await self._invoke_once(
                        rest_api, headers=request_headers, json=json
                    )

            status = (
                result.get("status")
                if isinstance(result, dict) and "ERROR" in result
                else None
            )
            status = _safe_http_status(status)
            server_delay = None
            if request_gate is None and status in http_retry.RETRYABLE_STATUSES:
                server_delay = http_retry.parse_retry_after(result.get("retryAfter"))
                if server_delay is not None:
                    self._api_cooldowns.reserve(url, server_delay)
            retry_allowed = True
            if response_gate is not None:
                retry_allowed = await response_gate(result, attempt)
            if (
                status == 401
                and callable(headers)
                and not auth_retried
                and retry_allowed
            ):
                auth_retried, force_refresh = True, True
                self.logger.warning("HTTP 401; reacquiring authentication once")
                continue
            if (
                status not in http_retry.RETRYABLE_STATUSES
                or attempt >= retries
                or not retry_allowed
            ):
                return result

            # Durable gates own their cooldown; legacy server waits happen at admission.
            delay = (
                0.0
                if response_gate is not None
                else http_retry.retry_delay(attempt, result.get("retryAfter"))
            )
            if request_gate is not None:
                self.logger.warning(
                    "Fabric GET HTTP %d; retrying in %.0fs (%d/%d)",
                    status,
                    delay,
                    attempt + 1,
                    retries,
                )
            else:
                self.logger.warning(
                    f"HTTP {status} from {rest_api[:120]}; retrying in {delay:.0f}s ({attempt + 1}/{retries})"
                )
            if server_delay is None:
                await asyncio.sleep(delay)
            attempt += 1

    async def _safe_get(
        self, url: str, headers: dict[str, str] | None
    ) -> dict[str, Any]:
        """Read gated JSON without redirects or response body/token diagnostics.

        :param url: Validated request URL, never included in diagnostics.
        :param headers: Authentication headers, never included in diagnostics.
        :return: A JSON object or safe error dictionary. Non-200 errors retain
            status and Retry-After and add an allowlisted errorCode, inspecting
            bodies up to 16 KiB with a one-byte oversize probe and a one-second
            diagnostic read budget.
        """
        async with (
            aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS),
                timeout=aiohttp.ClientTimeout(total=30, connect=10),
            ) as session,
            session.get(url, headers=headers, allow_redirects=False) as response,
        ):
            self.logger.info("Fabric GET: HTTP %d", response.status)
            if response.status != 200:
                error_code = await _fabric_response_error_code(response)
                self.logger.warning(
                    "Fabric GET failed: HTTP %d errorCode=%s",
                    response.status,
                    error_code,
                )
                return {
                    "ERROR": "HTTP request failed",
                    "status": response.status,
                    "retryAfter": response.headers.get("Retry-After"),
                    "errorCode": error_code,
                }
            try:
                result = await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                self.logger.warning(
                    "Fabric GET validation failed: HTTP %d "
                    "field=$ expected=JSON object observed=invalid JSON or content type",
                    response.status,
                )
                return {"ERROR": "Invalid JSON response"}
            if not isinstance(result, dict):
                log_validation_failure(
                    self.logger, "Fabric GET HTTP 200", "$", "object", result
                )
                return {"ERROR": "Expected JSON object"}
            return result

    async def _safe_definition_request(
        self, url: str, headers: dict[str, str] | None, method: str
    ) -> dict[str, Any]:
        """Retrieve definitions/LRO metadata without redirects or body diagnostics.

        Only documented definition exports and UUID operation polling/result URLs
        are allowed. A 202 body is intentionally not decoded. Header URLs are
        never followed; callers construct operation URLs from validated IDs.
        """
        guid = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
        root = r"https://api\.fabric\.microsoft\.com/v1/"
        routes = {
            "POST": root
            + rf"workspaces/{guid}/(?:notebooks/{guid}/getDefinition\?format=ipynb|dataPipelines/{guid}/getDefinition)",
            "GET": root + rf"operations/{guid}(?:/result)?",
        }
        if method not in routes or re.fullmatch(routes[method], url) is None:
            return {"ERROR": "Disallowed definition request URL"}
        async with (
            aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS),
                timeout=aiohttp.ClientTimeout(total=30, connect=10),
            ) as session,
            session.request(
                method, url, headers=headers, allow_redirects=False
            ) as response,
        ):
            self.logger.info("Fabric definition retrieval: HTTP %d", response.status)
            if response.status not in (200, 202):
                return {
                    "ERROR": "Definition request failed",
                    "status": response.status,
                    "retryAfter": response.headers.get("Retry-After"),
                    "errorCode": await _fabric_response_error_code(response),
                }
            body = {}
            if response.status == 200:
                try:
                    body = await response.json()
                except (ValueError, aiohttp.ContentTypeError, RecursionError):
                    return {"ERROR": "Invalid definition JSON"}
                if not isinstance(body, dict):
                    return {"ERROR": "Expected definition JSON object"}
            return {
                "status": response.status,
                "retryAfter": response.headers.get("Retry-After"),
                "operationId": response.headers.get("x-ms-operation-id"),
                "body": body,
            }

    async def _invoke_once(
        self, rest_api, headers=None, json=None
    ) -> Coroutine[dict[str, Any], None, None]:
        """
        Invoke a REST API once (no retry)
        url: str
        headers: dict
        body: dict
        """
        url = self.get_powerbi_url(rest_api)

        def _log(method, url, status, result=None):
            if result is None:
                count = "n/a"
            elif isinstance(result, dict):
                count = len(result.get("value", result))
            elif isinstance(result, list):
                count = len(result)
            else:
                count = "n/a"
            short_url = url if len(url) <= 120 else url[:117] + "..."
            print(f"[API] {method} {short_url} -> HTTP {status} | records: {count}")

        ## The conintuation Token redirects to your organization for Power BI instead of accessing
        ## the REST API the originated the call. Therefore, we need to intercept and call the
        ## using the continuation URI
        if "continuationToken" in rest_api:
            async with (
                aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS),
                    timeout=_TIMEOUT,
                ) as session,
                session.get(url=url, headers=headers) as response,
            ):
                if response.ok:
                    try:
                        result = await response.json(encoding="utf-8")
                        _log("GET", rest_api, response.status, result)
                        return result
                    except ValueError as e:
                        print(
                            f"[API] GET {rest_api} -> HTTP {response.status} | Error decoding JSON: {e}"
                        )
                        return await response.content
                else:
                    print(f"[API] GET {rest_api} -> HTTP {response.status} | ERROR")
                    return await _error_result(response)

        if json:
            async with (
                aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS),
                    timeout=_TIMEOUT,
                ) as session,
                session.post(url, headers=headers, json=json) as response,
            ):
                if response.ok:
                    try:
                        results = await response.json()
                        _log("POST", url, response.status, results)

                        if isinstance(results, dict) and "error" in results:
                            print("Error in results:", results["error"])
                            return results
                        elif isinstance(results, dict) and len(results) == 0:
                            print("No results found")
                            return {"message": "No results found"}
                        elif isinstance(results, dict) and len(results) > 0:
                            return results
                        else:
                            print("Unexpected results format:", results)
                            return {
                                "message": "Unexpected results format",
                                "results": results,
                            }
                    except ValueError as e:
                        print(
                            f"[API] POST {url} -> HTTP {response.status} | Error decoding JSON: {e}"
                        )
                        return await response.content
                    except (asyncio.TimeoutError, aiohttp.ClientError, TypeError) as e:
                        print(
                            f"[API] POST {url} -> HTTP {response.status} | Error: {e}"
                        )
                else:
                    print(f"[API] POST {url} -> HTTP {response.status} | ERROR")
                    return await _error_result(response)

        else:
            if not headers:
                url = rest_api
                async with (
                    aiohttp.ClientSession(
                        connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS),
                        timeout=_TIMEOUT,
                    ) as session,
                    session.get(url) as response,
                ):
                    if response.ok:
                        try:
                            result = await response.json(encoding="utf-8")
                            _log("GET", url, response.status, result)
                            return result
                        except ValueError as e:
                            print(
                                f"[API] GET {url} -> HTTP {response.status} | Error decoding JSON: {e}"
                            )
                            return await response.content
                    else:
                        print(f"[API] GET {url} -> HTTP {response.status} | ERROR")
                        return await _error_result(response)
            else:
                async with (
                    aiohttp.ClientSession(
                        connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS),
                        timeout=_TIMEOUT,
                    ) as session,
                    session.get(url, headers=headers) as response,
                ):
                    if response.ok:
                        result = await response.json(encoding="utf-8")
                        _log("GET", url, response.status, result)
                        return result
                    print(f"[API] GET {url} -> HTTP {response.status} | ERROR")
                    return await _error_result(response)
