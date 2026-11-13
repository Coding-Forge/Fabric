"""Offline minimized shortcut evidence and notebook lineage integration."""

import copy
import json
import unittest
from unittest.mock import MagicMock

from env.utility.shortcut_relationships import (
    SHORTCUT_MODULE,
    shortcut_fingerprint,
    shortcut_records,
)
from notebooks import monitor_analytics as analytics
from notebooks import monitor_validation as validation
from notebooks.build_monitor_notebooks import generated_notebooks
from tests.fabric_helpers import WORKSPACE, item
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
