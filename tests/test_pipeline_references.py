"""Pipeline dependencies are literal, scoped evidence, not observed execution."""

import copy
import json
import unittest
from unittest.mock import patch

from env.utility.pipeline_references import pipeline_references

WORKSPACE = "00000000-0000-0000-0000-000000000001"
NOTEBOOK = "aaaaaaaa-0000-0000-0000-000000000002"
PIPELINE = "00000000-0000-0000-0000-000000000003"
LAKEHOUSE = "00000000-0000-0000-0000-000000000004"
CONNECTION = "00000000-0000-0000-0000-000000000005"
PRIVATE = "SYNTHETIC_PRIVATE_PIPELINE_VALUE"


def activity(kind, **properties):
    return {"name": "same activity name", "type": kind, "typeProperties": properties}


def pipeline(*activities):
    return {"properties": {"activities": list(activities)}}


def dataset(kind, **properties):
    return {"type": kind, "typeProperties": properties}


def lakehouse(kind, root, **properties):
    result = dataset(kind, **properties)
    result["linkedService"] = {
        "properties": {
            "type": "Lakehouse",
            "typeProperties": {
                "workspaceId": WORKSPACE,
                "artifactId": LAKEHOUSE,
                "rootFolder": root,
            },
        }
    }
    return result


def refs(result):
    return {(r["operation"], r["kind"], r["reference"]) for r in result["references"]}


class PipelineReferenceTests(unittest.TestCase):
    def test_notebook_and_child_pipeline_calls_do_not_invent_resource_resolution(self):
        source = pipeline(
            activity(
                "TridentNotebook", notebookId=NOTEBOOK.upper(), workspaceId=WORKSPACE
            ),
            activity(
                "InvokePipeline",
                pipelineId=PIPELINE,
                workspaceId=WORKSPACE,
                operationType="InvokeFabricPipeline",
            ),
            activity(
                "ExecutePipeline",
                pipeline={"referenceName": PIPELINE, "type": "PipelineReference"},
            ),
        )
        before = copy.deepcopy(source)
        result = pipeline_references(source)
        self.assertEqual(source, before)
        self.assertEqual(
            refs(result),
            {("execute", "notebook", NOTEBOOK), ("execute", "pipeline", PIPELINE)},
        )
        self.assertEqual(len(result["references"]), 3)
        by_name = result["references"][-1]
        self.assertEqual(by_name["referenceType"], "name")
        self.assertNotIn("workspaceId", by_name)
        self.assertTrue(
            all(r["resolution"] == "unresolved" for r in result["references"])
        )
        self.assertFalse(result["runtimeVerified"])
        self.assertTrue(result["complete"])

    def test_copy_table_reads_writes_and_explicit_connection_lakehouse_context(self):
        source = dataset(
            "SqlServerTable", database="source_db", schema="dbo", table="orders"
        )
        source["externalReferences"] = {"connection": CONNECTION}
        target = lakehouse(
            "LakehouseTable", "Tables", schema="silver", table="orders_clean"
        )
        result = pipeline_references(
            pipeline(
                activity(
                    "Copy",
                    source={"type": "SqlServerSource", "datasetSettings": source},
                    sink={"type": "LakehouseTableSink", "datasetSettings": target},
                )
            )
        )
        self.assertEqual(
            refs(result),
            {
                ("read", "connection", CONNECTION),
                ("read", "table", "orders"),
                ("write", "lakehouse", LAKEHOUSE),
                ("write", "table", "orders_clean"),
            },
        )
        read = next(
            r
            for r in result["references"]
            if r["kind"] == "table" and r["operation"] == "read"
        )
        self.assertEqual(
            (read["database"], read["schema"], read["connectionId"]),
            ("source_db", "dbo", CONNECTION),
        )
        write = result["references"][-1]
        self.assertEqual(
            (
                write["workspaceId"],
                write["artifactId"],
                write["rootFolder"],
                write["schema"],
            ),
            (WORKSPACE, LAKEHOUSE, "Tables", "silver"),
        )
        self.assertTrue(result["complete"])

    def test_copy_file_targets_keep_declared_locations_and_destination_alias(self):
        source = dataset(
            "DelimitedText",
            location={
                "type": "AzureBlobFSLocation",
                "fileSystem": "landing",
                "folderPath": "/raw/",
                "fileName": "orders.csv",
            },
        )
        target = lakehouse(
            "Parquet",
            "Files",
            location={"type": "LakeHouseLocation", "folderPath": "clean/orders"},
        )
        result = pipeline_references(
            pipeline(
                activity(
                    "Copy",
                    source={"type": "DelimitedTextSource", "datasetSettings": source},
                    destination={"type": "ParquetSink", "datasetSettings": target},
                )
            )
        )
        self.assertIn(("read", "path", "/raw/orders.csv"), refs(result))
        self.assertIn(("write", "path", "clean/orders"), refs(result))
        paths = [r for r in result["references"] if r["kind"] == "path"]
        self.assertEqual(paths[0]["fileSystem"], "landing")
        self.assertEqual(paths[1]["artifactId"], LAKEHOUSE)
        self.assertTrue(result["complete"])

    def test_nested_branches_loops_and_inactive_activities_are_potential_calls_only(
        self,
    ):
        call = activity("TridentNotebook", notebookId=NOTEBOOK, workspaceId=WORKSPACE)
        loop = activity(
            "ForEach",
            items={"type": "Expression", "value": PRIVATE},
            activities=[
                activity(
                    "Until",
                    activities=[
                        activity(
                            "IfCondition",
                            ifTrueActivities=[call],
                            ifFalseActivities=[
                                activity(
                                    "Switch",
                                    cases=[{"value": "a", "activities": [call]}],
                                    defaultActivities=[call],
                                )
                            ],
                        )
                    ],
                )
            ],
        )
        loop["state"] = "Inactive"
        result = pipeline_references(pipeline(loop))
        paths = [r["activityPath"] for r in result["references"]]
        self.assertEqual(len(paths), 3)
        self.assertEqual(len(set(paths)), 3)
        self.assertTrue(all("/typeProperties/activities/" in p for p in paths))
        self.assertTrue(any("/ifTrueActivities/" in p for p in paths))
        self.assertTrue(any("/cases/0/activities/" in p for p in paths))
        self.assertTrue(any("/defaultActivities/" in p for p in paths))
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertEqual(result["evidence"], "static_inference")
        self.assertFalse(result["runtimeVerified"])

    def test_dynamic_missing_and_external_calls_are_diagnosed_without_guessing(self):
        result = pipeline_references(
            pipeline(
                activity(
                    "TridentNotebook",
                    notebookId={"type": "Expression", "value": PRIVATE},
                    workspaceId=WORKSPACE,
                ),
                activity(
                    "TridentNotebook",
                    notebookId=NOTEBOOK,
                    workspaceId="@pipeline().parameters.workspace",
                ),
                activity(
                    "InvokePipeline",
                    pipelineId=PIPELINE,
                    workspaceId=WORKSPACE,
                    operationType="InvokeAzureDataFactoryPipeline",
                ),
                activity(
                    "ExecutePipeline",
                    pipeline={
                        "type": "PipelineReference",
                        "referenceName": "@variables('child')",
                    },
                ),
                activity(
                    "TridentNotebook", notebookId="../" + PRIVATE, workspaceId=WORKSPACE
                ),
            )
        )
        self.assertEqual(refs(result), {("execute", "notebook", NOTEBOOK)})
        self.assertNotIn("workspaceId", result["references"][0])
        self.assertFalse(result["complete"])
        reasons = {d["reason"] for d in result["diagnostics"]}
        self.assertTrue(
            {
                "invalid_identifier",
                "dynamic_or_missing_target",
                "unsupported_pipeline_operation",
            }
            <= reasons
        )
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_queries_dynamic_paths_and_wildcards_do_not_become_literal_data_targets(
        self,
    ):
        for field in ("sqlReaderQuery", "query", "sqlReaderStoredProcedureName"):
            with self.subTest(field=field):
                settings = dataset("SqlServerTable", table="unused_default")
                settings["externalReferences"] = {"connection": CONNECTION}
                result = pipeline_references(
                    pipeline(
                        activity(
                            "Copy",
                            source={
                                "type": "SqlServerSource",
                                "datasetSettings": settings,
                                field: PRIVATE,
                            },
                            sink={
                                "datasetSettings": dataset(
                                    "LakehouseTable", table="output"
                                )
                            },
                        )
                    )
                )
                self.assertIn(("read", "connection", CONNECTION), refs(result))
                self.assertFalse(
                    any(
                        r["operation"] == "read" and r["kind"] == "table"
                        for r in result["references"]
                    )
                )
                self.assertNotIn(PRIVATE, json.dumps(result))
                self.assertFalse(result["complete"])
        for folder, store in (
            ("@pipeline().parameters.folder", {}),
            ("raw/*", {}),
            ("raw", {"wildcardFileName": "*.csv"}),
            ("raw", {"fileListPath": PRIVATE}),
        ):
            with self.subTest(folder=folder, store=store):
                result = pipeline_references(
                    pipeline(
                        activity(
                            "Copy",
                            source={
                                "datasetSettings": dataset(
                                    "DelimitedText",
                                    location={
                                        "type": "AzureBlobFSLocation",
                                        "folderPath": folder,
                                        "fileName": "old.csv",
                                    },
                                ),
                                "storeSettings": store,
                            },
                            sink={
                                "datasetSettings": dataset(
                                    "LakehouseTable", table="output"
                                )
                            },
                        )
                    )
                )
                self.assertFalse(any(r["kind"] == "path" for r in result["references"]))
                self.assertFalse(result["complete"])
                self.assertNotIn(PRIVATE, json.dumps(result))

    def test_unsupported_activities_and_datasets_are_not_successful_empty_analysis(
        self,
    ):
        result = pipeline_references(
            pipeline(
                activity("WebActivity", body=PRIVATE),
                activity(
                    "Copy",
                    source={
                        "datasetSettings": dataset("UnsupportedStore", password=PRIVATE)
                    },
                    sink={
                        "datasetSettings": dataset(
                            "LakehouseTable",
                            table={"value": PRIVATE, "type": "Expression"},
                        )
                    },
                ),
                activity("Wait", waitTimeInSeconds=1),
            )
        )
        self.assertEqual(result["references"], [])
        self.assertFalse(result["complete"])
        self.assertTrue(
            {
                "unsupported_activity_type",
                "unsupported_copy_dataset",
                "dynamic_or_missing_target",
            }
            <= {d["reason"] for d in result["diagnostics"]}
        )
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertTrue(pipeline_references({"properties": {}})["complete"])
        self.assertTrue(pipeline_references(pipeline())["complete"])

    def test_malformed_containers_and_traversal_limits_fail_closed(self):
        for content in (
            {},
            {"properties": []},
            {"properties": {"activities": {}}},
            pipeline(None),
            pipeline({"type": []}),
            pipeline(activity("ForEach", activities=None)),
            pipeline(activity("Until")),
            pipeline(activity("IfCondition", ifTrueActivities={})),
            pipeline(activity("Switch", cases=[{"activities": {}}])),
            pipeline(activity("Copy", source={"datasetSettings": []})),
        ):
            with (
                self.subTest(content=content),
                self.assertRaises((ValueError, TypeError)),
            ):
                pipeline_references(content)
        with (
            patch("env.utility.pipeline_references._MAX_ACTIVITIES", 1),
            self.assertRaisesRegex(ValueError, "safety limit"),
        ):
            pipeline_references(pipeline(activity("Wait"), activity("Wait")))
        nested = activity("ForEach", activities=[])
        nested["typeProperties"]["activities"].append(nested)
        with (
            patch("env.utility.pipeline_references._MAX_DEPTH", 2),
            self.assertRaisesRegex(ValueError, "safety limit"),
        ):
            pipeline_references(pipeline(nested))
