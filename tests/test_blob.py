"""Blob file management: set_context credential, asyncio.to_thread offloading, read/write behavior."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from env.utility import blob
from env.utility.blob import Blob_File_Management


def _context():
    return SimpleNamespace(storage_url="https://acct.blob.test", StorageAccountContainerName="cont")


class BlobFileManagementTests(unittest.IsolatedAsyncioTestCase):
    def _bfm(self):
        with patch.object(blob, "DefaultAzureCredential") as cred:
            bfm = Blob_File_Management()
            bfm.set_context(_context())
        self.cred = cred
        return bfm

    def test_set_context_binds_context_and_default_credential(self):
        bfm = self._bfm()
        self.cred.assert_called_once_with()
        self.assertEqual(bfm.context.storage_url, "https://acct.blob.test")
        self.assertIs(bfm.credentials, self.cred.return_value)

    def test_initial_state_is_empty(self):
        bfm = Blob_File_Management()
        self.assertIsNone(bfm.context)
        self.assertIsNone(bfm.credentials)

    async def test_write_uploads_via_to_thread_with_overwrite(self):
        bfm = self._bfm()
        client = MagicMock()
        seen = []
        real = blob.asyncio.to_thread

        async def spy(func, *args, **kwargs):
            seen.append(func)
            return await real(func, *args, **kwargs)

        with patch.object(blob, "BlobClient", return_value=client) as ctor, \
                patch.object(blob.asyncio, "to_thread", spy):
            await bfm.write_to_file("a/b.json", b"123")
        ctor.assert_called_once_with(account_url="https://acct.blob.test", container_name="cont",
                                     blob_name="a/b.json", credential=bfm.credentials)
        client.upload_blob.assert_called_once_with(data=b"123", overwrite=True)
        self.assertEqual(seen, [client.upload_blob])

    async def test_write_failure_is_reraised(self):
        bfm = self._bfm()
        client = MagicMock()
        client.upload_blob.side_effect = RuntimeError("denied")
        with patch.object(blob, "BlobClient", return_value=client):
            with self.assertRaises(RuntimeError):
                await bfm.write_to_file("x", b"1")

    async def test_read_downloads_via_to_thread_and_parses_yaml(self):
        bfm = self._bfm()
        client = MagicMock()
        client.download_blob.return_value.readall.return_value = b"raw"
        used = []
        real = blob.asyncio.to_thread

        async def spy(func, *args, **kwargs):
            used.append(func)
            return await real(func, *args, **kwargs)

        with patch.object(blob, "BlobClient", return_value=client), \
                patch.object(blob.asyncio, "to_thread", spy), \
                patch.object(blob.yaml, "safe_load", create=True, return_value={"k": 1}) as load:
            result = await bfm.read_from_file("state.yaml")
        self.assertEqual(result, {"k": 1})
        load.assert_called_once_with(b"raw")
        self.assertEqual(len(used), 1)
        client.download_blob.assert_called_once_with()

    async def test_read_not_found_returns_none(self):
        bfm = self._bfm()
        client = MagicMock()
        client.download_blob.side_effect = blob.ResourceNotFoundError("missing")
        with patch.object(blob, "BlobClient", return_value=client):
            self.assertIsNone(await bfm.read_from_file("state.yaml"))

    async def test_read_other_failure_is_reraised(self):
        bfm = self._bfm()
        client = MagicMock()
        client.download_blob.side_effect = RuntimeError("auth failure")
        with patch.object(blob, "BlobClient", return_value=client):
            with self.assertRaises(RuntimeError):
                await bfm.read_from_file("state.yaml")

    async def test_read_yaml_parse_failure_is_reraised(self):
        bfm = self._bfm()
        client = MagicMock()
        client.download_blob.return_value.readall.return_value = b"x"
        with patch.object(blob, "BlobClient", return_value=client), \
                patch.object(blob.yaml, "safe_load", create=True, side_effect=ValueError("bad yaml")):
            with self.assertRaises(ValueError):
                await bfm.read_from_file("state.yaml")


if __name__ == "__main__":
    unittest.main()
