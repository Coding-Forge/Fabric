"""Offline evidence contracts for notebooks 12-21."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from env.modules import fabricdeploymentpipelineoperations as deployment_collector
from notebooks import monitor_analytics as analytics
from notebooks import monitor_module_analytics as modules
from notebooks import monitor_validation as validation
from tests.fabric_helpers import PIPELINE, WORKSPACE, CollectorTestCase, operation

OTHER = "00000000-0000-0000-0000-000000000003"
PRIVATE = "DO_NOT_KEEP_PRIVATE_METADATA"


def document(path, value):
    return analytics.document(path, json.dumps(value).encode())


def dated(prefix, name, value):
    return document(f"{prefix}/2026/01/02/{name}", value)


def transform(documents):
    return analytics.transform(documents, module_extractor=modules.transform_modules)


class ModuleEvidenceTests(unittest.TestCase):
    def fixtures(self):
        return [
            dated(
                "catalog/snapshots",
                "apps.json",
                [
                    {
                        "id": PIPELINE,
                        "name": "App",
                        "workspaceId": WORKSPACE,
                        "lastUpdate": "2026-01-01T10:00:00Z",
                        "description": PRIVATE,
                    }
                ],
            ),
            dated(
                "capacity",
                "20260102_00000.capacity.json",
                [
                    {
                        "id": PIPELINE,
                        "displayName": "Capacity",
                        "sku": "F64",
                        "state": "Active",
                        "region": "west",
                    }
                ],
            ),
            dated(
                "capacity_metrics",
                f"20260102_{PIPELINE}_utilization_20260101.capacity_metrics.json",
                {
                    "capacityId": PIPELINE,
                    "sku": "F64",
                    "date": "2026-01-01",
                    "group": "utilization",
                    "rows": [
                        {
                            "Timepoints[Timepoint]": "2026-01-01T10:00:00",
                            "[CU limit]": 64,
                            "[SKU CU by timepoint %]": None,
                        }
                    ],
                },
            ),
            dated(
                "graph",
                "users.json",
                [
                    {
                        "id": WORKSPACE,
                        "accountEnabled": True,
                        "userType": "Member",
                        "assignedLicenses": [],
                        "userPrincipalName": PRIVATE,
                        "displayName": PRIVATE,
                        "mail": PRIVATE,
                    }
                ],
            ),
            dated(
                "graph",
                "groups.json",
                [
                    {
                        "id": OTHER,
                        "securityEnabled": True,
                        "mailEnabled": False,
                        "groupTypes": [],
                        "isPowerBIAudienceGroup": True,
                        "mail": PRIVATE,
                    }
                ],
            ),
            dated(
                "graph",
                "groupmembers.json",
                [{"groupId": OTHER, "memberId": WORKSPACE, "displayName": PRIVATE}],
            ),
            dated(
                "graph",
                "userlicenses.json",
                [
                    {
                        "userId": WORKSPACE,
                        "skuId": PIPELINE,
                        "disabledPlans": [],
                        "userPrincipalName": PRIVATE,
                    }
                ],
            ),
            dated(
                "graph",
                "subscribedskus.json",
                [
                    {
                        "skuId": PIPELINE,
                        "skuPartNumber": "FABRIC",
                        "consumedUnits": 2,
                        "prepaidUnits": {"enabled": 3, "suspended": 0, "warning": 0},
                    }
                ],
            ),
            dated(
                "roles",
                "20260102_00000.roles.json",
                [
                    {
                        "id": WORKSPACE,
                        "users": [
                            {
                                "identifier": PRIVATE,
                                "principalType": "User",
                                "groupUserAccessRight": "Member",
                                "displayName": PRIVATE,
                            }
                        ],
                    }
                ],
            ),
            dated(
                "tenant",
                "tenant-settings.json",
                {
                    "tenantSettings": [
                        {
                            "settingName": "Example",
                            "enabled": False,
                            "enabledSecurityGroups": [
                                {"graphId": OTHER, "name": PRIVATE}
                            ],
                            "excludedSecurityGroups": [],
                        }
                    ]
                },
            ),
            dated(
                "delegatedsettings/capacities",
                "capacities.json",
                [
                    {
                        "id": PIPELINE,
                        "tenantSettings": [
                            {
                                "settingName": "Example",
                                "enabled": True,
                                "delegatedFrom": "Tenant",
                                "excludedSecurityGroups": [OTHER],
                            }
                        ],
                    }
                ],
            ),
            dated(
                "domains",
                "domains.json",
                [
                    {
                        "id": OTHER,
                        "displayName": "Domain",
                        "workspaceId": WORKSPACE,
                        "workspace": "Workspace",
                    },
                    {
                        "id": OTHER,
                        "displayName": "Domain",
                        "workspaceId": PIPELINE,
                        "workspace": "Workspace 2",
                    },
                ],
            ),
            dated(
                "gitconnections",
                "gitconnections.json",
                [
                    {
                        "workspaceId": WORKSPACE,
                        "gitConnectionState": "Connected",
                        "gitProviderDetails": {
                            "gitProviderType": "GitHub",
                            "ownerName": PRIVATE,
                            "directoryName": PRIVATE,
                            "repositoryName": "Repository",
                            "branchName": "main",
                            "url": PRIVATE,
                            "credential": PRIVATE,
                        },
                        "gitSyncDetails": {"lastSyncTime": "2026-01-01T10:00:00Z"},
                    }
                ],
            ),
            dated(
                "tags",
                "tags.json",
                [
                    {
                        "id": PIPELINE,
                        "displayName": "Finance",
                        "scope": {"type": "Domain", "domainId": OTHER},
                    }
                ],
            ),
            *[
                dated(
                    "widelysharedlinks",
                    name,
                    [
                        {
                            "artifactId": PIPELINE,
                            "artifactType": "Report",
                            "accessRight": "Read",
                            "shareType": "Link",
                            "sharer": PRIVATE,
                            "url": PRIVATE,
                        }
                    ],
                )
                for name in modules.MODULE_ARTIFACTS["sharing"]
            ],
        ]

    def test_all_legacy_families_project_safe_fields_and_stable_observations(self):
        documents = self.fixtures()
        output = transform(documents)
        again = transform(list(reversed(documents)))
        for domain, datasets in modules.MODULE_DOMAINS.items():
            if domain == "deployments":
                continue
            for dataset in datasets:
                with self.subTest(dataset=dataset):
                    self.assertTrue(output[dataset])
                    self.assertEqual(output[dataset], again[dataset])
                    self.assertNotIn(PRIVATE, json.dumps(output[dataset]))
                    for entry in output[dataset]:
                        self.assertEqual(entry["source_date"], "2026-01-02")
                        self.assertEqual(entry["coverage_status"], "legacy_unverified")
                        self.assertIsNone(entry["observed_at_utc"])
                        self.assertIsNone(entry["run_id"])
                        self.assertEqual(
                            set(entry),
                            set(analytics.COMMON) | set(analytics.SCHEMAS[dataset]),
                        )
        self.assertEqual(len(output["domains"]), 1)
        self.assertEqual(len(output["domain_workspaces"]), 2)
        self.assertEqual(output["directory_users"][0]["assigned_license_count"], 0)
        self.assertTrue(
            output["workspace_role_assignments"][0]["principal_id"].startswith(
                "sha256:"
            )
        )

    def test_unknown_and_empty_role_and_delegated_scopes_remain_distinct(self):
        output = transform(
            [
                dated(
                    "roles",
                    "20260102_00000.roles.json",
                    [
                        {"id": WORKSPACE},
                        {"id": PIPELINE, "users": []},
                        {"id": OTHER, "users": None},
                    ],
                ),
                dated(
                    "delegatedsettings/workspaces",
                    "workspaces.json",
                    [{"id": WORKSPACE}, {"id": PIPELINE, "overrides": []}],
                ),
            ]
        )
        for dataset, count_key in (
            ("workspace_role_scopes", "assignment_count"),
            ("delegated_setting_scopes", "setting_count"),
        ):
            by_id = {
                entry.get("workspace_id", entry.get("entity_id")): entry
                for entry in output[dataset]
            }
            self.assertIsNone(by_id[WORKSPACE][count_key])
            self.assertEqual(by_id[PIPELINE][count_key], 0)
        self.assertFalse(output["workspace_role_assignments"])
        self.assertFalse(output["delegated_setting_overrides"])

    def test_malformed_file_quarantines_all_pending_tables(self):
        cases = [
            dated(
                "domains",
                "domains.json",
                [
                    {"id": OTHER, "displayName": "A", "workspaceId": WORKSPACE},
                    {"id": OTHER, "displayName": "B", "workspaceId": PIPELINE},
                ],
            ),
            dated(
                "roles",
                "20260102_00000.roles.json",
                [
                    {"id": WORKSPACE, "users": []},
                    {"id": PIPELINE, "users": "not an array"},
                ],
            ),
            dated("graph", "users.json", [{"id": WORKSPACE}, {"id": None}]),
            dated(
                "tenant",
                "tenant-settings.json",
                {
                    "tenantSettings": [
                        {
                            "settingName": "Example",
                            "enabledSecurityGroups": [OTHER],
                            "enabled": "true",
                        }
                    ]
                },
            ),
            dated(
                "delegatedsettings/workspaces",
                "workspaces.json",
                [{"id": WORKSPACE, "tenantSettings": [], "overrides": [{}]}],
            ),
            dated(
                "graph",
                "userlicenses.json",
                [{"userId": WORKSPACE, "skuId": PIPELINE, "disabledPlans": [12]}],
            ),
        ]
        for source in cases:
            with self.subTest(path=source["path"]):
                output = transform([source])
                coverage = output["estate_coverage"]
                self.assertEqual(len(coverage), 1)
                self.assertEqual(coverage[0]["coverage_status"], "invalid")
                self.assertIsNone(coverage[0]["record_count"])
                for dataset in analytics.MODULE_SCHEMAS:
                    self.assertFalse(output[dataset])

    def test_metrics_keep_nullable_values_query_dates_and_timezone_uncertainty(self):
        source = self.fixtures()[2]
        output = transform([source])
        values = {
            entry["metric_name"]: entry
            for entry in output["capacity_metric_observations"]
        }
        self.assertEqual(values["CU limit"]["metric_value"], 64.0)
        self.assertIsNone(values["SKU CU by timepoint %"]["metric_value"])
        self.assertIsNone(values["CU limit"]["timepoint_utc"])
        self.assertEqual(values["CU limit"]["metric_date"], "2026-01-01")
        value = copy.deepcopy(source["value"])
        value["rows"][0]["Timepoints[Timepoint]"] = "2026-01-01T10:00:00+02:00"
        aware = transform([document(source["path"], value)])[
            "capacity_metric_observations"
        ]
        self.assertEqual(aware[0]["timepoint_utc"], "2026-01-01T08:00:00.000000Z")
        for mutate in (
            lambda value: value.update(capacityId=OTHER),
            lambda value: value.update(group="unsupported"),
            lambda value: value["rows"][0].update({"[CU limit]": True}),
            lambda value: value["rows"][0].update({"[CU limit]": float("inf")}),
            lambda value: value.update(rows=[{"[Unknown measure]": 1}]),
        ):
            value = copy.deepcopy(source["value"])
            mutate(value)
            invalid = transform([document(source["path"], value)])
            self.assertFalse(invalid["capacity_metric_observations"])
            self.assertEqual(
                invalid["estate_coverage"][0]["coverage_status"], "invalid"
            )

    def test_source_versions_change_identity_without_fabricating_collection_time(self):
        source = self.fixtures()[0]
        changed = copy.deepcopy(source["value"])
        changed[0]["name"] = "Renamed"
        changed[0].update(observedAt="2026-01-02T00:00:00Z", runId="untrusted")
        before = transform([source])["apps"][0]
        after = transform([document(source["path"], changed)])["apps"][0]
        self.assertNotEqual(before["observation_id"], after["observation_id"])
        self.assertIsNone(after["observed_at_utc"])
        self.assertIsNone(after["run_id"])
        self.assertFalse(transform([])["apps"])
        empty = transform([dated("catalog/snapshots", "apps.json", [])])
        self.assertEqual(empty["estate_coverage"][0]["record_count"], 0)
        self.assertEqual(
            empty["estate_coverage"][0]["coverage_status"], "legacy_unverified"
        )

    def test_reader_only_admits_requested_supported_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "monitor"
            for source in self.fixtures():
                path = root / source["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(source["value"]))
            with patch.object(analytics, "LAKEHOUSE_FILES", folder):
                documents = analytics.load_documents(
                    str(root), source_prefixes={"graph"}
                )
                self.assertEqual(len(documents), 5)
                self.assertTrue(
                    all(source["path"].startswith("graph/") for source in documents)
                )


class DeploymentCompatibilityTests(CollectorTestCase):
    def output(self, files=None):
        return transform(
            [
                document(path, value)
                for path, value in (self.files if files is None else files).items()
                if not path.endswith("/request_gate.json")
            ]
        )

    async def collect(self, rows):
        ctx = self.context(
            {"value": [{"id": PIPELINE, "displayName": "Pipeline"}]}, rows
        )
        return await deployment_collector.main(ctx)

    async def test_real_collector_success_empty_failed_and_discovery_failure(self):
        for rows, expected in (
            ({"value": []}, 0),
            ({"value": [operation()]}, 1),
            ({"ERROR": "denied", "status": 403}, None),
        ):
            self.files.clear()
            with self.subTest(rows=rows):
                await self.collect(rows)
                output = self.output()
                self.assertEqual(len(output["deployment_pipelines"]), 1)
                resource = output["deployment_operation_resources"][0]
                self.assertEqual(resource["record_count"], expected)
                self.assertEqual(
                    resource["coverage_status"],
                    "failed" if expected is None else "success",
                )
                self.assertEqual(len(output["deployment_operations"]), expected or 0)
        self.files.clear()
        await deployment_collector.main(
            self.context({"ERROR": "denied", "status": 403})
        )
        output = self.output()
        self.assertFalse(output["deployment_pipelines"])
        self.assertFalse(output["deployment_operations"])
        self.assertEqual(output["estate_coverage"][0]["coverage_status"], "failed")

    async def test_corrupt_or_unfinished_run_never_partially_publishes(self):
        await self.collect({"value": [operation()]})
        original = copy.deepcopy(self.files)
        resource = next(path for path in original if path.endswith(f"/{PIPELINE}.json"))
        manifest = next(path for path in original if path.endswith("/manifest.json"))
        for mutate in (
            lambda files: files[resource].update(requestPath="wrong"),
            lambda files: files[resource].update(
                parent={"deploymentPipeline": {"id": OTHER}}
            ),
            lambda files: files[resource]["records"].append(
                {"id": "bad", "type": "Deploy"}
            ),
            lambda files: files.pop(resource),
            lambda files: files[manifest].update(finished=False, complete=False),
        ):
            files = copy.deepcopy(original)
            mutate(files)
            output = self.output(files)
            for dataset in modules.MODULE_DOMAINS["deployments"]:
                self.assertFalse(output[dataset])
            self.assertIn(
                output["estate_coverage"][0]["coverage_status"],
                {"invalid", "unfinished"},
            )

    async def test_operation_duration_and_repeated_poll_history(self):
        value = {
            **operation(),
            "executionStartTime": "2026-01-02T01:00:00Z",
            "executionEndTime": "2026-01-02T01:00:30Z",
        }
        await self.collect({"value": [value]})
        await self.collect({"value": [{**value, "status": "Succeeded"}]})
        output = self.output()
        self.assertEqual(len(output["deployment_operations"]), 2)
        self.assertEqual(
            {entry["status"] for entry in output["deployment_operations"]},
            {"Executing", "Succeeded"},
        )
        self.assertTrue(
            all(
                entry["duration_seconds"] == 30
                for entry in output["deployment_operations"]
            )
        )
        self.assertTrue(
            all(entry["observed_at_utc"] for entry in output["deployment_operations"])
        )


class ExpandedValidationScopeTests(unittest.TestCase):
    def test_ten_and_twenty_five_table_scopes_stay_compatible_with_opt_in_full_scope(
        self,
    ):
        spark = MagicMock()

        def frame(dataset):
            return SimpleNamespace(
                schema=SimpleNamespace(
                    fields=[
                        SimpleNamespace(name=key, dataType=kind)
                        for key, kind in {
                            **analytics.COMMON,
                            **analytics.SCHEMAS[dataset],
                        }.items()
                    ]
                )
            )

        def version_frame(_, prefix, dataset, version):
            result = MagicMock()
            result.schema = frame(dataset).schema
            result.select.return_value = result
            return result

        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(validation, "LAKEHOUSE_FILES", folder),
            patch.object(validation, "load_documents", return_value=[]) as read,
            patch.object(validation, "read_curated") as curated,
            patch.object(
                validation, "validation_table_identity", return_value=(WORKSPACE, 1)
            ),
            patch.object(
                validation, "validation_version_frame", side_effect=version_frame
            ),
            patch.object(
                validation,
                "to_frame",
                side_effect=lambda _, dataset, rows: frame(dataset),
            ),
            patch.object(
                validation,
                "validation_table_metrics",
                return_value={"rows": 0, "unique_ids": 0, "invalid_metadata_rows": 0},
            ),
            patch.object(validation, "validation_reports"),
            patch.object(validation, "validation_assert_stable"),
            patch.object(validation, "validation_save_baseline"),
        ):
            for estate, modules_enabled, expected, prefixes in (
                (False, False, analytics.CORE_DATASETS, analytics.CORE_SOURCE_PREFIXES),
                (
                    True,
                    False,
                    analytics.ESTATE_DATASETS,
                    analytics.CORE_SOURCE_PREFIXES | analytics.ESTATE_PREFIXES,
                ),
                (False, True, analytics.SCHEMAS, None),
                (True, True, analytics.SCHEMAS, None),
            ):
                curated.reset_mock()
                snapshot = validation.validate_rerun(
                    spark,
                    MagicMock(),
                    raw_root=str(Path(folder) / "monitor"),
                    prefix="monitor_",
                    permission_mode="Scoped",
                    action="capture",
                    baseline_name="new.json",
                    include_estate_tables=estate,
                    include_module_tables=modules_enabled,
                )
                self.assertEqual(set(snapshot["tables"]), set(expected))
                self.assertEqual(curated.call_count, len(expected))
                self.assertEqual(read.call_args.kwargs["source_prefixes"], prefixes)
