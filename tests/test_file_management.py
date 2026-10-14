"""Read semantics: None only when the file is not found, otherwise errors propagate."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from azure.core.exceptions import ResourceNotFoundError

from env.utility.fabric import File_Table_Management
from env.utility.file_management import File_Management


def _ctx(**kw):
    base = dict(StorageAccountContainerName=None, StorageAccountContainerRootPath=None, OutputPath=None,
                LakehouseName=None, PathInLakehouse="p", logger=MagicMock())
    base.update(kw)
    return SimpleNamespace(**base)


def _fm(ctx):
    fm = File_Management()
    fm.context = ctx
    return fm


class FabricReadTests(unittest.IsolatedAsyncioTestCase):
    def _ftm(self, download):
        ftm = File_Table_Management()
        ftm.fsc = MagicMock()
        file_client = ftm.fsc.get_directory_client.return_value.get_file_client.return_value
        file_client.download_file = download
        return ftm

    async def test_returns_bytes(self):
        ftm = self._ftm(MagicMock(return_value=MagicMock(readall=MagicMock(return_value=b"abc"))))
        self.assertEqual(await ftm.read("dir", "f"), b"abc")
        ftm.fsc.get_directory_client.assert_called_once_with("dir")

    async def test_not_found_returns_none(self):
        ftm = self._ftm(MagicMock(side_effect=ResourceNotFoundError("gone")))
        self.assertIsNone(await ftm.read("dir", "f"))

    async def test_other_errors_are_reraised(self):
        ftm = self._ftm(MagicMock(side_effect=PermissionError("denied")))
        with self.assertRaises(PermissionError):
            await ftm.read("dir", "f")

    async def test_readall_failure_is_reraised(self):
        dl = MagicMock()
        dl.readall.side_effect = OSError("reset")
        ftm = self._ftm(MagicMock(return_value=dl))
        with self.assertRaises(OSError):
            await ftm.read("dir", "f")


class FileManagementReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_blob_content_returned_with_root_path(self):
        ctx = _ctx(StorageAccountContainerName="c", StorageAccountContainerRootPath="root")
        fm = _fm(ctx)
        fm.bfm = MagicMock(read_from_file=AsyncMock(return_value={"a": 1}))
        self.assertEqual(await fm.read(path="", file_name="state.yaml"), {"a": 1})
        fm.bfm.read_from_file.assert_awaited_once_with(blob_name="root/state.yaml")

    async def test_blob_without_root_path(self):
        fm = _fm(_ctx(StorageAccountContainerName="c"))
        fm.bfm = MagicMock(read_from_file=AsyncMock(return_value={}))
        await fm.read(path="a/", file_name="s.yaml")
        fm.bfm.read_from_file.assert_awaited_once_with(blob_name="a/s.yaml")

    async def test_blob_not_found_returns_none(self):
        fm = _fm(_ctx(StorageAccountContainerName="c"))
        fm.bfm = MagicMock(read_from_file=AsyncMock(return_value=None))
        self.assertIsNone(await fm.read(file_name="state.yaml"))

    async def test_blob_error_is_reraised_and_logged(self):
        ctx = _ctx(StorageAccountContainerName="c")
        fm = _fm(ctx)
        fm.bfm = MagicMock(read_from_file=AsyncMock(side_effect=RuntimeError("auth")))
        with self.assertRaises(RuntimeError):
            await fm.read(file_name="state.yaml")
        ctx.logger.error.assert_called()

    async def test_local_read_returns_text_and_none(self):
        fm = _fm(_ctx(OutputPath="/out"))
        fm.lfm = MagicMock(read=AsyncMock(side_effect=["text", None]))
        self.assertEqual(await fm.read(path="", file_name="state.yaml"), "text")
        self.assertIsNone(await fm.read(path="", file_name="state.yaml"))
        fm.lfm.read.assert_awaited_with(path="", file_name="state.yaml")

    async def test_local_error_is_reraised(self):
        fm = _fm(_ctx(OutputPath="/out"))
        fm.lfm = MagicMock(read=AsyncMock(side_effect=PermissionError("no")))
        with self.assertRaises(PermissionError):
            await fm.read(file_name="state.yaml")

    async def test_fabric_decodes_bytes(self):
        fm = _fm(_ctx(LakehouseName="lh"))
        fm.ftm = MagicMock(read=AsyncMock(return_value="héllo".encode()))
        self.assertEqual(await fm.read(path="", file_name="state.yaml"), "héllo")
        fm.ftm.read.assert_awaited_once_with(file_name="state.yaml", path="lh.Lakehouse/Files/p/")

    async def test_fabric_not_found_returns_none(self):
        fm = _fm(_ctx(LakehouseName="lh"))
        fm.ftm = MagicMock(read=AsyncMock(return_value=None))
        self.assertIsNone(await fm.read(file_name="state.yaml"))

    async def test_fabric_error_is_reraised(self):
        fm = _fm(_ctx(LakehouseName="lh"))
        fm.ftm = MagicMock(read=AsyncMock(side_effect=OSError("x")))
        with self.assertRaises(OSError):
            await fm.read(file_name="state.yaml")


if __name__ == "__main__":
    unittest.main()
