import os
import json
import logging
from typing import Dict, Any, Coroutine
from dotenv import load_dotenv, dotenv_values
from datetime import datetime, timedelta
import yaml

from azure.storage.blob import BlobClient, BlobServiceClient
from azure.identity import ClientSecretCredential

logging.basicConfig(filename='myapp.log', level=logging.INFO)


class Blob_File_Management:

    def __init__(self):

        self.context = None
        self.credentials = None
        self.tenant_id = None
        self.client_id = None
        self.client_secret = None
        self.workspace_name = None

    def set_context(self, context):
        self.context = context

        self.tenant_id = context.ServicePrincipal.get("TenantId")
        self.client_id = context.ServicePrincipal.get("AppId")
        self.client_secret = context.ServicePrincipal.get("AppSecret")
        self.workspace_name = context.WorkspaceName

        self.credentials = ClientSecretCredential(
            client_id=self.client_id,
            client_secret=self.client_secret,
            tenant_id=self.tenant_id
        )

    def read_from_file(self, blob_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.app_settings.get("StorageAccountConnStr"))
        blob_client = blob_service_client.get_blob_client(container=self.container_name, blob=blob_name)
        blob_content = blob_client.download_blob().readall()
        return blob_client

    async def write_to_file(self, blob_name, content):
        """
        param blob_name is a string of the path where you want to save your file
        param content is a byte variable that can be uploaded to blob storage
        """

        conn_str = self.context.StorageAccountConnStr

        if conn_str is None:
            blob_client = BlobClient(
                account_url=self.context.storage_url, 
                container_name=self.context.StorageAccountContainerName,
                blob_name=blob_name, 
                credential=self.credentials,
                
            )

        else:
            blob_client = BlobClient.from_connection_string(
                conn_str=conn_str,
                container_name=self.context.StorageAccountContainerName,
                blob_name=blob_name,
            )            

        blob_client.upload_blob(data=content, overwrite=True)

    async def read_from_file(self, blob_name:str):
        conn_str = self.context.StorageAccountConnStr

        if conn_str is None:
            blob_client = BlobClient(
                account_url=self.context.storage_url, 
                container_name=self.context.StorageAccountContainerName, 
                blob_name=blob_name, 
                credential=self.credentials,
                
            )

        else:
            blob_client = BlobClient.from_connection_string(
                conn_str=conn_str,
                container_name=self.context.StorageAccountContainerName,
                blob_name=blob_name,
            )            

        data = blob_client.download_blob()
        response = yaml.safe_load(data.readall())
        return response
