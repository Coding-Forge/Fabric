"""env/version.py: version lookup from the repo-root VERSION file."""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import monitor
from env import version
from env.version import UNKNOWN_VERSION, get_version

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class GetVersionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "VERSION"

    def _get(self, path=None):
        with patch.object(version, "VERSION_FILE", path or self.path):
            return get_version()

    def test_reads_and_strips_version(self):
        self.path.write_text("  1.2.3 \n\n", encoding="utf-8")
        self.assertEqual(self._get(), "1.2.3")

    def test_missing_file_returns_unknown(self):
        self.assertEqual(self._get(self.path.with_name("nope")), UNKNOWN_VERSION)

    def test_empty_file_returns_unknown(self):
        self.path.write_text("", encoding="utf-8")
        self.assertEqual(self._get(), UNKNOWN_VERSION)

    def test_whitespace_only_file_returns_unknown(self):
        self.path.write_text(" \n\t\n", encoding="utf-8")
        self.assertEqual(self._get(), UNKNOWN_VERSION)

    def test_invalid_utf8_returns_unknown(self):
        self.path.write_bytes(b"\xff\xfe\xfa1.0.0")
        self.assertEqual(self._get(), UNKNOWN_VERSION)

    def test_unreadable_file_returns_unknown(self):
        self.path.write_text("1.0.0", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            self.assertEqual(self._get(), UNKNOWN_VERSION)

    def test_directory_instead_of_file_returns_unknown(self):
        self.assertEqual(self._get(self.path.parent), UNKNOWN_VERSION)

    def test_unknown_constant_value(self):
        self.assertEqual(UNKNOWN_VERSION, "unknown")


class RepoVersionFileTests(unittest.TestCase):
    def test_version_file_points_at_repo_root(self):
        self.assertEqual(version.VERSION_FILE.name, "VERSION")
        self.assertTrue(version.VERSION_FILE.is_file())

    def test_real_version_is_semantic(self):
        value = get_version()
        self.assertRegex(value, SEMVER)


class StartupLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_logs_version(self):
        async def _run():
            return None

        audit = MagicMock()
        audit.run = MagicMock(side_effect=_run)
        env = {
            "APPLICATION_MODULES": "Activity",
            "LAKEHOUSE_NAME": "lh",
            "WORKSPACE_NAME": "ws",
            "TENANT_ID": "t",
            "CLIENT_ID": "c",
            "CLIENT_SECRET": "s",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(monitor, "Audits", return_value=audit),
            patch.object(monitor, "get_version", return_value="9.8.7"),
            self.assertLogs(monitor.logger, level="INFO") as logs,
        ):
            await monitor.main()
        self.assertIn(
            "Starting Fabric Monitor run (version 9.8.7)",
            [r.getMessage() for r in logs.records],
        )


if __name__ == "__main__":
    unittest.main()
