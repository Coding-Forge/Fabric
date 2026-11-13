"""Synthetic pipeline activity evidence, independent of collector implementations."""

WORKSPACE = "00000000-0000-0000-0000-000000000001"
RUN = "00000000-0000-0000-0000-000000000010"
ACTIVITY = "00000000-0000-0000-0000-000000000011"
CHILD = "00000000-0000-0000-0000-000000000012"
PARENT = {
    "workspaceId": WORKSPACE,
    "pipelineRunId": RUN,
    "lastUpdatedAfter": "2026-01-01T00:00:00.000000Z",
    "lastUpdatedBefore": "2026-01-02T00:00:00.000000Z",
}


def activity(**changes):
    return {
        "pipelineRunId": RUN,
        "activityRunId": ACTIVITY,
        "activityName": "Copy",
        "activityType": "Copy",
        "status": "Succeeded",
        "activityRunStart": "2026-01-01T01:00:00Z",
        "activityRunEnd": None,
        "durationInMs": None,
        "output": {},
        **changes,
    }
