"""Deterministic collector harness: real request gates, mocked HTTP and storage."""

import copy
import importlib
import json
import os
import socket
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from env.context import Context
from tests.helpers import make_context

WORKSPACE = "00000000-0000-0000-0000-000000000001"
PIPELINE = "00000000-0000-0000-0000-000000000002"
ROOT = "https://api.fabric.microsoft.com/v1/"
PRIVATE_MARKER = "SYNTHETIC_PRIVATE_DIAGNOSTIC"
NAMES = (
    "FabricItemAccessPermissions",
    "FabricItemJobHistory",
    "FabricConnections",
    "FabricDeploymentPipelineOperations",
    "FabricItemDefinitions",
)


class PrivateDiagnosticValue:
    """An untrusted value whose repr and class name must never reach diagnostics."""

    def __repr__(self):
        return PRIVATE_MARKER


def item(number=10, kind="Notebook", workspace=WORKSPACE):
    return {
        "workspaceId": workspace,
        "itemId": f"00000000-0000-0000-0000-{number:012d}",
        "type": kind,
    }


def inventory(*items, token=None):
    result = {
        "itemEntities": [
            {"id": target["itemId"], **{k: target[k] for k in ("workspaceId", "type")}}
            for target in items
        ]
    }
    if token is not None:
        result["continuationToken"] = token
    return result


def job(target=None, status="InProgress", identity="job-1"):
    return {
        "id": identity,
        "itemId": (target or item())["itemId"],
        "jobType": "RunNotebook",
        "invokeType": "Manual",
        "status": status,
    }


def operation(status="Executing", identity="operation-1"):
    return {"id": identity, "type": "Deploy", "status": status}


def connection(identity="connection-1"):
    return {
        "id": identity,
        "displayName": "Test connection",
        "connectivityType": "ShareableCloud",
        "connectionDetails": {"type": "SQL"},
    }


def deny_network():
    """Block Internet sockets, preserving Unix sockets needed by asyncio."""
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex

    def guard(method):
        def connect(sock, address):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise AssertionError("Unit tests must not access the network")
            return method(sock, address)

        return connect

    return (
        patch.object(socket.socket, "connect", guard(original)),
        patch.object(socket.socket, "connect_ex", guard(original_ex)),
        patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("DNS is offline")
        ),
    )


class CollectorTestCase(unittest.IsolatedAsyncioTestCase):
    """Share persisted JSON across fresh Context instances, never live clients."""

    def setUp(self):
        self.now = datetime(2026, 1, 2, 3, 4, 5)
        self.elapsed = 0.0
        self.files = {}
        self.writes = []
        self.request_times = []
        self.sleep = AsyncMock(side_effect=self.advance)
        for patcher in (
            patch.dict(
                os.environ,
                {"API_MAX_RETRIES": "3", "API_MAX_RETRY_DELAY": "120", "DRY_RUN": ""},
            ),
            patch("env.context.utc_now", side_effect=lambda: self.now),
            patch(
                "env.utility.fabric_collection.utc_now", side_effect=lambda: self.now
            ),
            patch("env.utility.fabric_collection.asyncio.sleep", self.sleep),
            *deny_network(),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.elapsed += seconds

    def context(self, *responses):
        ctx = make_context()
        ctx.invokeAPI = Context.invokeAPI.__get__(ctx)
        tenant = MagicMock()
        tenant.get_headers.return_value = {"Authorization": "offline-placeholder"}
        ctx.clients["tenant"] = tenant

        async def request(*args, **kwargs):
            self.request_times.append(self.now)
            result = queue.pop(0)
            if isinstance(result, BaseException):
                raise result
            return copy.deepcopy(result)

        queue = list(responses)
        ctx._safe_get = AsyncMock(side_effect=request)

        async def read(path, name):
            return copy.deepcopy(self.files.get(path + name))

        async def save(path, name, value):
            self.files[path + name] = copy.deepcopy(value)
            self.writes.append((path + name, copy.deepcopy(value)))

        ctx.fm.read_snapshot = AsyncMock(side_effect=read)
        ctx.fm.save_snapshot = AsyncMock(side_effect=save)
        return ctx

    async def permissions(self, ctx):
        module = importlib.import_module("env.modules.fabricitemaccesspermissions")
        gate = importlib.import_module("env.utility.fabric_collection")
        # Scheduler deadlines and gate admission must share a clock, advanced
        # with UTC by mocked sleeps/requests. Leave the real event loop's clock
        # alone so asyncio timeout/debug bookkeeping is not distorted.
        scheduler = SimpleNamespace(
            **{
                **vars(gate.asyncio),
                "get_running_loop": lambda: SimpleNamespace(time=lambda: self.elapsed),
                "sleep": self.sleep,
            }
        )
        with (
            patch.object(module, "asyncio", scheduler),
            patch.object(gate, "asyncio", scheduler),
        ):
            return await module.main(ctx)

    def manifests(self, module):
        return [
            value
            for path, value in self.files.items()
            if path.startswith(module + "/") and path.endswith("/manifest.json")
        ]

    def resources(self, module):
        return [
            value
            for path, value in self.files.items()
            if path.startswith(module + "/") and "requestPath" in value
        ]

    def urls(self, ctx):
        return [call.args[0] for call in ctx._safe_get.await_args_list]

    def assert_finished(self, module, complete):
        manifest = self.manifests(module)[-1]
        self.assertIs(manifest["finished"], True)
        self.assertIs(manifest["complete"], complete)
        return manifest

    def assert_sanitized(self, logs, *diagnostics):
        rendered = "\n".join(logs) + json.dumps([diagnostics, self.files, self.writes])
        for private in (PRIVATE_MARKER, PrivateDiagnosticValue.__name__):
            self.assertNotIn(private, rendered)
