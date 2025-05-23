import os
import json

from azure.identity import ClientSecretCredential
from azure.storage.filedatalake import FileSystemClient, DataLakeDirectoryClient
from azure.storage.blob import BlobClient


class File_Table_Management:

    def __init__(self):
        
        self.sp = None
        self.tenant_id = None
        self.client_id = None
        self.client_secret = None
        self.workspace_name = None
        self.fsc = None
        self.context = None

    def set_context(self, context):
        self.context = context

        self.tenant_id = context.ServicePrincipal.get("TenantId")
        self.client_id = context.ServicePrincipal.get("AppId")
        self.client_secret = context.ServicePrincipal.get("AppSecret")
        self.workspace_name = context.WorkspaceName
        self.fsc = self.get_file_system_client()


    def __await__(self):
        # Call ls the constructor and returns the instance
        return self.get_file_system_client(
            client_id=self.client_id, 
            client_secret=self.client_secret,
            tenant_id=self.tenant_id,
            workspace_name=self.workspace_name).__await__()

    def get_file_system_client(self) -> FileSystemClient:
        cred = ClientSecretCredential(tenant_id=self.tenant_id,
                                    client_id=self.client_id,
                                    client_secret=self.client_secret)

        file_system_client = FileSystemClient(
            account_url="https://onelake.dfs.fabric.microsoft.com",
            file_system_name=self.workspace_name,
            credential=cred)

        return file_system_client

    async def create_file_system_client(self, service_client, file_system_name: str) -> FileSystemClient:
        file_system_client = service_client.get_file_system_client(file_system=file_system_name)
        return file_system_client

    def create_directory_client(self, path: str) -> DataLakeDirectoryClient:
        file_system_client = self.fsc
        directory_client = file_system_client.get_directory_client(path)
        return directory_client

    async def list_directory_contents(self, file_system_client: FileSystemClient, directory_name: str):
        paths = file_system_client.get_paths(path=directory_name)
        for path in paths:
            print(path.name + '\n')

    async def create_directory(self, directory_name: str) -> DataLakeDirectoryClient:
        file_system_client = self.fsc
        directory_client = file_system_client.create_directory(directory_name)

        return directory_client            

    async def upload_file_to_directory(self, directory_client: DataLakeDirectoryClient, local_path: str, file_name: str):
        file_client = directory_client.get_file_client(file_name)
        
        if await file_client.exists():
            print(f"File '{file_name}' already exists.")
            return
        
        with open(file=os.path.join(local_path, file_name), mode="rb") as data:
            await file_client.upload_data(data, overwrite=True)

    # needs to be synchronous as multiple functions rely on the download to complete before continuing
    def download_file_from_directory(self, directory_client: DataLakeDirectoryClient, local_path: str, file_name: str):
        file_client = directory_client.get_file_client(file_name)

        with open(file=os.path.join(local_path, file_name), mode="wb") as local_file:
            download = file_client.download_file()
            local_file.write(download.readall())
            local_file.close()

    async def read(self, path:str, file_name: str):
        dc = self.fsc.get_directory_client(path)
        file_client = dc.get_file_client(file_name)
        try:
            download = file_client.download_file()
            return download.readall()
        except Exception as e:
            print(f"File not found: {e}")
            return None

    async def write_json_to_file(self, path:str, file_name: str, json_data):
        
        json_bytes = json_data
        directory = path
        file_path = os.path.join(directory, file_name)
        file_path.replace("//", "/")

        os.makedirs(directory, exist_ok=True)

        if self.context.on_fabric:
            with open(file_path, "wb") as file:
                file.write(json_bytes)
        else:
            dc = self.fsc.get_directory_client(path)
            file_client = dc.get_file_client(file_name)
            file_client.upload_data(json_bytes, overwrite=True)


