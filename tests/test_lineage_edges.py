"""Scanner lineage direction, coverage and persistence contracts."""

import unittest
from copy import deepcopy

from env.utility.lineage_edges import scan_snapshot


def example_scan():
    return {
        "workspaces": [
            {
                "id": "W1",
                "reports": [{"id": "R1", "name": "Report", "datasetId": "M1"}],
                "datasets": [
                    {
                        "id": "M1",
                        "upstreamDataflows": [
                            {"targetDataflowId": "F1", "groupId": "W1"},
                            {"targetDataflowId": "EXTERNAL", "groupId": "W2"},
                        ],
                        "upstreamDatasets": [
                            {"targetDatasetId": "OTHER", "groupId": "W3"}
                        ],
                        "datasourceUsages": [{"datasourceInstanceId": "S1"}],
                    }
                ],
                "dataflows": [
                    {"objectId": "F1", "name": "Flow"},
                    {"objectId": "EMPTY"},
                ],
            }
        ],
        "datasourceInstances": [
            {
                "datasourceId": "S1",
                "datasourceType": "Sql",
                "connectionDetails": {
                    "server": "example",
                    "database": "db",
                    "url": "private",
                    "connectionString": "private",
                },
            }
        ],
    }


def snapshot(scan):
    return scan_snapshot(scan, "scan-1", ["W1"], "2026-11-03T19:00:00.000000Z")


class LineageEdgesTests(unittest.TestCase):
    def test_scanner_shapes_and_directions(self):
        result = snapshot(example_scan())
        edges = {
            (row["QueryItemId"], row["Direction"], row["RelatedItemId"]): row
            for row in result["edges"]
        }
        self.assertIn(("r1", "upstream", "m1"), edges)
        self.assertIn(("m1", "downstream", "r1"), edges)
        self.assertIn(("m1", "upstream", "f1"), edges)
        self.assertIn(("f1", "downstream", "m1"), edges)
        self.assertEqual(edges["m1", "upstream", "f1"]["RelatedItemType"], "Dataflow")
        self.assertEqual(
            edges["m1", "upstream", "external"]["RelatedWorkspaceId"], "w2"
        )
        self.assertEqual(
            edges["m1", "upstream", "other"]["RelatedItemType"], "SemanticModel"
        )
        self.assertNotIn(("external", "downstream", "m1"), edges)
        source = edges["m1", "upstream", "s1"]
        self.assertEqual(source["RelatedItemName"], "Sql: example / db")
        self.assertIsNone(source["RelatedWorkspaceId"])
        self.assertNotIn("private", str(result))
        self.assertIn("empty", [item["id"] for item in result["items"]])
        self.assertEqual(result["requestedWorkspaceIds"], ["w1"])
        self.assertEqual(result["returnedWorkspaceIds"], ["w1"])

    def test_deterministic_case_insensitive_dedup_without_mutating_scan(self):
        scan = example_scan()
        model = scan["workspaces"][0]["datasets"][0]
        model["upstreamDataflows"].append({"targetDataflowId": "f1", "groupId": "w1"})
        before = deepcopy(scan)
        result = snapshot(scan)
        model["upstreamDataflows"].reverse()
        self.assertEqual(result, snapshot(scan))
        model["upstreamDataflows"].reverse()
        self.assertEqual(scan, before)
        matching = [
            e
            for e in result["edges"]
            if e["QueryItemId"] == "m1" and e["RelatedItemId"] == "f1"
        ]
        self.assertEqual(len(matching), 1)

    def test_generic_relation_and_unresolved_datasource_preserve_ids(self):
        scan = {
            "workspaces": [
                {
                    "id": "w1",
                    "datasets": [
                        {
                            "id": "m1",
                            "relations": [{"dependentOnArtifactId": "OUTSIDE"}],
                            "datasourceUsages": [{"datasourceInstanceId": "MISSING"}],
                        }
                    ],
                }
            ]
        }
        result = snapshot(scan)
        self.assertEqual(len(result["edges"]), 2)
        self.assertTrue(all(e["RelatedItemName"] is None for e in result["edges"]))
        self.assertTrue(all(e["RelatedWorkspaceId"] is None for e in result["edges"]))
        self.assertEqual(
            {e["RelatedItemId"] for e in result["edges"]}, {"outside", "missing"}
        )

    def test_duplicate_unresolved_references_merge_optional_metadata_deterministically(
        self,
    ):
        scan = example_scan()
        refs = scan["workspaces"][0]["datasets"][0]["upstreamDatasets"]
        refs.append({"targetDatasetId": "other"})
        first = snapshot(scan)
        refs.reverse()
        self.assertEqual(first, snapshot(scan))
        refs.append({"targetDatasetId": "other", "groupId": "conflict"})
        with self.assertRaises(ValueError):
            snapshot(scan)

    def test_empty_observations_preserve_inventory_and_coverage(self):
        result = snapshot({"workspaces": [{"id": "w1", "reports": [{"id": "r1"}]}]})
        self.assertTrue(result["complete"])
        self.assertEqual(result["edges"], [])
        self.assertEqual(len(result["items"]), 1)
        missing = snapshot({"workspaces": []})
        self.assertEqual(missing["returnedWorkspaceIds"], [])
        self.assertEqual(missing["requestedWorkspaceIds"], ["w1"])

    def test_malformed_recognized_structures_are_not_successful_empty_scans(self):
        for scan in (
            None,
            {},
            {"ERROR": "failed"},
            {"workspaces": {}},
            {"workspaces": [None]},
            {"workspaces": [{}]},
            {"workspaces": [{"id": "unexpected"}]},
            {"workspaces": [{"id": "w1", "scanError": {}}]},
            {"workspaces": [{"id": "w1", "datasets": {}}]},
            {"workspaces": [{"id": "w1", "datasets": [{}]}]},
            {
                "workspaces": [
                    {
                        "id": "w1",
                        "datasets": [
                            {
                                "id": "m1",
                                "upstreamDataflows": [{}],
                            }
                        ],
                    }
                ]
            },
            {"workspaces": [{"id": "w1", "reports": [{"id": "r1", "datasetId": 2}]}]},
            {
                "workspaces": [],
                "datasourceInstances": [
                    {
                        "datasourceId": "s1",
                        "connectionDetails": [],
                    }
                ],
            },
        ):
            with self.subTest(scan=scan), self.assertRaises(ValueError):
                snapshot(scan)

    def test_scan_id_cannot_be_a_path(self):
        for scan_id in ("../escape", "/absolute", "a/b", "a\\b", "", ".", None):
            with self.subTest(scan_id=scan_id), self.assertRaises(ValueError):
                scan_snapshot({"workspaces": []}, scan_id, ["w1"], "now")
