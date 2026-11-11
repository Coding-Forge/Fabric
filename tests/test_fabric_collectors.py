"""Offline behavioral tests for scoped Fabric observations and safe metadata."""

import copy
import json
import logging
import os
from unittest.mock import patch

from env.modules import (
    FabricConnections,
    FabricDeploymentPipelineOperations,
    FabricItemJobHistory,
)
from tests.fabric_helpers import (
    PIPELINE,
    PRIVATE_MARKER,
    ROOT,
    WORKSPACE,
    CollectorTestCase,
    PrivateDiagnosticValue,
    connection,
    item,
    job,
    operation,
)

JOBS = "fabricitemjobhistory"
CONNECTIONS = "fabricconnections"
OPERATIONS = "fabricdeploymentpipelineoperations"


class JobHistoryTests(CollectorTestCase):
    def setUp(self):
        super().setUp()
        self.target = item()
        self.scope = patch.dict(
            os.environ, {"FABRIC_ITEM_JOB_SCOPE": json.dumps([self.target])}
        )
        self.scope.start()
        self.addCleanup(self.scope.stop)

    async def test_pages_keep_identity_status_and_parent_and_encode_token(self):
        first = job()
        first.update(
            rootActivityId="activity-1",
            startTimeUtc="2026-01-02T01:00:00Z",
            endTimeUtc=None,
            failureReason={"errorCode": "OfflineExample"},
            unknown="not retained",
        )
        second = job(identity="job-2", status="Completed")
        ctx = self.context(
            {"value": [first], "continuationToken": "a /+?"},
            {"value": [second]},
        )
        self.assertTrue(await FabricItemJobHistory(ctx))
        endpoint = (
            f"workspaces/{WORKSPACE}/items/{self.target['itemId']}/jobs/instances"
        )
        self.assertEqual(
            self.urls(ctx),
            [ROOT + endpoint, ROOT + endpoint + "?continuationToken=a%20%2F%2B%3F"],
        )
        resource = self.resources(JOBS)[0]
        self.assertEqual(resource["parent"], self.target)
        self.assertEqual(resource["requestPath"], endpoint)
        self.assertEqual(
            resource["records"],
            [{k: v for k, v in first.items() if k != "unknown"}, second],
        )
        self.assertTrue(resource["observedAt"].endswith("Z"))
        self.assert_finished(JOBS, True)
        self.assertGreaterEqual(
            (self.request_times[1] - self.request_times[0]).total_seconds(), 1
        )

    async def test_empty_history_is_explicit_success_not_missing_observation(self):
        self.assertTrue(await FabricItemJobHistory(self.context({"value": []})))
        resource = self.resources(JOBS)[0]
        self.assertEqual(resource["records"], [])
        self.assertIs(resource["complete"], True)
        self.assertNotIn("error", resource)
        self.assert_finished(JOBS, True)

    async def test_invalid_job_or_later_page_failure_is_not_partial_success(self):
        invalid = (
            {**job(), "itemId": item(11)["itemId"]},
            {**job(), "status": ""},
            {**job(), "failureReason": "not an object"},
            {**job(), "startTimeUtc": 123},
        )
        for record in invalid:
            with self.subTest(record=record):
                self.assertFalse(
                    await FabricItemJobHistory(self.context({"value": [record]}))
                )
                resource = self.resources(JOBS)[-1]
                self.assertIs(resource["complete"], False)
                self.assertNotIn("records", resource)
                self.assert_finished(JOBS, False)
        ctx = self.context(
            {"value": [job()], "continuationToken": "next"},
            {"ERROR": "denied", "status": 403},
        )
        self.assertFalse(await FabricItemJobHistory(ctx))
        self.assertNotIn("records", self.resources(JOBS)[-1])
        self.assert_finished(JOBS, False)

    async def test_denied_item_does_not_starve_next_supported_item(self):
        targets = [
            item(kind=kind, number=10 + i)
            for i, kind in enumerate(("Notebook", "DataPipeline", "SparkJobDefinition"))
        ]
        with patch.dict(os.environ, {"FABRIC_ITEM_JOB_SCOPE": json.dumps(targets)}):
            ctx = self.context(
                {"ERROR": "denied", "status": 403},
                {"value": [job(targets[1])]},
                {"value": []},
            )
            self.assertFalse(await FabricItemJobHistory(ctx))
        self.assertEqual(ctx._safe_get.await_count, 3)
        self.assertEqual([r["parent"] for r in self.resources(JOBS)], targets)
        self.assertEqual(
            [r["complete"] for r in self.resources(JOBS)], [False, True, True]
        )

    async def test_status_changes_append_observations_instead_of_overwriting_history(
        self,
    ):
        self.assertTrue(await FabricItemJobHistory(self.context({"value": [job()]})))
        before = copy.deepcopy(self.files)
        self.advance(60)
        self.assertTrue(
            await FabricItemJobHistory(
                self.context({"value": [job(status="Completed")]})
            )
        )
        records = self.resources(JOBS)
        self.assertEqual(
            [r["records"][0]["status"] for r in records], ["InProgress", "Completed"]
        )
        self.assertLess(records[0]["observedAt"], records[1]["observedAt"])
        self.assertNotEqual(records[0]["runId"], records[1]["runId"])
        for path, value in before.items():
            if "/request_gate.json" not in path:
                self.assertEqual(self.files[path], value)


class ConnectionsTests(CollectorTestCase):
    async def test_paginated_allowlist_removes_nested_credentials_paths_and_queries(
        self,
    ):
        unsafe = connection()
        unsafe.update(
            gatewayId="gateway-1",
            privacyLevel="Organizational",
            credentialDetails={"password": "SYNTHETIC_CREDENTIAL_MARKER"},
            accessToken="SYNTHETIC_TOKEN_MARKER",
            connectionString="SYNTHETIC_CONNECTION_STRING",
            path="SYNTHETIC_PATH_MARKER",
            unknown={"query": "SYNTHETIC_QUERY_MARKER"},
        )
        unsafe["connectionDetails"].update(
            path="SYNTHETIC_NESTED_PATH", query="SYNTHETIC_NESTED_QUERY"
        )
        unnamed = {**connection("connection-2"), "displayName": None}
        ctx = self.context(
            {"value": [unsafe, copy.deepcopy(unsafe)], "continuationToken": "a/b"},
            {"value": [unnamed]},
        )
        self.assertTrue(await FabricConnections(ctx))
        expected = {
            **connection(),
            "gatewayId": "gateway-1",
            "privacyLevel": "Organizational",
        }
        resource = self.resources(CONNECTIONS)[0]
        self.assertEqual(resource["records"], [expected, unnamed])
        self.assertEqual(resource["parent"], {})
        self.assertNotIn("SYNTHETIC_", json.dumps(self.writes))
        self.assertEqual(
            self.urls(ctx),
            [ROOT + "connections", ROOT + "connections?continuationToken=a%2Fb"],
        )
        self.assert_finished(CONNECTIONS, True)

    async def test_empty_connections_saves_complete_envelope(self):
        self.assertTrue(await FabricConnections(self.context({"value": []})))
        self.assertEqual(self.resources(CONNECTIONS)[0]["records"], [])
        self.assert_finished(CONNECTIONS, True)

    async def test_required_fields_and_metadata_fail_with_sanitized_diagnostics(self):
        missing = object()
        cases = []
        for field in (
            "id",
            "displayName",
            "connectivityType",
            "connectionDetails.type",
        ):
            for value, observed in (
                (missing, "missing"),
                (None, "null"),
                ("", "empty string"),
                ({PRIVATE_MARKER: PRIVATE_MARKER}, "object"),
                (PrivateDiagnosticValue(), "other"),
            ):
                if field == "displayName" and value is None:
                    continue
                expected = (
                    "nonempty string or null"
                    if field == "displayName"
                    else "nonempty string"
                )
                cases.append((field, value, expected, observed))
        cases.extend(
            ("connectionDetails", value, "object", observed)
            for value, observed in (
                (missing, "missing"),
                (None, "null"),
                ("", "empty string"),
                ([PRIVATE_MARKER], "list"),
                (PrivateDiagnosticValue(), "other"),
            )
        )
        cases.extend(
            (field, value, "string or null", observed)
            for field in ("privacyLevel", "gatewayId")
            for value, observed in (
                ({PRIVATE_MARKER: PRIVATE_MARKER}, "object"),
                (PrivateDiagnosticValue(), "other"),
            )
        )
        for field, value, expected, observed in cases:
            with self.subTest(field=field, observed=observed):
                self.files.clear()
                self.writes.clear()
                record = connection(PRIVATE_MARKER + "-id")
                record["displayName"] = PRIVATE_MARKER + "-name"
                parent = record
                key = field
                if "." in field:
                    parent = record["connectionDetails"]
                    key = "type"
                if value is missing:
                    parent.pop(key, None)
                else:
                    parent[key] = value
                ctx = self.context({"value": [record]})
                ctx.logger = logging.getLogger(__name__)
                with self.assertLogs(ctx.logger, level="WARNING") as logs:
                    result = await FabricConnections(ctx)
                self.assertIs(result, False)
                self.assertIn(
                    f"record=1 field={field} expected={expected} observed={observed}",
                    "\n".join(logs.output),
                )
                self.assertNotIn("records", self.resources(CONNECTIONS)[-1])
                self.assert_finished(CONNECTIONS, False)
                self.assert_sanitized(logs.output, result)

    async def test_conflicting_duplicate_diagnostic_omits_identity_and_names(self):
        first = connection(PRIVATE_MARKER + "-id")
        first["displayName"] = PRIVATE_MARKER + "-first-name"
        ctx = self.context(
            {"value": [first, {**first, "displayName": PRIVATE_MARKER + "-other-name"}]}
        )
        ctx.logger = logging.getLogger(__name__)
        with self.assertLogs(ctx.logger, level="WARNING") as logs:
            result = await FabricConnections(ctx)
        self.assertIs(result, False)
        self.assertIn(
            "record=2 field=id expected=unique identity or identical duplicate "
            "observed=conflicting duplicate object",
            "\n".join(logs.output),
        )
        self.assertNotIn("records", self.resources(CONNECTIONS)[-1])
        self.assert_finished(CONNECTIONS, False)
        self.assert_sanitized(logs.output, result)


class DeploymentOperationsTests(CollectorTestCase):
    def pipelines(self, *ids):
        return {
            "value": [
                {"id": identity, "displayName": "Test pipeline"} for identity in ids
            ]
        }

    async def test_discovery_and_operation_pages_preserve_context_and_status(self):
        other = item(30)["itemId"]
        first = operation()
        first.update(
            sourceStageId="stage-a",
            targetStageId="stage-b",
            executionStartTime="2026-01-02T00:00:00Z",
            ignored="not saved",
        )
        ctx = self.context(
            {**self.pipelines(PIPELINE), "continuationToken": "pipelines/next"},
            self.pipelines(other),
            {"value": [first], "continuationToken": "operations/next"},
            {"value": [operation("Succeeded", "operation-2")]},
            {"value": []},
        )
        self.assertTrue(await FabricDeploymentPipelineOperations(ctx))
        self.assertEqual(
            self.urls(ctx),
            [
                ROOT + "deploymentPipelines",
                ROOT + "deploymentPipelines?continuationToken=pipelines%2Fnext",
                ROOT + f"deploymentPipelines/{PIPELINE}/operations",
                ROOT
                + f"deploymentPipelines/{PIPELINE}/operations?continuationToken=operations%2Fnext",
                ROOT + f"deploymentPipelines/{other}/operations",
            ],
        )
        resources = self.resources(OPERATIONS)
        self.assertEqual(
            resources[1]["parent"],
            {"deploymentPipeline": self.pipelines(PIPELINE)["value"][0]},
        )
        self.assertEqual(
            resources[1]["records"],
            [
                {k: v for k, v in first.items() if k != "ignored"},
                operation("Succeeded", "operation-2"),
            ],
        )
        self.assertEqual(resources[2]["records"], [])
        self.assert_finished(OPERATIONS, True)

    async def test_empty_discovery_is_success_without_operation_requests(self):
        ctx = self.context({"value": []})
        self.assertTrue(await FabricDeploymentPipelineOperations(ctx))
        self.assertEqual(self.resources(OPERATIONS)[0]["records"], [])
        self.assertEqual(ctx._safe_get.await_count, 1)

    async def test_denied_history_keeps_later_pipeline_observation(self):
        other = item(30)["itemId"]
        ctx = self.context(
            self.pipelines(PIPELINE, other),
            {"ERROR": "denied", "status": 403},
            {"value": []},
        )
        self.assertFalse(await FabricDeploymentPipelineOperations(ctx))
        resources = self.resources(OPERATIONS)
        self.assertNotIn("records", resources[1])
        self.assertEqual(resources[2]["records"], [])
        self.assert_finished(OPERATIONS, False)

    async def test_invalid_pipeline_identity_never_becomes_request_path(self):
        ctx = self.context(self.pipelines("../not-a-resource"))
        self.assertFalse(await FabricDeploymentPipelineOperations(ctx))
        self.assertEqual(ctx._safe_get.await_count, 1)
        self.assert_finished(OPERATIONS, False)

    async def test_invalid_operation_shape_is_incomplete_not_empty_success(self):
        for record in (
            {**operation(), "status": ""},
            {**operation(), "executionEndTime": 42},
        ):
            with self.subTest(record=record):
                self.assertFalse(
                    await FabricDeploymentPipelineOperations(
                        self.context(self.pipelines(PIPELINE), {"value": [record]})
                    )
                )
                self.assertNotIn("records", self.resources(OPERATIONS)[-1])
                self.assert_finished(OPERATIONS, False)

    async def test_operation_status_history_is_immutable_and_timestamped(self):
        for status in ("Executing", "Succeeded"):
            self.assertTrue(
                await FabricDeploymentPipelineOperations(
                    self.context(
                        self.pipelines(PIPELINE), {"value": [operation(status)]}
                    )
                )
            )
            self.advance(60)
        observations = [
            r for r in self.resources(OPERATIONS) if "deploymentPipeline" in r["parent"]
        ]
        self.assertEqual(
            [r["records"][0]["status"] for r in observations],
            ["Executing", "Succeeded"],
        )
        self.assertLess(observations[0]["observedAt"], observations[1]["observedAt"])
        self.assertNotEqual(observations[0]["runId"], observations[1]["runId"])
