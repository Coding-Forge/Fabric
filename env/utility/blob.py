import asyncio
import yaml

from azure.storage.blob import BlobClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

class Blob_File_Management:

    def __init__(self):
        self.context = None
        self.credentials = None

    def set_context(self, context):
        self.context = context
        # DefaultAzureCredential works both locally (via AZURE_CLIENT_ID / AZURE_CLIENT_SECRET /
        # AZURE_TENANT_ID env vars or `az login`) and in Azure (via Managed Identity).
        self.credentials = DefaultAzureCredential()

    def _get_client(self, blob_name: str) -> BlobClient:
        return BlobClient(
            account_url=self.context.storage_url,
            container_name=self.context.StorageAccountContainerName,
            blob_name=blob_name,
            credential=self.credentials,
        )

    async def write_to_file(self, blob_name: str, content: bytes):
        """
        param blob_name: full blob path within the container
        param content: bytes to upload
        """
        try:
            blob_client = self._get_client(blob_name)
            # the SDK client is synchronous; run it off the event loop
            await asyncio.to_thread(blob_client.upload_blob, data=content, overwrite=True)
            print(f"[BLOB WRITE] Successfully wrote {len(content)} bytes to {blob_name}")
        except Exception as e:
            print(f"[BLOB WRITE] Failed to write {blob_name}: {type(e).__name__}: {e}")
            raise

    async def read_from_file(self, blob_name: str):
        try:
            blob_client = self._get_client(blob_name)
            print(f"[BLOB READ] Using URL auth: {self.context.storage_url} | blob: {blob_name}")
            raw = await asyncio.to_thread(lambda: blob_client.download_blob().readall())
            print(f"[BLOB READ] Read {len(raw)} bytes from {blob_name}")
            return yaml.safe_load(raw)
        except ResourceNotFoundError:
            print(f"[BLOB READ] Blob not found: {blob_name}")
            return None
        except Exception as e:
            print(f"[BLOB READ] Failed to read {blob_name}: {type(e).__name__}: {e}")
            raise

