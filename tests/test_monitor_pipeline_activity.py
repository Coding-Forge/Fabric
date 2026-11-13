"""Offline pipeline activity grain, query coverage and opt-in notebook contracts."""

import copy
import json
import unittest

from notebooks import monitor_analytics as analytics
from notebooks import monitor_pipeline_activity as activity_reports
from tests.fabric_helpers import WORKSPACE, item
from tests.pipeline_activity_fixtures import ACTIVITY, CHILD, PARENT, RUN, activity

MODULE = "fabricpipelineactivityruns"
ITEM = item(2, "DataPipeline")
WINDOW = {key: PARENT[key] for key in ("lastUpdatedAfter", "lastUpdatedBefore")}
JOB_PARENT = {**ITEM, **WINDOW}
QUERY_PARENT = {**JOB_PARENT, "pipelineRunId": RUN}
PRIVATE = "DO_NOT_EXPORT_PRIVATE_PAYLOAD"


def document(path, value):
    return analytics.document(path, json.dumps(value).encode())


def capture(number, resources, *, mode="discovery", execution=None, finished=True):
    folder = f"{MODULE}/2026/01/02/{number:032x}"
    observed = f"2026-01-02T03:{number:02d}:00Z"
    documents, entries = [], []
    for parent, values in resources:
        if "pipelineRunId" in parent:
            name = f"{parent['workspaceId']}_{parent['pipelineRunId']}.json"
            endpoint = (
                f"workspaces/{parent['workspaceId']}/datapipelines/pipelineruns/"
                f"{parent['pipelineRunId']}/queryactivityruns"
            )
        elif "itemId" in parent:
            name = f"jobs_{parent['workspaceId']}_{parent['itemId']}.json"
            endpoint = f"workspaces/{parent['workspaceId']}/items/{parent['itemId']}/jobs/instances"
        else:
            name, endpoint = "inventory.json", "admin/items?type=DataPipeline"
        complete = values is not None
        resource = {
            "runId": f"{number:032x}",
            "observedAt": observed,
            "parent": parent,
            "requestPath": endpoint,
            "complete": complete,
        }
        resource.update(
            {"records": values} if complete else {"error": "Resource incomplete"}
        )
        documents.append(document(folder + "/" + name, resource))
        entries.append({"file": name, "parent": parent, "complete": complete})
    healthy = all(entry["complete"] for entry in entries)
    metadata = {
        "mode": mode,
        "excludeWorkspaceIds": [],
        **(
            {
                "lookbackHours": 24,
                "window": WINDOW,
                "sweepComplete": True,
                "sweepHealthy": healthy,
                "evidence": [],
            }
            if mode == "discovery"
            else {}
        ),
        **(execution or {}),
    }
    manifest = {
        "runId": f"{number:032x}",
        "observedAt": observed,
        "finished": finished,
        "complete": healthy and finished,
        "resources": entries if finished else [],
        "errors": [] if healthy or not finished else ["Resource incomplete"],
        "execution": metadata,
    }
    return [*documents, document(folder + "/manifest.json", manifest)]


def transform(documents):
    return analytics.transform(
        documents, pipeline_extractor=activity_reports.pipeline_activity_tables
    )


class PipelineActivityReportingTests(unittest.TestCase):
    def test_activity_grain_preserves_zero_unknown_window_identity_and_native_metrics(
        self,
    ):
        record = activity(
            activityType="ExecutePipeline",
            activityRunStart="2025-12-31T23:00:00Z",
            childPipelineRunId=CHILD,
            input=PRIVATE,
            error={"message": PRIVATE},
            output={
                "rowsRead": 0,
                "dataWritten": 12,
                "throughput": 1.5,
                "secret": PRIVATE,
            },
        )
        output = transform(
            capture(
                1,
                [
                    (WINDOW, [ITEM]),
                    (JOB_PARENT, [{"pipelineRunId": RUN}]),
                    (QUERY_PARENT, [record]),
                ],
            )
        )
        self.assertEqual(len(output["pipeline_activity_resources"]), 4)
        facts = output["pipeline_activity_observations"]
        self.assertEqual(len(facts), 1)
        observed = facts[0]
        self.assertEqual(observed["workspace_id"], WORKSPACE)
        self.assertEqual(observed["item_id"], ITEM["itemId"])
        self.assertEqual(observed["pipeline_run_id"], RUN)
        self.assertEqual(observed["activity_run_id"], ACTIVITY)
        self.assertEqual(observed["child_pipeline_run_id"], CHILD)
        self.assertEqual(observed["rows_read"], 0)
        self.assertIsNone(observed["rows_copied"])
        self.assertIsNone(observed["duration_ms"])
        self.assertEqual(observed["data_written"], 12)
        self.assertEqual(observed["throughput"], 1.5)
        self.assertEqual(observed["last_updated_after_utc"], WINDOW["lastUpdatedAfter"])
        self.assertEqual(observed["start_time_utc"], "2025-12-31T23:00:00.000000Z")
        self.assertNotIn(PRIVATE, json.dumps(output))
        self.assertEqual(
            set(observed),
            set(analytics.COMMON)
            | set(analytics.SCHEMAS["pipeline_activity_observations"]),
        )

    def test_successful_empty_job_history_does_not_invent_an_activity_query(self):
        output = transform(capture(1, [(WINDOW, [ITEM]), (JOB_PARENT, [])]))
        resources = output["pipeline_activity_resources"]
        jobs = next(
            row for row in resources if row["observation_unit"] == "pipeline_jobs"
        )
        self.assertEqual(jobs["coverage_status"], "success")
        self.assertEqual(jobs["record_count"], 0)
        self.assertFalse(
            any(row["observation_unit"] == "activity_query" for row in resources)
        )
        self.assertEqual(output["pipeline_activity_observations"], [])

    def test_empty_failed_and_missing_queries_keep_distinct_coverage(self):
        for values, expected, count in (([], "success", 0), (None, "failed", None)):
            with self.subTest(expected=expected):
                output = transform(capture(1, [(QUERY_PARENT, values)]))
                query = next(
                    row
                    for row in output["pipeline_activity_resources"]
                    if row["observation_unit"] == "activity_query"
                )
                self.assertEqual(query["coverage_status"], expected)
                self.assertEqual(query["record_count"], count)
                self.assertEqual(output["pipeline_activity_observations"], [])
        missing = transform([])
        self.assertEqual(
            missing["pipeline_activity_resources"][0]["coverage_status"], "missing"
        )
        self.assertIsNone(missing["pipeline_activity_resources"][0]["record_count"])

    def test_unfinished_and_invalid_sources_do_not_admit_metrics_or_private_payloads(
        self,
    ):
        unfinished = transform(
            capture(1, [(QUERY_PARENT, [activity()])], finished=False)
        )
        self.assertEqual(
            unfinished["pipeline_activity_resources"][0]["coverage_status"],
            "unfinished",
        )
        self.assertEqual(unfinished["pipeline_activity_observations"], [])
        for record in (
            activity(pipelineRunId=CHILD),
            activity(activityRunId=PRIVATE),
            activity(output={"rowsRead": True}),
            activity(output={"rowsRead": -1}),
            activity(output={"rowsRead": 1.5}),
            activity(output=[]),
            activity(durationInMs=-1),
            activity(childPipelineRunId=CHILD),
        ):
            with self.subTest(record=record):
                output = transform(capture(1, [(QUERY_PARENT, [record])]))
                self.assertEqual(
                    output["pipeline_activity_resources"][0]["coverage_status"],
                    "invalid",
                )
                self.assertEqual(output["pipeline_activity_observations"], [])
                self.assertNotIn(PRIVATE, json.dumps(output))

    def test_repeated_observations_are_historical_but_latest_metrics_are_not_additive(
        self,
    ):
        documents = capture(
            1, [(QUERY_PARENT, [activity(output={"rowsRead": 4})])]
        ) + capture(2, [(QUERY_PARENT, [activity(output={"rowsRead": 5})])])
        output = transform(documents)
        self.assertEqual(len(output["pipeline_activity_observations"]), 2)
        selected = activity_reports.selected_pipeline_activities(output)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["rows_read"], 5)
        self.assertEqual(output, transform(reversed(documents)))

    def test_new_failed_or_empty_query_never_falls_back_to_old_metrics(self):
        previous = capture(1, [(QUERY_PARENT, [activity()])])
        for values in (None, []):
            output = transform(previous + capture(2, [(QUERY_PARENT, values)]))
            self.assertEqual(len(output["pipeline_activity_observations"]), 1)
            self.assertEqual(activity_reports.selected_pipeline_activities(output), [])
            source = output["pipeline_activity_observations"][0]["source_path"]
            self.assertEqual(
                len(activity_reports.selected_pipeline_activities(output, source)), 1
            )

    def test_exclusion_scope_changes_do_not_reuse_previous_scope_metrics(self):
        output = transform(
            capture(1, [(QUERY_PARENT, [activity()])])
            + capture(2, [(WINDOW, [])], execution={"excludeWorkspaceIds": [WORKSPACE]})
        )
        self.assertEqual(len(output["pipeline_activity_observations"]), 1)
        self.assertEqual(activity_reports.selected_pipeline_activities(output), [])

    def test_invalid_window_route_exclusion_or_unknown_attempt_blocks_latest_selection(
        self,
    ):
        previous = capture(1, [(QUERY_PARENT, [activity()])])
        for mutation in ("window", "route", "exclusion", "timestamp"):
            with self.subTest(mutation=mutation):
                changed = capture(2, [(QUERY_PARENT, [activity()])])
                resource, manifest = (copy.deepcopy(doc["value"]) for doc in changed)
                if mutation == "window":
                    resource["parent"]["lastUpdatedBefore"] = "2026-01-03T00:00:00Z"
                    manifest["resources"][0]["parent"] = resource["parent"]
                elif mutation == "route":
                    resource["requestPath"] = "unapproved"
                elif mutation == "exclusion":
                    manifest["execution"]["excludeWorkspaceIds"] = [WORKSPACE]
                else:
                    manifest["observedAt"] = PRIVATE
                changed = [
                    document(changed[0]["path"], resource),
                    document(changed[1]["path"], manifest),
                ]
                output = transform(previous + changed)
                self.assertEqual(len(output["pipeline_activity_observations"]), 1)
                self.assertEqual(
                    activity_reports.selected_pipeline_activities(output), []
                )
                self.assertNotIn(PRIVATE, json.dumps(output))

    def test_explicit_parent_does_not_infer_pipeline_item_identity(self):
        output = transform(capture(1, [(PARENT, [activity()])], mode="explicit"))
        row = output["pipeline_activity_observations"][0]
        self.assertEqual(row["mode"], "explicit")
        self.assertIsNone(row["item_id"])
        self.assertEqual(row["item_type"], "DataPipeline")
