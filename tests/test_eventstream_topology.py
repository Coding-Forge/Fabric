"""Offline Eventstream topology, transport, provenance and notebook contracts."""

import copy
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from env import audit as audit_module
from env.audit import Audits
from env.config import build_audit
from env.modules import fabriceventstreamtopology as collector
from env.utility import fabric_collection as gates
from env.utility.eventstream_topology import (
    EVENTSTREAM_MODULE,
    eventstream_hash,
    eventstream_topology,
    validate_eventstream_topology,
)
from notebooks import monitor_analytics as analytics
from notebooks import monitor_validation as validation
from notebooks import monitor_visualizations as visualizations
from notebooks.build_monitor_notebooks import generated_notebooks
from tests.fabric_helpers import WORKSPACE, CollectorTestCase, inventory, item
from tests.test_monitor_notebooks import run

PRIVATE = "SYNTHETIC_PRIVATE_EVENTSTREAM"
TARGET = "00000000-0000-0000-0000-000000000099"
EXECUTION = {
    "excludeWorkspaceIds": [],
    "sweepComplete": True,
    "sweepHealthy": True,
    "sweepId": "1" * 32,
}


def topology():
    return {
        "compatibilityLevel": "1.1",
        "sources": [
            {
                "id": item(101)["itemId"],
                "name": PRIVATE + "_source",
                "type": "AzureEventHub",
                "status": "Running",
                "properties": {
                    "dataConnectionId": TARGET,
                    "credential": PRIVATE,
                    "connectionString": PRIVATE,
                    "topic": PRIVATE,
                },
            }
        ],
        "streams": [
            {
                "id": item(102)["itemId"],
                "name": PRIVATE + "_stream",
                "type": "DefaultStream",
                "inputNodes": [{"name": PRIVATE + "_source"}],
                "properties": {"schema": PRIVATE},
            }
        ],
        "operators": [
            {
                "name": PRIVATE + "_filter",
                "type": "Filter",
                "inputNodes": [{"name": PRIVATE + "_stream"}],
                "properties": {"conditions": PRIVATE, "query": PRIVATE},
                "inputSchemas": [{"column": PRIVATE}],
            }
        ],
        "destinations": [
            {
                "id": item(103)["itemId"],
                "name": PRIVATE + "_destination",
                "type": "Lakehouse",
                "status": "Running",
                "inputNodes": [{"name": PRIVATE + "_filter"}],
                "properties": {
                    "workspaceId": WORKSPACE,
                    "itemId": TARGET,
                    "deltaTable": PRIVATE,
                    "unknown": PRIVATE,
                },
                "error": {"message": PRIVATE},
            }
        ],
    }


def documents(body=None, number=1, **kwargs):
    return run(
        EVENTSTREAM_MODULE,
        number,
        item(kind="Eventstream"),
        [eventstream_topology(topology() if body is None else body)],
        execution=copy.deepcopy(EXECUTION),
        **kwargs,
    )


class EventstreamEvidenceTests(unittest.TestCase):
    def test_nodes_operators_adjacency_and_targets_are_preserved_without_payloads(self):
        graph = eventstream_topology(topology())
        self.assertEqual(len(graph["nodes"]), 4)
        self.assertEqual(len(graph["links"]), 3)
        self.assertTrue(all(link["resolved"] for link in graph["links"]))
        self.assertNotIn(PRIVATE, json.dumps(graph))
        nodes = {node["role"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["destination"]["targetItemId"], TARGET)
        self.assertEqual(nodes["destination"]["targetWorkspaceId"], WORKSPACE)
        self.assertEqual(
            nodes["source"]["connectionReference"], eventstream_hash(TARGET)
        )
        self.assertEqual(nodes["operator"]["targetStatus"], "not_applicable")
        self.assertIn(
            {
                "fromNode": nodes["operator"]["nodeId"],
                "toNode": nodes["destination"]["nodeId"],
                "resolved": True,
            },
            graph["links"],
        )
        self.assertEqual(graph["diagnostics"], [])

    def test_missing_containers_are_not_successful_empty_topology(self):
        for body in (
            {},
            {"sources": []},
            {**topology(), "operators": None},
            {**topology(), "continuationToken": "next"},
        ):
            with self.subTest(body=body), self.assertRaises((ValueError, TypeError)):
                eventstream_topology(body)
        empty = eventstream_topology(
            {key: [] for key in ("sources", "streams", "operators", "destinations")}
        )
        self.assertEqual(empty["nodes"], [])
        self.assertEqual(empty["links"], [])

    def test_missing_and_dangling_inputs_are_diagnostics_not_guessed_links(self):
        body = topology()
        del body["streams"][0]["inputNodes"]
        body["operators"][0]["inputNodes"] = [{"name": PRIVATE + "_absent"}]
        graph = eventstream_topology(body)
        reasons = {diagnostic["reason"] for diagnostic in graph["diagnostics"]}
        self.assertEqual(
            reasons, {"missing_topology_inputs", "unresolved_topology_input"}
        )
        self.assertEqual(sum(not link["resolved"] for link in graph["links"]), 1)
        self.assertNotIn(PRIVATE, json.dumps(graph))

    def test_explicit_target_identity_never_infers_workspace_or_unknown_semantics(self):
        for mutation, expected in (
            ("missing_workspace", "unresolved"),
            ("future_type", "unsupported"),
        ):
            with self.subTest(mutation=mutation):
                body = topology()
                destination = body["destinations"][0]
                if mutation == "missing_workspace":
                    del destination["properties"]["workspaceId"]
                else:
                    destination["type"] = "FutureDestination"
                graph = eventstream_topology(body)
                target = next(
                    node for node in graph["nodes"] if node["role"] == "destination"
                )
                self.assertEqual(target["targetStatus"], expected)
                self.assertIsNone(target["targetItemId"])
                self.assertIsNone(target["targetWorkspaceId"])

    def test_ambiguous_names_duplicate_ids_and_malformed_targets_fail_closed(self):
        for mutation in (
            "duplicate_name",
            "duplicate_id",
            "bad_target",
            "bad_inputs",
            "bad_properties",
        ):
            body = topology()
            if mutation == "duplicate_name":
                body["operators"][0]["name"] = body["sources"][0]["name"]
            elif mutation == "duplicate_id":
                body["destinations"][0]["id"] = body["sources"][0]["id"]
            elif mutation == "bad_target":
                body["destinations"][0]["properties"]["itemId"] = PRIVATE
            elif mutation == "bad_inputs":
                body["streams"][0]["inputNodes"] = [PRIVATE]
            else:
                body["sources"][0]["properties"] = PRIVATE
            with (
                self.subTest(mutation=mutation),
                self.assertRaises((ValueError, TypeError)),
            ):
                eventstream_topology(body)

    def test_minimized_evidence_is_revalidated_not_trusted(self):
        for mutation in (
            "extra_payload",
            "unknown_link",
            "false_target",
            "missing_diagnostic",
        ):
            graph = eventstream_topology(topology())
            if mutation == "extra_payload":
                graph["nodes"][0]["payload"] = PRIVATE
            elif mutation == "unknown_link":
                graph["links"][0]["fromNode"] = "0" * 64
            elif mutation == "false_target":
                node = next(
                    node for node in graph["nodes"] if node["role"] == "operator"
                )
                node.update(
                    targetItemId=TARGET,
                    targetWorkspaceId=WORKSPACE,
                    targetStatus="configured_item",
                )
            else:
                node = next(
                    node for node in graph["nodes"] if node["role"] == "destination"
                )
                node.update(
                    targetItemId=None, targetWorkspaceId=None, targetStatus="unresolved"
                )
            with (
                self.subTest(mutation=mutation),
                self.assertRaises((ValueError, TypeError)),
            ):
                validate_eventstream_topology(graph)

    def test_opt_in_adds_configuration_not_runtime_facts_or_new_tables(self):
        raw = documents()
        self.assertEqual(analytics.transform(raw)["lineage_edges"], [])
        output = analytics.transform(raw, include_eventstream_topology=True)
        edges = output["lineage_edges"]
        self.assertEqual(len(edges), 9)  # Four memberships, three inputs, two targets.
        self.assertEqual(
            sum(edge["relation_type"] == "topology_input" for edge in edges), 3
        )
        self.assertTrue(all(edge["runtime_verified"] is False for edge in edges))
        self.assertEqual(
            {edge["evidence_type"] for edge in edges}, {"eventstream_configuration"}
        )
        self.assertEqual(output["lineage_resources"][0]["record_count"], 9)
        self.assertNotIn(PRIVATE, json.dumps(output))
        self.assertEqual(set(output), set(analytics.SCHEMAS))

    def test_failed_unfinished_invalid_and_empty_are_distinct(self):
        for outcome in ("failed", "unfinished", "invalid", "empty"):
            raw = documents()
            resource, manifest = raw[0]["value"], raw[1]["value"]
            if outcome == "failed":
                resource.update(complete=False, error="Incomplete")
                del resource["records"]
                manifest.update(complete=False, errors=["Incomplete"])
                manifest["resources"][0]["complete"] = False
            elif outcome == "unfinished":
                manifest.update(complete=False, finished=False, resources=[], errors=[])
            elif outcome == "invalid":
                resource["requestPath"] += "/wrong"
            else:
                resource["records"] = [
                    eventstream_topology(
                        {
                            key: []
                            for key in (
                                "sources",
                                "streams",
                                "operators",
                                "destinations",
                            )
                        }
                    )
                ]
            raw = [
                analytics.document(doc["path"], json.dumps(doc["value"]).encode())
                for doc in raw
            ]
            output = analytics.transform(raw, include_eventstream_topology=True)
            self.assertEqual(output["lineage_edges"], [])
            if outcome in {"failed", "empty"}:
                coverage = output["lineage_resources"][0]
                self.assertEqual(
                    coverage["coverage_status"],
                    "failed" if outcome == "failed" else "success",
                )
                self.assertEqual(
                    coverage["record_count"], None if outcome == "failed" else 0
                )
            else:
                health = next(
                    row
                    for row in output["collection_health"]
                    if row["module"] == EVENTSTREAM_MODULE
                )
                self.assertEqual(health["coverage_status"], outcome)

    def test_scope_and_sweep_changes_cannot_reuse_old_configuration(self):
        modes = []
        for sweep, excluded in (("1" * 32, []), ("2" * 32, []), ("2" * 32, [TARGET])):
            raw = documents()
            raw[1]["value"]["execution"].update(
                sweepId=sweep, excludeWorkspaceIds=excluded
            )
            raw = [
                analytics.document(doc["path"], json.dumps(doc["value"]).encode())
                for doc in raw
            ]
            output = analytics.transform(raw, include_eventstream_topology=True)
            modes.append(output["lineage_edges"][0]["mode"])
        self.assertEqual(len(set(modes)), 3)
        baseline = {"tables": {}}
        current = {"tables": {}, "include_eventstream_topology": True}
        self.assertEqual(
            validation.validation_compare(None, current, {}, baseline)[0]["status"],
            "NOT_COMPARABLE",
        )

    def test_graph_draws_declared_internal_links_separately_from_membership(self):
        edges = analytics.transform(documents(), include_eventstream_topology=True)[
            "lineage_edges"
        ]
        frame, pyplot, axis = MagicMock(), MagicMock(), MagicMock()
        frame.orderBy.return_value.limit.return_value.collect.return_value = edges
        pyplot.subplots.return_value = (None, axis)
        with patch.dict(
            "sys.modules",
            {
                "matplotlib": SimpleNamespace(pyplot=pyplot),
                "matplotlib.pyplot": pyplot,
                "matplotlib.lines": SimpleNamespace(Line2D=MagicMock()),
            },
        ):
            visualizations.graph_lineage(frame, 20)
        styles = [call.kwargs["arrowprops"] for call in axis.annotate.call_args_list]
        self.assertEqual(sum(style["arrowstyle"] == "->" for style in styles), 3)
        self.assertEqual(sum(style["color"] == "tab:purple" for style in styles), 3)
        self.assertEqual(sum(style["color"] == "tab:gray" for style in styles), 4)
        self.assertNotIn(PRIVATE, str(axis.text.call_args_list))

    def test_generated_writer_and_orchestrator_pass_explicit_opt_in(self):
        artifacts = generated_notebooks()
        artifact = artifacts["04_monitor_lineage.ipynb"]
        namespace = {"__name__": "fabric_notebook"}
        parameters = "".join(artifact["cells"][1]["source"])
        library = "".join(artifact["cells"][3]["source"])
        execute = "".join(artifact["cells"][5]["source"])
        exec(  # noqa: S102 - Trusted generated code.
            compile(parameters + "\n" + library, "embedded_topology", "exec"), namespace
        )
        read, publish = MagicMock(return_value=documents()), MagicMock(return_value={})
        namespace.update(load_documents=read, publish=publish, spark=None)
        exec(compile(execute, "topology_writer", "exec"), namespace)  # noqa: S102 - Trusted generated code with mocked I/O.
        self.assertNotIn(EVENTSTREAM_MODULE, read.call_args.kwargs["source_prefixes"])
        self.assertEqual(publish.call_args.args[1]["lineage_edges"], [])
        namespace["INCLUDE_EVENTSTREAM_TOPOLOGY"] = True
        exec(compile(execute, "topology_writer", "exec"), namespace)  # noqa: S102 - Trusted generated code with mocked I/O.
        self.assertIn(EVENTSTREAM_MODULE, read.call_args.kwargs["source_prefixes"])
        self.assertEqual(len(publish.call_args.args[1]["lineage_edges"]), 9)

        calls = MagicMock(return_value="")
        namespace = {
            "notebookutils": SimpleNamespace(notebook=SimpleNamespace(run=calls)),
            "spark": MagicMock(),
            "display": MagicMock(),
        }
        config, execute = [
            "".join(cell["source"])
            for cell in artifacts["nb_orchestrator.ipynb"]["cells"]
            if cell["cell_type"] == "code"
        ]
        exec(compile(config, "orchestrator_config", "exec"), namespace)  # noqa: S102 - Trusted generated code.
        namespace["INCLUDE_EVENTSTREAM_TOPOLOGY"] = True
        exec(compile(execute, "orchestrator_run", "exec"), namespace)  # noqa: S102 - Trusted generated code with mocked Fabric APIs.
        self.assertEqual(calls.call_count, 19)
        self.assertTrue(
            all(
                call.args[2]["INCLUDE_EVENTSTREAM_TOPOLOGY"]
                for call in calls.call_args_list
            )
        )


class EventstreamCollectorTests(CollectorTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.dict(
            os.environ, {"FABRIC_EVENTSTREAM_EXCLUDE_WORKSPACE_IDS": ""}
        )
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
            if path.startswith(EVENTSTREAM_MODULE + "/")
            and path.rsplit("/", 1)[-1] not in {"request_gate.json", "progress.json"}
        ]

    async def test_admin_inventory_pagination_exclusions_and_object_response(self):
        target = item(kind="Eventstream")
        context = self.context(
            inventory(target, token="a /+?"),
            inventory(item(11, "Eventstream", TARGET)),
            topology(),
        )
        with patch.dict(
            os.environ, {"FABRIC_EVENTSTREAM_EXCLUDE_WORKSPACE_IDS": TARGET}
        ):
            self.assertTrue(await self.collect(context))
        urls = self.urls(context)
        self.assertTrue(urls[0].endswith("admin/items?type=Eventstream"))
        self.assertTrue(urls[1].endswith("&continuationToken=a%20%2F%2B%3F"))
        self.assertTrue(
            urls[2].endswith(
                f"workspaces/{WORKSPACE}/eventstreams/{target['itemId']}/topology"
            )
        )
        self.assertEqual(len(urls), 3)
        self.assertGreaterEqual(
            (self.request_times[1] - self.request_times[0]).total_seconds(), 23
        )
        self.assertNotIn(PRIVATE, json.dumps(self.writes))
        output = analytics.transform(
            self.documents(), include_eventstream_topology=True
        )
        self.assertEqual(len(output["lineage_edges"]), 9)
        self.assert_finished(EVENTSTREAM_MODULE, True)

    async def test_denial_and_malformed_object_do_not_starve_other_items(self):
        targets = [item(number, "Eventstream") for number in (10, 11, 12)]
        context = self.context(
            inventory(*targets),
            {"ERROR": "Denied", "status": 403},
            {},
            {key: [] for key in ("sources", "streams", "operators", "destinations")},
        )
        self.assertFalse(await self.collect(context))
        resources = self.resources(EVENTSTREAM_MODULE)[1:]
        self.assertEqual(
            [resource["complete"] for resource in resources], [False, False, True]
        )
        self.assertTrue(all("records" not in resource for resource in resources[:2]))
        output = analytics.transform(
            self.documents(), include_eventstream_topology=True
        )
        self.assertEqual(output["lineage_edges"], [])
        self.assert_finished(EVENTSTREAM_MODULE, False)

    async def test_unexpected_pagination_never_becomes_partial_success(self):
        context = self.context(
            inventory(item(kind="Eventstream")),
            {**topology(), "continuationToken": "next"},
        )
        self.assertFalse(await self.collect(context))
        self.assertNotIn("records", self.resources(EVENTSTREAM_MODULE)[-1])
        self.assertEqual(len(self.urls(context)), 2)

    async def test_deferred_slice_resumes_next_item_with_same_sweep(self):
        targets = [item(number, "Eventstream") for number in (10, 11)]
        context = self.context(inventory(*targets), topology())
        original = context._safe_get.side_effect

        async def slow_page(*args, **kwargs):
            result = await original(*args, **kwargs)
            if len(self.request_times) == 2:
                self.advance(80)
            return result

        context._safe_get.side_effect = slow_page
        self.assertFalse(await self.collect(context))
        saved = self.files[EVENTSTREAM_MODULE + "/progress.json"]
        self.assertEqual(saved["nextItem"], 1)
        resumed = self.context(topology())
        self.assertTrue(await self.collect(resumed))
        self.assertEqual(len(self.urls(resumed)), 1)
        modes = {
            row["mode"]
            for row in analytics.transform(
                self.documents(), include_eventstream_topology=True
            )["lineage_edges"]
        }
        self.assertEqual(len(modes), 1)
        self.assertEqual(
            self.manifests(EVENTSTREAM_MODULE)[-1]["execution"]["sweepId"],
            saved["sweepId"],
        )

    async def test_manifest_failure_replays_uncommitted_inventory_and_topology(self):
        target = item(kind="Eventstream")
        context = self.context(inventory(target), topology())
        original = context.fm.save_snapshot.side_effect

        async def fail(path, name, value):
            if name == "manifest.json" and value["finished"]:
                raise RuntimeError("Synthetic storage failure")
            await original(path, name, value)

        context.fm.save_snapshot.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "Synthetic storage"):
            await self.collect(context)
        self.assertEqual(
            self.files[EVENTSTREAM_MODULE + "/progress.json"]["phase"], "inventory"
        )
        replay = self.context(inventory(target), topology())
        self.assertTrue(await self.collect(replay))
        self.assertEqual(len(self.urls(replay)), 2)

    async def test_new_empty_sweep_gets_new_selection_scope(self):
        self.assertTrue(
            await self.collect(
                self.context(inventory(item(kind="Eventstream")), topology())
            )
        )
        first = self.manifests(EVENTSTREAM_MODULE)[-1]["execution"]["sweepId"]
        self.assertTrue(await self.collect(self.context(inventory())))
        last = self.manifests(EVENTSTREAM_MODULE)[-1]["execution"]["sweepId"]
        self.assertNotEqual(first, last)
        output = analytics.transform(
            self.documents(), include_eventstream_topology=True
        )
        health = sorted(
            (
                row
                for row in output["collection_health"]
                if row["module"] == EVENTSTREAM_MODULE
            ),
            key=lambda row: row["observed_at_utc"],
        )
        self.assertTrue(
            all(edge["mode"] != health[-1]["mode"] for edge in output["lineage_edges"])
        )

    async def test_invalid_exclusions_or_progress_fail_before_auth_and_writes(self):
        for saved, exclusions in (
            (None, PRIVATE),
            ({}, ""),
            ({"settings": {"excludeWorkspaceIds": []}}, ""),
        ):
            self.files.clear()
            if saved is not None:
                self.files[EVENTSTREAM_MODULE + "/progress.json"] = saved
            context = self.context()
            with (
                self.subTest(saved=saved),
                patch.dict(
                    os.environ, {"FABRIC_EVENTSTREAM_EXCLUDE_WORKSPACE_IDS": exclusions}
                ),
                self.assertRaises((ValueError, TypeError)),
            ):
                await self.collect(context)
            context.clients["tenant"].get_headers.assert_not_called()
            context._safe_get.assert_not_awaited()
            context.fm.save_snapshot.assert_not_awaited()

    async def test_public_registration_cron_and_successful_checkpoint(self):
        audit = Audits()
        context = self.context(inventory())
        audit.context, audit.fm = context, context.fm
        old = "2025-12-01T00:00:00.000000Z"
        state = {EVENTSTREAM_MODULE: {"lastRun": old}}
        audit.fm.read = AsyncMock(return_value=state)
        audit.fm.save = AsyncMock()
        build_audit(
            settings={
                "TENANT_ID": "offline",
                "CLIENT_ID": "offline",
                "CLIENT_SECRET": "offline-placeholder",
                "APPLICATION_MODULES": "FabricEventstreamTopology",
                "LAKEHOUSE_NAME": "OfflineLakehouse",
                "WORKSPACE_NAME": "OfflineWorkspace",
                "FABRICEVENTSTREAMTOPOLOGY_CRON": "0 1 * * *",
            },
            audit=audit,
        )
        with (
            patch.object(audit, "_Audits__setup_clients"),
            patch.object(audit_module, "is_function_due", return_value=True) as due,
        ):
            self.assertTrue(await audit.run())
        self.assertEqual(due.call_args.args[0], "0 1 * * *")
        self.assertNotEqual(state[EVENTSTREAM_MODULE]["lastRun"], old)
