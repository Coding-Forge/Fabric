import asyncio
import sys
import socket
import platform
import aiohttp
import logging
from typing import Dict, Any, Coroutine, Optional
from datetime import datetime, timedelta, timezone
from env.utility import http_retry
from env.utility.file_management import File_Management

# Format of the timestamps stored in state.yaml; the values are always UTC
STATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime (matches parsed state timestamps)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_stamp(moment: Optional[datetime] = None) -> str:
    """Format a UTC moment as a state timestamp.

    :param moment: Naive UTC datetime; defaults to now.
    :return: A ``%Y-%m-%dT%H:%M:%S.%fZ`` string.
    """
    return (moment or utc_now()).strftime(STATE_TIME_FORMAT)


# On Linux/WSL, aiohttp tries IPv6 first which causes SSL handshake timeouts.
# Force IPv4 on Linux. On Windows, aiohttp resolves correctly without this constraint.
_CONNECTOR_KWARGS = dict(family=socket.AF_INET) if platform.system() != "Windows" else {}
_TIMEOUT = aiohttp.ClientTimeout(total=300, connect=60)

async def _error_result(response: aiohttp.ClientResponse) -> Dict[str, Any]:
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
        self.CatalogGetInfoParameters = "lineage=true&datasourceDetails=true&getArtifactUsers=true&datasetSchema=true&datasetExpressions=true"
        self.CatalogGetModifiedParameters = "excludePersonalWorkspaces=false&excludeInActiveWorkspaces=true"
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
        self.ApplicationModules = None
        self.storage_url = None
        self.StorageAccountConnStr = None
        self.StorageAccountContainerName = None
        self.StorageAccountContainerRootPath = None
        self.OutputPath = None
        self.GraphExtractGroups = None
        self.WorkspaceName = None
        self.clients = {}
        self.fm = File_Management()
        self.current_state = None
        self.logging_level = logging.ERROR
        self.logger = logging.getLogger(__name__)
        self.all_workspaces = False
        self.exclude_personal_workspaces = True
        self.exclude_inactive_workspaces = True
        self.on_fabric = True
        self.capacity_metrics_dataset_id = None
        self.impersonatedUserName = None
        self._api_semaphore: Optional[asyncio.Semaphore] = None

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
            "CRITICAL": logging.CRITICAL
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

        fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        stdoutHandler.setFormatter(fmt)
        errHandler.setFormatter(fmt)

        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S', force=True, handlers=[stdoutHandler, errHandler]
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
        self.ServicePrincipal = {
            "AppId": AppId,
            "AppSecret": AppSecret,
            "TenantId": TenantId,
            "Environment": Environment
        }

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
            self.logger.error(f"An exception occurred while converting the datetime value {date_time!r}: {ve}")
            raise ValueError(f"Invalid datetime value {date_time!r}: {ve}") from ve
    
    
    async def invokeAPI(self, rest_api, headers=None, json=None)-> Coroutine[Dict[str,Any], None, None]:
        """Invoke a REST API, honouring throttling.

        Requests share a concurrency cap (``API_MAX_CONCURRENCY``, default 16). Responses
        with HTTP 429, 503 or 504 are retried up to ``API_MAX_RETRIES`` times (default 3),
        waiting for ``Retry-After`` when present and exponential backoff otherwise. When
        retries are exhausted the last error dict is returned.

        :param rest_api: Relative (Power BI root) or absolute URL.
        :param headers: Request headers.
        :param json: Optional JSON body; when set the request is a POST.
        :return: The decoded JSON, or an error dict (see ``_error_result``).
        """
        if self._api_semaphore is None:
            self._api_semaphore = asyncio.Semaphore(http_retry.max_concurrency())

        retries = http_retry.max_retries()
        attempt = 0
        while True:
            # The slot is released while sleeping so other requests can proceed
            async with self._api_semaphore:
                result = await self._invoke_once(rest_api, headers=headers, json=json)

            status = result.get("status") if isinstance(result, dict) and "ERROR" in result else None
            if status not in http_retry.RETRYABLE_STATUSES or attempt >= retries:
                return result

            delay = http_retry.retry_delay(attempt, result.get("retryAfter"))
            self.logger.warning(f"HTTP {status} from {rest_api[:120]}; retrying in {delay:.0f}s ({attempt + 1}/{retries})")
            await asyncio.sleep(delay)
            attempt += 1

    async def _invoke_once(self, rest_api, headers=None, json=None)-> Coroutine[Dict[str,Any], None, None]:
        """
        Invoke a REST API once (no retry)
        url: str
        headers: dict
        body: dict
        """
        api_root = "https://api.powerbi.com/v1.0/myorg/"

        url = rest_api if rest_api.startswith("http") else api_root + rest_api

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
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS), timeout=_TIMEOUT) as session:
                async with session.get(url=rest_api, headers=headers) as response:
                    if response.ok:
                        try:
                            result = await response.json(encoding='utf-8')
                            _log("GET", rest_api, response.status, result)
                            return result
                        except ValueError as e:
                            print(f"[API] GET {rest_api} -> HTTP {response.status} | Error decoding JSON: {e}")
                            return await response.content
                    else:
                        print(f"[API] GET {rest_api} -> HTTP {response.status} | ERROR")
                        return await _error_result(response)

        if json:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS), timeout=_TIMEOUT) as session:
                async with session.post(url, headers=headers, json=json) as response:
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
                                return {"message": "Unexpected results format", "results": results}
                        except ValueError as e:
                            print(f"[API] POST {url} -> HTTP {response.status} | Error decoding JSON: {e}")
                            return await response.content
                        except Exception as e:
                            print(f"[API] POST {url} -> HTTP {response.status} | Error: {e}")
                        finally:
                            if response.status == 429:
                                print("429 error thrown")
                                return await _error_result(response)
                            else:
                                pass
                    else:
                        print(f"[API] POST {url} -> HTTP {response.status} | ERROR")
                        return await _error_result(response)

                    
        else:
            if not headers:
                url = rest_api
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS), timeout=_TIMEOUT) as session:
                    async with session.get(url) as response:
                        if response.ok:
                            try:
                                result = await response.json(encoding='utf-8')
                                _log("GET", url, response.status, result)
                                return result
                            except ValueError as e:
                                print(f"[API] GET {url} -> HTTP {response.status} | Error decoding JSON: {e}")
                                return await response.content
                        else:
                            print(f"[API] GET {url} -> HTTP {response.status} | ERROR")
                            return await _error_result(response)
            else:

                url = rest_api if rest_api.startswith("http") else api_root + rest_api

                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(**_CONNECTOR_KWARGS), timeout=_TIMEOUT) as session:
                    async with session.get(url, headers=headers) as response:
                        if response.ok:
                            result = await response.json(encoding='utf-8')
                            _log("GET", url, response.status, result)
                            return result
                        print(f"[API] GET {url} -> HTTP {response.status} | ERROR")
                        return await _error_result(response)





        
