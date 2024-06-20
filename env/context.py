import msal
import aiohttp
from typing import Dict, Any, Coroutine
from datetime import datetime, timedelta


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
        self.ApplicationModules = None
        self.storage_url = None
        self.StorageAccountConnStr = None
        self.StorageAccountContainerName = None
        self.StorageAccountContainerRootPath = None
        self.OutputPath = None
        self.GraphExtractGroups = None
        self.WorkspaceName = None

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

    def set_Domains_cron(self, Domains_cron):
        self.Domains_cron = Domains_cron

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
        else:
            return None
    
    def get_ApplicationModules(self):
        return self.ApplicationModules

    def convert_dt_str(self, date_time):
        """
        Convert a datetime object to a string
        date_time: datetime object
        """
        format = "%Y-%m-%dT%H:%M:%S.%fZ"

        if isinstance(date_time, datetime):
            date_time = date_time.strftime(format)

        try:
            datetime_str = datetime.strptime(date_time, format)
            return datetime_str
        except ValueError as ve:
            print(f"An exception occurred while reading the file: {ve}")
            exit()
    
    
    def get_context(self, graph=False, tenant=False):
        """
        Get the access token for the Power BI API
        """
        try:
            sp = self.get_ServicePrincipal()
            tenant_id = sp['TenantId']
            client_id = sp['AppId']
            client_secret = sp['AppSecret']

        except Exception as e:
            print("An exception occurred while reading the file:", str(e))

        if graph:
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            scope = "https://graph.microsoft.com/.default"
        elif tenant:
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            scope = "https://api.fabric.microsoft.com/.default"  
        else:
            #authority = f"https://login.microsoftonline.com/{tenant_id}/oauth2/token?api-version=1.0"
            authority = f"https://login.microsoftonline.com/{tenant_id}"
            scope = "https://analysis.windows.net/powerbi/api/.default"
            

        # Create a ConfidentialClientApplication object
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority
        )

        scopes = [scope]
        
        # Acquire a token using client credentials
        try:
            result = app.acquire_token_for_client(scopes=scopes)
            if "access_token" in result:
                access_token = result["access_token"]
                # Use the access token to make API calls to Power BI
                headers = {'Authorization': f'Bearer {access_token}'}

                # TODO: Add your Power BI API calls here

            else:
                # If silent token acquisition fails, fallback to interactive authentication
                result = app.acquire_token_for_client(scopes=scopes)

                if "access_token" in result:
                    # TODO: Add your Power BI API calls here
                    access_token = result["access_token"]
                    # Use the access token to make API calls to Power BI
                    headers = {'Authorization': f'Bearer {access_token}'}

                else:
                    print(result.get("error_description", "Authentication failed."))

            return headers
        
        except Exception as ex:
            print(ex)

    async def invokeAPI(self, rest_api, headers=None, json=None)-> Coroutine[Dict[str,Any], None, None]:
        """
        Invoke a REST API
        url: str
        headers: dict
        body: dict
        """
        api_root = "https://api.powerbi.com/v1.0/myorg/"

        url = api_root + rest_api

        ## The conintuation Token redirects to your organization for Power BI instead of accessing
        ## the REST API the originated the call. Therefore, we need to intercept and call the 
        ## using the continuation URI
        if "continuationToken" in rest_api:
            async with aiohttp.ClientSession() as session:
                async with session.get(url=rest_api, headers=headers) as response:
                    return await response.json()

        if json:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=json) as response:
                    return await response.json()
        else:
            if not headers:
                url = rest_api
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        return await response.json(encoding='utf-8')
            else:

                p = rest_api.find("api.fabric.microsoft")

                url = api_root + rest_api
                if p > 0:
                    url = rest_api

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers) as response:
                        if response.ok:
                            return await response.json(encoding='utf-8')
                        return {"error" : "429 error thrown", "message": response}




        
