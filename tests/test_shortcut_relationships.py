"""Offline shortcut collection, minimized evidence and lineage integration."""

import copy
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from env import audit as audit_module
from env.audit import Audits
from env.config import build_audit
from env.modules import fabricshortcuts as collector
from env.utility import fabric_collection as gates
from env.utility.shortcut_relationships import (
    SHORTCUT_MODULE,
    shortcut_fingerprint,
    shortcut_records,
)
from notebooks import monitor_analytics as analytics
from notebooks import monitor_validation as validation
from notebooks.build_monitor_notebooks import generated_notebooks
from tests.fabric_helpers import WORKSPACE, CollectorTestCase, inventory, item
from tests.test_monitor_notebooks import run

PRIVATE = "SYNTHETIC_PRIVATE_SHORTCUT"
TARGET = "00000000-0000-0000-0000-000000000099"
EXECUTION = {
    "excludeWorkspaceIds": [],
    "sweepComplete": True,
    "sweepHealthy": True,
}


def shortcut(name="shortcut", kind="OneLake"):
    target = {"type": kind}
    if kind == "OneLake":
        target["oneLake"] = {
            "workspaceId": WORKSPACE,
            "itemId": TARGET,
            "path": "Tables/" + PRIVATE,
        }
    return {"path": "Files/" + PRIVATE, "name": name, "target": target}


class ShortcutEvidenceTests(unittest.TestCase):
    def test_external_locations_are_fingerprinted_without_query_tokens(self):
        value = shortcut(PRIVATE, "AmazonS3")
        value["target"]["amazonS3"] = {
            "location": "https://example.test/" + PRIVATE + "?sig=SECRET#fragment",
            "subpath": PRIVATE,
            "connectionId": TARGET,
            "credentials": {"secret": PRIVATE},
        }
        first = shortcut_records([value])
        value["target"]["amazonS3"]["location"] = (
            "https://example.test/" + PRIVATE + "?sig=DIFFERENT#other"
        )
        self.assertEqual(shortcut_records([value]), first)
        self.assertNotIn(PRIVATE, json.dumps(first))
        self.assertNotIn("SECRET", json.dumps(first))
        self.assertEqual(first[0]["targetStatus"], "external_reference")
        self.assertIsNone(first[0]["targetItemId"])
        self.assertEqual(
            first[0]["shortcutId"], shortcut_fingerprint(["Files/" + PRIVATE, PRIVATE])
        )

    def test_hidden_and_future_targets_remain_unresolved_not_empty(self):
        for kind, expected in (
            ("AmazonS3", "unavailable"),
            ("FutureStorage", "unsupported"),
        ):
            with self.subTest(kind=kind):
                result = shortcut_records([shortcut(kind=kind)])
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["targetStatus"], expected)
                self.assertIsNone(result[0]["targetItemId"])
                self.assertIsNone(result[0]["targetReference"])

    def test_conflicting_targets_and_malformed_onelake_ids_fail_closed(self):
        first = shortcut()
        second = copy.deepcopy(first)
        second["target"]["oneLake"]["itemId"] = WORKSPACE
        malformed = copy.deepcopy(first)
        malformed["target"]["oneLake"]["workspaceId"] = PRIVATE
        for values in ([first, second], [malformed]):
            with (
                self.subTest(values=values),
                self.assertRaises((ValueError, TypeError)),
            ):
                shortcut_records(values)
        self.assertEqual(len(shortcut_records([first, copy.deepcopy(first)])), 1)

    def test_lineage_is_opt_in_and_never_promotes_configuration_to_runtime(self):
        values = shortcut_records([shortcut(), shortcut("hidden", "AmazonS3")])
        documents = run(
            SHORTCUT_MODULE, 1, item(kind="Lakehouse"), values, execution=EXECUTION
        )
        self.assertEqual(analytics.transform(documents)["lineage_edges"], [])
        output = analytics.transform(documents, include_shortcuts=True)
        self.assertEqual(len(output["lineage_edges"]), 2)
        known = next(
            edge for edge in output["lineage_edges"] if edge["related_item_id"]
        )
        self.assertEqual(known["related_item_id"], TARGET)
        self.assertEqual(known["related_workspace_id"], WORKSPACE)
        self.assertEqual(known["resolution"], "configured_item")
        self.assertEqual(known["direction"], "association")
        self.assertTrue(
            all(edge["runtime_verified"] is False for edge in output["lineage_edges"])
        )
        self.assertEqual(output["lineage_resources"][0]["diagnostic_count"], 1)
        self.assertNotIn(PRIVATE, json.dumps(output))

    def test_failed_empty_invalid_and_unfinished_resources_are_distinct(self):
        for outcome in ("empty", "failed", "invalid", "unfinished"):
            with self.subTest(outcome=outcome):
                documents = run(
                    SHORTCUT_MODULE,
                    1,
                    item(kind="Lakehouse"),
                    [],
                    execution=EXECUTION,
                    complete=outcome != "failed",
                    success=outcome != "failed",
                )
                if outcome == "invalid":
                    documents[0]["value"]["requestPath"] += "/wrong"
                elif outcome == "unfinished":
                    documents[1]["value"].update(
                        finished=False, complete=False, resources=[], errors=[]
                    )
                documents = [
                    analytics.document(doc["path"], json.dumps(doc["value"]).encode())
                    for doc in documents
                ]
                output = analytics.transform(documents, include_shortcuts=True)
                self.assertEqual(output["lineage_edges"], [])
                if outcome in {"empty", "failed"}:
                    resource = output["lineage_resources"][0]
                    self.assertEqual(
                        resource["coverage_status"],
                        "success" if outcome == "empty" else "failed",
                    )
                    self.assertEqual(
                        resource["record_count"], 0 if outcome == "empty" else None
                    )
                else:
                    health = next(
                        row
                        for row in output["collection_health"]
                        if row["module"] == SHORTCUT_MODULE
                    )
                    self.assertEqual(health["coverage_status"], outcome)

    def test_validation_scope_change_is_not_comparable_even_without_new_files(self):
        baseline = {"tables": {}, "include_shortcuts": False}
        current = {"tables": {}, "include_shortcuts": True}
        self.assertEqual(
            validation.validation_compare(None, current, {}, baseline)[0]["status"],
            "NOT_COMPARABLE",
        )

    def test_generated_lineage_writer_requires_explicit_source_opt_in(self):
        artifact = generated_notebooks()["04_monitor_lineage.ipynb"]
        namespace = {"__name__": "fabric_notebook"}
        parameters = "".join(artifact["cells"][1]["source"])
        library = "".join(artifact["cells"][3]["source"])
        execute = "".join(artifact["cells"][5]["source"])
        exec(  # noqa: S102 - Trusted generated code.
            compile(parameters + "\n" + library, "embedded_shortcuts", "exec"),
            namespace,
        )
        documents = run(
            SHORTCUT_MODULE,
            1,
            item(kind="Lakehouse"),
            shortcut_records([shortcut()]),
            execution=EXECUTION,
        )
        read, publish = MagicMock(return_value=documents), MagicMock(return_value={})
        namespace.update(load_documents=read, publish=publish, spark=None)
        exec(compile(execute, "lineage_writer", "exec"), namespace)  # noqa: S102 - Trusted generated cell with mocked I/O.
        self.assertNotIn(SHORTCUT_MODULE, read.call_args.kwargs["source_prefixes"])
        self.assertEqual(publish.call_args.args[1]["lineage_edges"], [])
        namespace["INCLUDE_SHORTCUTS"] = True
        exec(compile(execute, "lineage_writer", "exec"), namespace)  # noqa: S102 - Trusted generated cell with mocked I/O.
        self.assertIn(SHORTCUT_MODULE, read.call_args.kwargs["source_prefixes"])
        self.assertEqual(len(publish.call_args.args[1]["lineage_edges"]), 1)

    def test_excluded_owner_or_manifest_scope_mismatch_quarantines_facts(self):
        for execution in (
            {**EXECUTION, "excludeWorkspaceIds": [WORKSPACE]},
            {**EXECUTION, "sweepComplete": False},
        ):
            with self.subTest(execution=execution):
                documents = run(
                    SHORTCUT_MODULE,
                    1,
                    item(kind="Lakehouse"),
                    shortcut_records([shortcut()]),
                    execution=execution,
                )
                output = analytics.transform(documents, include_shortcuts=True)
                self.assertEqual(output["lineage_edges"], [])
                health = next(
                    row
                    for row in output["collection_health"]
                    if row["module"] == SHORTCUT_MODULE
                )
                self.assertEqual(health["coverage_status"], "invalid")


class ShortcutCollectorTests(CollectorTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {"FABRIC_SHORTCUT_EXCLUDE_WORKSPACE_IDS": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def collect(self, context):
        scheduler = SimpleNamespace(
            **{
                **vars(gates.asyncio),
                "get_running_loop": lambda: SimpleNamespace(time=lambda: self.elapsed),
                "sleep": self.sleep,
            }
        )
        with (
            patch.object(collector, "asyncio", scheduler),
            patch.object(gates, "asyncio", scheduler),
        ):
            return await collector.main(context)

    def documents(self):
        return [
            analytics.document(path, json.dumps(value).encode())
            for path, value in self.files.items()
            if path.startswith(SHORTCUT_MODULE + "/")
            and path.rsplit("/", 1)[-1] not in {"request_gate.json", "progress.json"}
        ]

    async def test_admin_discovery_opt_out_and_paginated_non_admin_listing(self):
        allowed, excluded = item(kind="Lakehouse"), item(11, "Lakehouse", TARGET)
        context = self.context(
            inventory(allowed, token="a /+?"),
            inventory(excluded),
            {"value": [shortcut()], "continuationToken": "next /"},
            {"value": [shortcut("second", "AmazonS3")]},
        )
        with patch.dict(os.environ, {"FABRIC_SHORTCUT_EXCLUDE_WORKSPACE_IDS": TARGET}):
            self.assertTrue(await self.collect(context))
        urls = self.urls(context)
        self.assertTrue(urls[0].endswith("admin/items?type=Lakehouse"))
        self.assertTrue(urls[1].endswith("continuationToken=a%20%2F%2B%3F"))
        self.assertTrue(
            urls[2].endswith(
                f"workspaces/{WORKSPACE}/items/{allowed['itemId']}/shortcuts"
            )
        )
        self.assertTrue(urls[3].endswith("continuationToken=next%20%2F"))
        self.assertEqual(len(urls), 4)
        self.assertGreaterEqual(
            (self.request_times[1] - self.request_times[0]).total_seconds(), 23
        )
        resource = self.resources(SHORTCUT_MODULE)[-1]
        self.assertEqual(len(resource["records"]), 2)
        self.assertNotIn(PRIVATE, json.dumps(self.writes))
        output = analytics.transform(self.documents(), include_shortcuts=True)
        self.assertEqual(len(output["lineage_edges"]), 2)
        self.assert_finished(SHORTCUT_MODULE, True)

    async def test_denial_does_not_starve_next_item_and_empty_is_explicit(self):
        targets = [item(10, "Lakehouse"), item(11, "Lakehouse")]
        context = self.context(
            inventory(*targets), {"ERROR": "denied", "status": 403}, {"value": []}
        )
        self.assertFalse(await self.collect(context))
        resources = self.resources(SHORTCUT_MODULE)[1:]
        self.assertEqual(
            [resource["complete"] for resource in resources], [False, True]
        )
        self.assertNotIn("records", resources[0])
        self.assertEqual(resources[1]["records"], [])
        output = analytics.transform(self.documents(), include_shortcuts=True)
        item_resources = [row for row in output["lineage_resources"] if row["item_id"]]
        self.assertEqual(
            {row["item_id"]: row["record_count"] for row in item_resources},
            {targets[0]["itemId"]: None, targets[1]["itemId"]: 0},
        )
        self.assert_finished(SHORTCUT_MODULE, False)

    async def test_later_page_failure_never_exports_partial_relationships(self):
        context = self.context(
            inventory(item(kind="Lakehouse")),
            {"value": [shortcut()], "continuationToken": "next"},
            {"ERROR": "denied", "status": 403},
        )
        self.assertFalse(await self.collect(context))
        self.assertNotIn("records", self.resources(SHORTCUT_MODULE)[-1])
        self.assertEqual(
            analytics.transform(self.documents(), include_shortcuts=True)[
                "lineage_edges"
            ],
            [],
        )

    async def test_deferred_page_resumes_without_repeating_inventory_or_losing_rows(
        self,
    ):
        context = self.context(
            inventory(item(kind="Lakehouse")),
            {"value": [shortcut()], "continuationToken": "next"},
        )
        original = context._safe_get.side_effect

        async def slow_page(*args, **kwargs):
            result = await original(*args, **kwargs)
            if len(self.request_times) == 2:
                self.advance(80)
            return result

        context._safe_get.side_effect = slow_page
        self.assertFalse(await self.collect(context))
        saved = self.files[SHORTCUT_MODULE + "/progress.json"]
        self.assertEqual(saved["continuationToken"], "next")
        self.assertEqual(len(saved["records"]), 1)
        self.assertIn(SHORTCUT_MODULE, context.deferred_modules)
        resumed = self.context({"value": [shortcut("second")]})
        self.assertTrue(await self.collect(resumed))
        self.assertEqual(len(self.urls(resumed)), 1)
        self.assertTrue(
            self.urls(resumed)[0].endswith("shortcuts?continuationToken=next")
        )
        self.assertEqual(len(self.resources(SHORTCUT_MODULE)[-1]["records"]), 2)

    async def test_manifest_failure_replays_uncommitted_cursors(self):
        context = self.context(
            inventory(item(kind="Lakehouse")), {"value": [shortcut()]}
        )
        original = context.fm.save_snapshot.side_effect

        async def fail_manifest(path, name, value):
            if name == "manifest.json" and value["finished"]:
                raise RuntimeError("Synthetic storage failure")
            await original(path, name, value)

        context.fm.save_snapshot.side_effect = fail_manifest
        with self.assertRaisesRegex(RuntimeError, "Synthetic storage"):
            await self.collect(context)
        self.assertEqual(
            self.files[SHORTCUT_MODULE + "/progress.json"]["phase"], "inventory"
        )
        replay = self.context(
            inventory(item(kind="Lakehouse")), {"value": [shortcut()]}
        )
        self.assertTrue(await self.collect(replay))
        self.assertTrue(self.urls(replay)[0].endswith("admin/items?type=Lakehouse"))

    async def test_invalid_exclusions_or_progress_fail_before_requests(self):
        for saved, exclusions in (
            (None, PRIVATE),
            ({}, ""),
            ({"settings": {"excludeWorkspaceIds": []}}, ""),
        ):
            with self.subTest(saved=saved, exclusions=exclusions):
                self.files.clear()
                if saved is not None:
                    self.files[SHORTCUT_MODULE + "/progress.json"] = saved
                context = self.context()
                with (
                    patch.dict(
                        os.environ,
                        {"FABRIC_SHORTCUT_EXCLUDE_WORKSPACE_IDS": exclusions},
                    ),
                    self.assertRaises((ValueError, TypeError)),
                ):
                    await self.collect(context)
                context._safe_get.assert_not_awaited()
                context.clients["tenant"].get_headers.assert_not_called()
                context.fm.save_snapshot.assert_not_awaited()

    async def test_public_registration_cron_and_successful_checkpoint(self):
        audit = Audits()
        context = self.context(inventory())
        audit.context, audit.fm = context, context.fm
        old = "2025-12-01T00:00:00.000000Z"
        state = {SHORTCUT_MODULE: {"lastRun": old}}
        audit.fm.read = AsyncMock(return_value=state)
        audit.fm.save = AsyncMock()
        build_audit(
            settings={
                "TENANT_ID": "offline",
                "CLIENT_ID": "offline",
                "CLIENT_SECRET": "offline-placeholder",
                "APPLICATION_MODULES": "FabricShortcuts",
                "LAKEHOUSE_NAME": "OfflineLakehouse",
                "WORKSPACE_NAME": "OfflineWorkspace",
                "FABRICSHORTCUTS_CRON": "0 1 * * *",
            },
            audit=audit,
        )
        with (
            patch.object(audit, "_Audits__setup_clients"),
            patch.object(audit_module, "is_function_due", return_value=True) as due,
        ):
            self.assertTrue(await audit.run())
        self.assertEqual(due.call_args.args[0], "0 1 * * *")
        self.assertNotEqual(state[SHORTCUT_MODULE]["lastRun"], old)
