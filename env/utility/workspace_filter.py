from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

T = TypeVar("T")


@dataclass(frozen=True)
class WorkspaceFilterCounts:
    found: int
    included: int
    excluded: int


def parse_workspace_ids(value: str | Iterable[str] | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    values = value.split(",") if isinstance(value, str) else value
    workspace_ids = set()
    for raw_id in values:
        workspace_id = str(raw_id).strip()
        if not workspace_id:
            continue
        try:
            workspace_ids.add(str(UUID(workspace_id)))
        except ValueError as exc:
            raise ValueError(f"Invalid workspace ID: {workspace_id!r}") from exc
    return frozenset(workspace_ids)


def filter_workspace_records(
    records: Iterable[T],
    include_workspace_ids: str | Iterable[str] | None,
    exclude_workspace_ids: str | Iterable[str] | None,
    *,
    get_workspace_id: Callable[[T], object],
) -> tuple[list[T], WorkspaceFilterCounts]:
    records = list(records)
    include_ids = parse_workspace_ids(include_workspace_ids)
    exclude_ids = parse_workspace_ids(exclude_workspace_ids)
    filtered = []

    for record in records:
        if not include_ids and not exclude_ids:
            filtered.append(record)
            continue
        raw_id = get_workspace_id(record)
        try:
            workspace_id = str(UUID(str(raw_id).strip()))
        except (AttributeError, TypeError, ValueError):
            continue
        if workspace_id in exclude_ids or (
            include_ids and workspace_id not in include_ids
        ):
            continue
        filtered.append(record)

    counts = WorkspaceFilterCounts(
        found=len(records),
        included=len(filtered),
        excluded=len(records) - len(filtered),
    )
    return filtered, counts


def log_workspace_filter_counts(
    logger, collector: str, counts: WorkspaceFilterCounts, processed: int
) -> None:
    logger.info(
        "%s workspace filter: found=%d, included=%d, excluded=%d, processed=%d",
        collector,
        counts.found,
        counts.included,
        counts.excluded,
        processed,
    )
