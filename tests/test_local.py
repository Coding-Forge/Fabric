"""Local file management: set_context, off-loop writes via asyncio.to_thread, no os.chdir."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from env.utility import local
from env.utility.local import Local_File_Management


class LocalFileManagementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_set_context_defaults_root_to_output_path(self):
        lfm = Local_File_Management()
        ctx = SimpleNamespace(OutputPath="/some/out")
        lfm.set_context(ctx)
        self.assertIs(lfm.context, ctx)
        self.assertEqual(lfm.root_path, "/some/out")

    def test_set_context_keeps_explicit_root(self):
        lfm = Local_File_Management(root_path="/explicit")
        lfm.set_context(SimpleNamespace(OutputPath="/other"))
        self.assertEqual(lfm.root_path, "/explicit")

    def test_set_context_without_output_path_leaves_root_none(self):
        lfm = Local_File_Management()
        lfm.set_context(SimpleNamespace())
        self.assertIsNone(lfm.root_path)

    async def test_save_writes_bytes_and_creates_directories(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        await lfm.save(path="a/b/", file_name="f.json", content=b'{"x": 1}')
        with open(os.path.join(self.tmp.name, "a", "b", "f.json"), "rb") as fh:
            self.assertEqual(fh.read(), b'{"x": 1}')

    async def test_save_overwrites_existing_file(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        await lfm.save("d", "f.txt", b"first-longer")
        await lfm.save("d", "f.txt", b"second")
        with open(os.path.join(self.tmp.name, "d", "f.txt"), "rb") as fh:
            self.assertEqual(fh.read(), b"second")

    async def test_save_does_not_change_working_directory(self):
        before = os.getcwd()
        lfm = Local_File_Management(root_path=self.tmp.name)
        with patch.object(local.os, "chdir") as chdir:
            await lfm.save("sub/", "f.txt", b"x")
        chdir.assert_not_called()
        self.assertEqual(os.getcwd(), before)

    async def test_save_runs_write_via_asyncio_to_thread(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        real = local.asyncio.to_thread
        seen = []

        async def spy(func, *args, **kwargs):
            seen.append(func)
            return await real(func, *args, **kwargs)

        with patch.object(local.asyncio, "to_thread", spy):
            await lfm.save("s", "f.txt", b"data")
        self.assertEqual(len(seen), 1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "s", "f.txt")))

    async def test_save_without_root_uses_relative_path_from_cwd(self):
        old = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, old)
        lfm = Local_File_Management()
        await lfm.save("rel", "f.txt", b"x")
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "rel", "f.txt")))

    async def test_save_reraises_os_errors(self):
        blocker = os.path.join(self.tmp.name, "blocker")
        with open(blocker, "wb") as fh:
            fh.write(b"x")
        lfm = Local_File_Management(root_path=blocker)  # a file, so makedirs must fail
        with self.assertRaises(OSError):
            await lfm.save("child", "f.txt", b"x")

    async def test_read_returns_text(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        await lfm.save("a", "f.txt", "héllo".encode("utf-8"))
        self.assertEqual(await lfm.read("a", "f.txt"), "héllo")

    async def test_read_missing_file_returns_none(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        self.assertIsNone(await lfm.read("nope", "f.txt"))

    async def test_read_empty_file_returns_empty_string(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        await lfm.save("a", "e.txt", b"")
        self.assertEqual(await lfm.read("a", "e.txt"), "")

    async def test_read_other_os_error_is_reraised(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        os.makedirs(os.path.join(self.tmp.name, "a", "isdir"))
        with self.assertRaises(OSError):  # reading a directory is not "not found"
            await lfm.read("a", "isdir")

    async def test_read_invalid_utf8_is_reraised(self):
        lfm = Local_File_Management(root_path=self.tmp.name)
        await lfm.save("a", "bad.bin", b"\xff\xfe\x00")
        with self.assertRaises(UnicodeDecodeError):
            await lfm.read("a", "bad.bin")


if __name__ == "__main__":
    unittest.main()
