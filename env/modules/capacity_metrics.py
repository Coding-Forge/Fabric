import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from env.context import utc_now
from env.utility.http_retry import RequestHeaders

STATE_KEY = "capacitymetrics"
DEFAULT_DAYS_BACK = 3
MAX_DAYS_BACK = 30
DAYS_BACK_ENV = "CAPACITY_METRICS_DAYS_BACK"
INCLUDE_SUSPENDED_ENV = "CAPACITY_METRICS_INCLUDE_SUSPENDED"

_GUID_RE = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)

CAPACITIES_QUERY = (
    "EVALUATE SELECTCOLUMNS(Capacities, "
    '"id", Capacities[Capacity Id], '
    '"state", Capacities[State], '
    '"name", Capacities[Capacity name], '
    '"sku", Capacities[SKU])'
)

# DirectQuery tables return no rows unless the query is scoped to a capacity (via
# MPARAMETER and TREATAS) and a date, so every group query uses this template.
GROUP_QUERY_TEMPLATE = (
    "DEFINE MPARAMETER 'CapacitiesList' = {{ \"{capacity_id}\" }}\n"
    "EVALUATE SUMMARIZECOLUMNS('Timepoints'[Timepoint],\n"
    "    TREATAS({{\"{capacity_id}\"}}, 'Capacities'[Capacity Id]),\n"
    "    TREATAS({{DATE({year},{month},{day})}}, 'Dates'[Date]),\n"
    "    {measures})"
)

PROBE_QUERY_TEMPLATE = "EVALUATE ROW(\"probe\", 'All Measures'[{measure}])"


@dataclass(frozen=True)
class MeasureGroup:
    """A set of measures queried together (one call per capacity and day).

    :param name: Group name, used in the output file name.
    :param measures: Measure names in the ``All Measures`` table.
    """

    name: str
    measures: tuple[str, ...]


@dataclass(frozen=True)
class MetricsVersion:
    """A Capacity Metrics app measure set.

    :param name: Label for logging.
    :param probe_measure: A measure that only exists in this version or newer.
    :param groups: Measure groups to query when this version is detected.
    """

    name: str
    probe_measure: str | None
    groups: tuple[MeasureGroup, ...]


UTILIZATION = MeasureGroup(
    "utilization",
    (
        "CU limit",
        "SKU CU by timepoint %",
        "Background billable CU %",
        "Interactive billable CU %",
    ),
)
UTILIZATION_FULL = MeasureGroup(
    "utilization",
    UTILIZATION.measures
    + (
        "SKU CU by timepoint",
        "Background non billable CU %",
        "Interactive non billable CU %",
    ),
)
CARRY_OVER = MeasureGroup(
    "carryover",
    (
        "Carry over add %",
        "Carry over burndown %",
        "Cumulative carry over %",
        "Expected burndown in minutes",
    ),
)

# Ordered newest first. The first version whose probe measure exists wins; the last
# entry has no probe and is the known-good fallback. Extend by prepending entries.
VERSIONS: tuple[MetricsVersion, ...] = (
    MetricsVersion(
        "carry-over", "Cumulative carry over %", (UTILIZATION_FULL, CARRY_OVER)
    ),
    MetricsVersion("baseline", None, (UTILIZATION,)),
)


class QueryError(Exception):
    """An executeQueries call failed.

    ``status`` is the HTTP status when known; ``error_body`` is True when the
    service returned an error payload (as opposed to no/odd response).
    """

    def __init__(
        self, message: str, status: int | None = None, error_body: bool = False
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_body = error_body


def validate_capacity_id(capacity_id: Any) -> str:
    """Validate that a capacity ID is GUID-shaped so it is safe to put in DAX.

    :param capacity_id: Candidate capacity ID.
    :return: The ID unchanged.
    :raises ValueError: If the value is not a GUID string.
    """
    if not isinstance(capacity_id, str) or not _GUID_RE.fullmatch(capacity_id):
        raise ValueError("Capacity ID is not a valid GUID")
    return capacity_id


def build_group_query(capacity_id: str, day: datetime, group: MeasureGroup) -> str:
    """Build the DAX query for one measure group, capacity and day.

    :param capacity_id: GUID-shaped capacity ID (validated here).
    :param day: The UTC day to query.
    :param group: The measure group.
    :return: The DAX query text.
    :raises ValueError: If ``capacity_id`` is not a GUID.
    """
    validate_capacity_id(capacity_id)
    measures = ",\n    ".join(f"\"{m}\", 'All Measures'[{m}]" for m in group.measures)
    return GROUP_QUERY_TEMPLATE.format(
        capacity_id=capacity_id,
        year=day.year,
        month=day.month,
        day=day.day,
        measures=measures,
    )


def get_days_back() -> int:
    """Return the look-back window in days from ``CAPACITY_METRICS_DAYS_BACK``.

    :return: A positive integer, clamped to ``MAX_DAYS_BACK`` (30) when larger;
        the default when unset or invalid.
    """
    raw = os.environ.get(DAYS_BACK_ENV, "").strip()
    if not raw:
        return DEFAULT_DAYS_BACK
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_DAYS_BACK
    if value < 1:
        return DEFAULT_DAYS_BACK
    return min(value, MAX_DAYS_BACK)


def _is_fatal(exc: QueryError) -> bool:
    """Return True for throttling (429) or server (>=500) failures."""
    return exc.status is not None and (exc.status == 429 or exc.status >= 500)


def include_suspended() -> bool:
    """Return whether non-Active capacities should be queried."""
    return os.environ.get(INCLUDE_SUSPENDED_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _last_run(context: Any) -> datetime | None:
    """Read this module's lastRun from the context state, or ``None`` if unavailable."""
    state = context.current_state
    try:
        if isinstance(state, str):
            state = json.loads(state)
        if not isinstance(state, dict):
            return None
        entry = state.get(STATE_KEY)
        value = entry.get("lastRun") if isinstance(entry, dict) else None
        if not value:
            return None
        return context.convert_dt_str(value)
    except ValueError:
        return None


def compute_days(
    last_run: datetime | None, now: datetime, days_back: int
) -> list[datetime]:
    """Compute the UTC days to query, oldest first, ending with today.

    The window starts the day before ``last_run`` (so a partially loaded day is
    completed) but never earlier than ``days_back`` days before today.

    :param last_run: Naive UTC lastRun, or ``None``.
    :param now: Naive UTC current time.
    :param days_back: Maximum look-back in days.
    :return: Midnight datetimes.
    """
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days_back)
    if last_run is not None:
        previous_day = last_run.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        start = min(max(start, previous_day), today)
    return [start + timedelta(days=i) for i in range((today - start).days + 1)]


async def _execute_query(
    context: Any, dataset_id: str, headers: RequestHeaders, query: str
) -> list[dict[str, Any]]:
    """Run one DAX query through executeQueries and return its rows.

    :raises QueryError: On an HTTP error, an error body, or an unexpected response.
    """
    payload: dict[str, Any] = {
        "queries": [{"query": query}],
        "serializerSettings": {"includeNulls": True},
    }
    if getattr(context, "impersonatedUserName", None):
        payload["impersonatedUserName"] = context.impersonatedUserName

    response = await context.invokeAPI(
        f"datasets/{dataset_id}/executeQueries", headers=headers, json=payload
    )

    if not isinstance(response, dict):
        raise QueryError("no response")
    if "ERROR" in response:
        raise QueryError(
            f"{response['ERROR']} {str(response.get('message', ''))[:300]}",
            response.get("status"),
        )
    if "error" in response:
        raise QueryError(str(response["error"])[:300], error_body=True)
    results = response.get("results")
    if not results or not isinstance(results, list):
        raise QueryError("unexpected response shape")
    result = results[0]
    if "error" in result:
        raise QueryError(str(result["error"])[:300], error_body=True)
    tables = result.get("tables") or []
    return list(tables[0].get("rows") or []) if tables else []


async def detect_version(
    context: Any, dataset_id: str, headers: RequestHeaders
) -> MetricsVersion:
    """Pick the newest measure set whose probe measure exists in the model.

    A missing measure (HTTP 400 or an error body without a status) means the next older set is tried.

    :return: The detected version.
    :raises QueryError: For any other failure (throttling, auth, network).
    """
    for version in VERSIONS[:-1]:
        query = PROBE_QUERY_TEMPLATE.format(measure=version.probe_measure)
        try:
            await _execute_query(context, dataset_id, headers, query)
        except QueryError as exc:
            if exc.status == 400 or (exc.status is None and exc.error_body):
                context.logger.info(
                    f"Capacity Metrics measure set '{version.name}' unavailable ({exc}); "
                    "trying an older set"
                )
                continue
            raise
        return version
    # The last entry is the baseline set, which needs no probe.
    return VERSIONS[-1]


async def get_capacities(
    context: Any, dataset_id: str, headers: RequestHeaders
) -> list[dict[str, Any]]:
    """Read capacities from the model's Capacities table.

    :return: Dicts with ``id``, ``state``, ``name`` and ``sku`` keys.
    :raises QueryError: If the query fails.
    """
    rows = await _execute_query(context, dataset_id, headers, CAPACITIES_QUERY)
    return [
        {
            "id": row.get("[id]"),
            "state": row.get("[state]"),
            "name": row.get("[name]"),
            "sku": row.get("[sku]"),
        }
        for row in rows
    ]


async def main(context=None):
    """
    Capacity Metrics
    """
    if context is None:
        raise RuntimeError("Context is None")

    dataset_id = str(
        getattr(context, "capacity_metrics_dataset_id", None) or ""
    ).strip()
    if not dataset_id:
        # Opt-in module: nothing to do without a dataset, and retrying cannot help
        context.logger.warning(
            "CAPACITY_METRICS_DATASET_ID is not set; skipping Capacity Metrics extraction"
        )
        return True

    headers = context.clients["pbi"].get_headers
    run_date = utc_now()
    path = (
        f"capacity_metrics/{run_date.strftime('%Y')}/{run_date.strftime('%m')}/"
        f"{run_date.strftime('%d')}/"
    )
    failures = 0

    try:
        version = await detect_version(context, dataset_id, headers)
        capacities = await get_capacities(context, dataset_id, headers)
    except QueryError as exc:
        context.logger.error(f"Capacity Metrics setup failed: {exc}")
        return False
    context.logger.info(
        f"Capacity Metrics measure set: {version.name}; {len(capacities)} capacities"
    )

    days = compute_days(_last_run(context), run_date, get_days_back())
    with_suspended = include_suspended()

    for capacity in capacities:
        capacity_id = capacity["id"]
        try:
            validate_capacity_id(capacity_id)
        except ValueError:
            context.logger.error(
                "Skipping a capacity with an invalid ID in the Capacities table"
            )
            failures += 1
            continue
        if capacity["state"] != "Active" and not with_suspended:
            context.logger.info(
                f"Skipping capacity {capacity_id} (state: {capacity['state']})"
            )
            continue

        saved_rows = 0
        for day in days:
            for group in version.groups:
                query = build_group_query(capacity_id, day, group)
                try:
                    rows = await _execute_query(context, dataset_id, headers, query)
                except QueryError as exc:
                    context.logger.error(
                        f"Capacity {capacity_id} {day:%Y-%m-%d} group '{group.name}' failed: {exc}"
                    )
                    failures += 1
                    if _is_fatal(exc):
                        context.logger.error(
                            f"Aborting Capacity Metrics run: status {exc.status} "
                            f"(throttling/server failure) persisted after retries; "
                            f"{failures} failed queries; remaining queries skipped"
                        )
                        return False
                    continue
                if not rows:
                    continue
                saved_rows += len(rows)
                content = {
                    "capacityId": capacity_id,
                    "capacityName": capacity["name"],
                    "sku": capacity["sku"],
                    "date": day.strftime("%Y-%m-%d"),
                    "group": group.name,
                    "rows": rows,
                }
                file_name = (
                    f"{run_date.strftime('%Y%m%d')}_{capacity_id}_{group.name}_"
                    f"{day.strftime('%Y%m%d')}.capacity_metrics.json"
                )
                await context.fm.save(path=path, file_name=file_name, content=content)

        if saved_rows == 0 and capacity["state"] == "Active":
            context.logger.warning(
                f"Capacity {capacity_id} is Active but returned no metrics rows for "
                f"{days[0]:%Y-%m-%d}..{days[-1]:%Y-%m-%d}"
            )

    if failures:
        context.logger.error(
            f"Capacity Metrics finished with {failures} failed queries; lastRun will not advance"
        )
    return failures == 0


if __name__ == "__main__":
    asyncio.run(main())
