"""Strict, read-only Fabric collection support for scoped observational snapshots."""

import asyncio
import json
import math
import os
from datetime import datetime, timedelta
from logging import Logger
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import aiohttp

from env.context import (
    Context,
    _safe_http_status,
    log_validation_failure,
    safe_fabric_error_code,
    utc_now,
    utc_stamp,
)
from env.utility import http_retry
from env.utility.admin_paging import fetch_all_pages

JsonValue = bool | int | float | str | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
FABRIC_ROOT = "https://api.fabric.microsoft.com/v1"
JOB_ITEM_TYPES = frozenset({"Notebook", "DataPipeline", "SparkJobDefinition"})


class _RequestDeferred(RuntimeError):
    """Signal an explicit incomplete collection without sending a request."""


def item_scope(key: str, maximum: int) -> list[dict[str, str]]:
    """Parse an explicit, nonempty JSON item scope from an environment variable.

    :param key: Environment variable containing workspaceId, itemId and type objects.
    :param maximum: Maximum number of unique items permitted per run.
    :return: Validated item identities, in configured order.
    :raises ValueError: If the configuration is missing, malformed, or duplicated.
    :raises TypeError: If a scope entry is not an object.
    """
    try:
        values = json.loads(os.environ.get(key, "null"))
    except ValueError:
        raise ValueError(f"{key} must contain a JSON item scope") from None
    if not isinstance(values, list) or not 1 <= len(values) <= maximum:
        raise ValueError(f"{key} requires between 1 and {maximum} explicit items")
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        if not isinstance(value, dict):
            raise TypeError(f"{key} contains an invalid item")
        try:
            workspace = str(UUID(value["workspaceId"]))
            item = str(UUID(value["itemId"]))
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ValueError(f"{key} requires UUID workspaceId and itemId") from None
        item_type = value.get("type")
        if not isinstance(item_type, str) or not item_type.isalnum():
            raise ValueError(f"{key} requires an item type")
        identity = (workspace, item)
        if identity in seen:
            raise ValueError(f"{key} contains duplicate item identities")
        seen.add(identity)
        result.append({"workspaceId": workspace, "itemId": item, "type": item_type})
    return result


def select_fields(record: JsonObject, fields: tuple[str, ...]) -> JsonObject:
    """Return only explicitly allowed top-level JSON fields from a record."""
    return {field: record[field] for field in fields if field in record}


class FabricCollection:
    """Collect sequential pages with safe logging and per-attempt throttling.

    Snapshots are immutable per run under ``module/YYYY/MM/DD/runId/``. Each
    record file has parent identity, request path, UTC observation time and
    success state; the final manifest marks whole-run completeness. Historical
    consumers deduplicate by parent IDs plus record ID, taking the latest
    observedAt for current status, retaining older observations for history.
    An absent manifest or ``finished=false`` means interrupted/partial writes,
    never an empty success. A finished manifest can contain both successful and
    failed resources; valid successful resource observations remain usable even
    though whole-run ``complete`` is false and the checkpoint does not advance.

    Server cooldowns are durable across sequential runs in module-local ledgers.
    Permission attempt pacing is also durable. Only one scheduler instance may
    collect against a given output root; this is not a distributed rate limiter.
    A pre-request pending marker prevents early reuse after an unacknowledged
    attempt or failed cooldown write; clearing it requires operator investigation.

    :param context: Runtime providing Fabric auth, HTTP retries and strict storage.
    :param module: Lower-case module folder.
    :param coverage: Explicit reporting coverage and API retention limitations.
    :param interval: Minimum seconds between HTTP attempts within this collector.
    :param single_attempt: Defer retries and allow at most one HTTP attempt per run.
    :param request_deadline: Optional absolute event-loop monotonic deadline for
        starting the durable reservation. The caller must exclude its network
        and storage reserve. Enables budgeted UTC gate waits with at most three
        sleep/recheck cycles; None preserves immediate single-attempt deferral.
    """

    def __init__(
        self,
        context: Context,
        module: str,
        coverage: str,
        interval: float = 1.0,
        *,
        single_attempt: bool = False,
        request_deadline: float | None = None,
    ) -> None:
        self.context = context
        self.module = module
        self.coverage = coverage
        self.interval = interval
        self.run_id = uuid4().hex
        self.path = f"{module}/{utc_now():%Y/%m/%d}/{self.run_id}/"
        self.results: list[JsonValue] = []
        self._latest_resource_observed_at: datetime | None = None
        self.next_request = utc_now()
        self.durable_gate = module == "fabricitemaccesspermissions"
        self.logger = context.logger
        self._list_key = "value"
        self._page_count = 0
        self._allow_paging = True
        self.single_attempt = single_attempt
        self.request_deadline = request_deadline
        self.attempts = 0
        self.blocked = False
        self.pending = False
        self.errors: list[JsonValue] = []
        self.execution: JsonObject = {}
        self.resume_later = False
        self.failed = False
        self._resource_deferred = False

    async def start(self) -> None:
        """Persist an incomplete manifest and load the module's throttle ledger.

        :raises RuntimeError: If snapshot storage or the ledger is unusable.
        """
        if self.module not in self.context.collection_coverage_logged:
            self.logger.info("%s coverage: %s", self.module, self.coverage)
            if self.durable_gate:
                self.logger.info(
                    "%s requires one scheduler per output root; external API "
                    "quota use is not coordinated",
                    self.module,
                )
            self.context.collection_coverage_logged.add(self.module)
        ledger = await self.context.fm.read_snapshot(
            f"{self.module}/", "request_gate.json"
        )
        if ledger is not None:
            try:
                if not isinstance(ledger.get("nextRequestUtc"), str):
                    raise TypeError("Missing timestamp")
                if not isinstance(ledger.get("blocked", False), bool):
                    raise TypeError("Invalid blocked flag")
                if not isinstance(ledger.get("pending", False), bool):
                    raise TypeError("Invalid pending flag")
                self.next_request = self.context.convert_dt_str(
                    ledger["nextRequestUtc"]
                )
                self.blocked = ledger.get("blocked", False)
                self.pending = ledger.get("pending", False)
            except (KeyError, ValueError, TypeError):
                raise RuntimeError("Fabric request gate ledger is invalid") from None
        await self._write_manifest(False, False)

    def record_deferral(self, reason: str) -> None:
        """Record a safe pause without masking an unsafe durable request gate."""
        if self.pending or self.blocked:
            self.failed = True
            self.logger.error("%s blocked: %s", self.module, reason)
        else:
            self.resume_later = True
            self._resource_deferred = True
            self.logger.info("%s deferred: %s", self.module, reason)

    def _request_delay(self) -> float:
        if self.pending:
            raise _RequestDeferred(
                "Unacknowledged HTTP attempt; operator intervention required"
            )
        if self.blocked:
            raise _RequestDeferred(
                "Invalid Retry-After; operator intervention required"
            )
        if self.single_attempt and self.attempts:
            raise _RequestDeferred("One-attempt execution budget exhausted")
        delay = (self.next_request - utc_now()).total_seconds()
        if self.request_deadline is not None:
            if (
                asyncio.get_running_loop().time() + max(0.0, delay)
                > self.request_deadline
            ):
                raise _RequestDeferred(
                    f"Request deferred until {utc_stamp(self.next_request)}"
                )
        elif delay > 30 or (self.single_attempt and delay > 0):
            raise _RequestDeferred(
                f"Request deferred until {utc_stamp(self.next_request)}"
            )
        return max(0.0, delay)

    async def _wait_for_request(self) -> None:
        """Wait within the admission deadline, rechecking UTC after each sleep.

        The optional deadline excludes the caller's request/storage reserve.
        Defer after three sleeps if UTC still forbids admission, even if the
        monotonic budget remains; cancellation and fail-closed flags propagate.
        Without a deadline, retain the legacy single-check wait behavior.
        """
        delay = self._request_delay()
        if self.request_deadline is None:
            if delay > 0:
                await asyncio.sleep(delay)
            return
        for _ in range(3):
            if delay <= 0:
                return
            await asyncio.sleep(delay)
            delay = self._request_delay()
        if delay > 0:
            raise _RequestDeferred(
                f"Request deferred until {utc_stamp(self.next_request)}"
            )

    async def _gate(self) -> None:
        await self._wait_for_request()
        self.next_request = utc_now() + timedelta(seconds=self.interval)
        self.pending = True
        reservation_start = utc_now()
        reservation_monotonic = asyncio.get_running_loop().time()
        if self.durable_gate:
            # Reserve before sending, so cancellation/crashes do not erase pacing.
            # Include an allowed ledger-write duration so slow storage cannot
            # shorten the interval between actual HTTP attempts.
            self.next_request += timedelta(seconds=5)
        await self._save_gate()
        # Wait for the write to settle rather than cancelling a threaded
        # SDK upload that could later overwrite a newer reservation.
        if self.durable_gate and (
            (utc_now() - reservation_start).total_seconds() > 5
            or (
                self.request_deadline is not None
                and asyncio.get_running_loop().time() - reservation_monotonic > 5
            )
        ):
            raise RuntimeError(
                "Permission throttle ledger write exceeded its five-second margin"
            )
        self.attempts += 1

    async def _save_gate(self) -> None:
        await self.context.fm.save_snapshot(
            f"{self.module}/",
            "request_gate.json",
            {
                "nextRequestUtc": utc_stamp(self.next_request),
                "blocked": self.blocked,
                "pending": self.pending,
            },
        )

    async def _observe_response(self, response: JsonObject, attempt: int) -> bool:
        # Clear the pre-request marker only when the response/cooldown is durable.
        # A timeout, cancellation or failed response write leaves future runs blocked.
        self.pending = False
        if "ERROR" not in response:
            await self._save_gate()
            return not self.single_attempt
        status = _safe_http_status(response.get("status"))
        if (
            status not in http_retry.RETRYABLE_STATUSES
            and response.get("retryAfter") is None
        ):
            await self._save_gate()
            return not self.single_attempt
        raw = response.get("retryAfter")
        try:
            delay = http_retry.parse_retry_after(raw) if isinstance(raw, str) else None
        except (OverflowError, ValueError):
            delay = None
        if raw is not None and (delay is None or not math.isfinite(delay)):
            # An unknown server cooldown cannot safely become a guessed delay.
            self.blocked = True
            await self._save_gate()
            self.errors.append("Invalid Retry-After; further requests blocked")
            self.logger.error("%s blocked by invalid Retry-After", self.module)
            return False
        if delay is None:
            delay = http_retry.BASE_BACKOFF_SECONDS * (2**attempt)
        try:
            self.next_request = max(
                self.next_request, utc_now() + timedelta(seconds=delay)
            )
        except OverflowError:
            self.blocked = True
            self.errors.append("Retry-After outside supported timestamp range")
        await self._save_gate()
        return not self.single_attempt and not self.blocked

    async def invokeAPI(self, url: str, headers: dict[str, str]) -> JsonObject:
        """Adapt existing paging to strictly validated, throttled Fabric GETs.

        :param url: Fabric v1 HTTPS URL generated from a fixed endpoint.
        :param headers: Ignored; a cached Fabric-audience token is refreshed per page.
        :return: Validated page or a sanitized error object, never response bodies.
            Request failures include numeric status (or None) and an allowlisted
            errorCode (or fixed safe label), also retained in manifest errors.
        """
        self._resource_deferred = False
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.fabric.microsoft.com"
            or not parsed.path.startswith("/v1/")
            or parsed.fragment
        ):
            return {"ERROR": "Disallowed Fabric request URL"}
        self._page_count += 1
        if self._page_count > 10000:
            return {"ERROR": "Page safety limit exceeded; collection incomplete"}
        try:
            # A blocked control file must also prevent authentication I/O.
            self._request_delay()
            fabric_headers = await asyncio.to_thread(
                self.context.clients["tenant"].get_headers
            )
            response = await self.context.invokeAPI(
                url,
                headers=fabric_headers,
                request_gate=self._gate,
                response_gate=self._observe_response,
            )
        except _RequestDeferred as exc:
            self.errors.append(str(exc))
            self.record_deferral(str(exc))
            return {"ERROR": str(exc), "deferred": True}
        except (asyncio.TimeoutError, TimeoutError, aiohttp.ClientError):
            self.failed = True
            self.errors.append("Fabric transport failure")
            self.logger.error("%s Fabric GET transport failure", self.module)
            return {"ERROR": "Fabric transport failure"}
        if not isinstance(response, dict) or "ERROR" in response or "error" in response:
            self.failed = True
            status = response.get("status") if isinstance(response, dict) else None
            safe_status = _safe_http_status(status)
            error_code = safe_fabric_error_code(response)
            log = (
                self.logger.warning
                if safe_status in http_retry.RETRYABLE_STATUSES
                else self.logger.error
            )
            if safe_status is not None:
                log(
                    "%s Fabric request failed: HTTP %d errorCode=%s",
                    self.module,
                    safe_status,
                    error_code,
                )
            else:
                log(
                    "%s Fabric request failed: HTTP status unavailable errorCode=%s",
                    self.module,
                    error_code,
                )
            if not isinstance(response, dict):
                log_validation_failure(
                    self.logger, self.module, "$", "object", response
                )
            self.errors.append(
                {
                    "error": "Fabric request failed",
                    "status": safe_status,
                    "errorCode": error_code,
                }
            )
            if isinstance(response, dict) and (
                safe_status in http_retry.RETRYABLE_STATUSES or self.blocked
            ):
                return {
                    "ERROR": "Fabric request deferred after throttling",
                    "status": safe_status,
                    "errorCode": error_code,
                    "deferred": True,
                    "attempted": True,
                }
            return {
                "ERROR": "Fabric request failed",
                "status": safe_status,
                "errorCode": error_code,
            }
        records = response.get(self._list_key)
        list_path = {
            "value": "$.value",
            "itemEntities": "$.itemEntities",
            "accessDetails": "$.accessDetails",
        }.get(self._list_key, "$.resultList")
        if not isinstance(records, list):
            log_validation_failure(
                self.logger,
                self.module,
                list_path,
                "list",
                records,
                missing=self._list_key not in response,
            )
            return {"ERROR": "Missing or malformed Fabric result list"}
        for ordinal, record in enumerate(records, 1):
            if not isinstance(record, dict):
                log_validation_failure(
                    self.logger,
                    self.module,
                    f"{list_path}[]",
                    "object",
                    record,
                    ordinal=ordinal,
                )
                return {"ERROR": "Missing or malformed Fabric result list"}
        token = response.get("continuationToken")
        if token is not None and (not isinstance(token, str) or not token):
            log_validation_failure(
                self.logger,
                self.module,
                "$.continuationToken",
                "nonempty string or null",
                token,
            )
            return {"ERROR": "Malformed continuation token"}
        if token and not self._allow_paging:
            self.logger.warning(
                "%s validation failed: field=$.continuationToken "
                "expected=absent or null on unpaged endpoint observed=string",
                self.module,
            )
            return {"ERROR": "Unexpected pagination on an unpaged endpoint"}
        if response.get("continuationUri") and not token:
            log_validation_failure(
                self.logger,
                self.module,
                "$.continuationToken",
                "nonempty string when continuationUri is present",
                token,
                missing="continuationToken" not in response,
            )
            return {"ERROR": "Continuation URI without token; collection incomplete"}
        return response

    async def page(
        self, endpoint: str, list_key: str = "value", *, paged: bool = True
    ) -> JsonObject:
        """Fetch one validated page, retaining its token for resumable discovery.

        :param endpoint: Relative Fabric v1 endpoint, including any encoded token.
        :param list_key: Required result-list property.
        :param paged: Whether continuation tokens are permitted.
        :return: A validated page or an explicit error/deferred result.
        """
        self._list_key = list_key
        self._allow_paging = paged
        self._page_count = 0
        return await self.invokeAPI(f"{FABRIC_ROOT}/{endpoint}", {})

    async def pages(
        self, endpoint: str, list_key: str = "value", *, paged: bool = True
    ) -> list[JsonObject] | None:
        """Fetch all pages, failing rather than returning a partial or malformed list.

        :param endpoint: Relative Fabric v1 endpoint, optionally with fixed query.
        :param list_key: Required result list property.
        :param paged: Whether the documented endpoint supports continuationToken.
        :return: All records, including an empty list, or None on incomplete coverage.
        """
        self._list_key = list_key
        self._page_count = 0
        self._allow_paging = paged
        return await fetch_all_pages(
            self, f"{FABRIC_ROOT}/{endpoint}", {}, list_key, self.module
        )

    async def snapshot(
        self,
        name: str,
        endpoint: str,
        parent: JsonObject,
        records: list[JsonObject] | None,
    ) -> bool:
        """Persist a resource observation and add its outcome to the run manifest.

        :param name: Snapshot JSON basename without extension.
        :param endpoint: Relative request endpoint.
        :param parent: Workspace/item/pipeline identity context.
        :param records: Complete records, or None for a failed resource.
        :return: Whether this resource was collected successfully.
        :raises RuntimeError: If storage fails; manifest remains incomplete.
        """
        success = records is not None
        observed_at = utc_now()
        envelope: JsonObject = {
            "runId": self.run_id,
            "observedAt": utc_stamp(observed_at),
            "coverage": self.coverage,
            "requestPath": endpoint,
            "parent": parent,
            "complete": success,
        }
        if success:
            envelope["records"] = records
        else:
            envelope["error"] = "Resource inaccessible, malformed, or incomplete"
            if self._resource_deferred:
                self.logger.info("%s resource deferred: %s", self.module, name)
            else:
                self.failed = True
                self.logger.error("%s resource incomplete: %s", self.module, name)
        await self.context.fm.save_snapshot(self.path, f"{name}.json", envelope)
        self._latest_resource_observed_at = max(
            self._latest_resource_observed_at or observed_at, observed_at
        )
        self.results.append(
            {"file": f"{name}.json", "parent": parent, "complete": success}
        )
        return success

    async def finish(self, complete: bool) -> bool:
        """Write the run manifest; only a successful final write commits a run.

        :param complete: Whether discovery and every selected resource succeeded.
        :return: The supplied completion state.
        :raises RuntimeError: If storage fails or final UTC precedes a saved resource.
        """
        await self._write_manifest(complete, True)
        self.context.deferred_modules.discard(self.module)
        if not complete and self.resume_later and not self.failed:
            self.context.deferred_modules.add(self.module)
        return complete

    async def _write_manifest(self, complete: bool, finished: bool) -> None:
        observed_at = utc_now()
        if (
            finished
            and self._latest_resource_observed_at is not None
            and observed_at < self._latest_resource_observed_at
        ):
            raise RuntimeError(
                "Manifest UTC precedes a saved resource; collection not committed"
            )
        await self.context.fm.save_snapshot(
            self.path,
            "manifest.json",
            {
                "runId": self.run_id,
                "observedAt": utc_stamp(observed_at),
                "coverage": self.coverage,
                "complete": complete,
                "finished": finished,
                "resources": self.results,
                "errors": self.errors,
                "execution": self.execution,
            },
        )


def identified_records(
    records: list[JsonObject] | None,
    required: tuple[str, ...] = ("id",),
    *,
    logger: Logger | None = None,
) -> list[JsonObject] | None:
    """Validate identity/status fields and remove identical duplicate records.

    :param records: Complete API records or None after a failed request.
    :param required: Fields required to be nonempty strings.
    :param logger: Optional runtime logger for sanitized validation diagnostics.
        Required field names must be hardcoded schema keys when logging is enabled.
    :return: Records keyed by ID, or None on malformed/conflicting duplicates.
    """
    if records is None:
        return None
    indexed: dict[str, JsonObject] = {}
    for ordinal, record in enumerate(records, 1):
        for key in required:
            if not isinstance(record.get(key), str) or not record[key]:
                if logger is not None:
                    log_validation_failure(
                        logger,
                        "Fabric records",
                        key,
                        "nonempty string",
                        record.get(key),
                        missing=key not in record,
                        ordinal=ordinal,
                    )
                return None
        identity = record.get("id")
        if not isinstance(identity, str) or not identity:
            if logger is not None:
                log_validation_failure(
                    logger,
                    "Fabric records",
                    "id",
                    "nonempty string",
                    identity,
                    missing="id" not in record,
                    ordinal=ordinal,
                )
            return None
        if identity in indexed and indexed[identity] != record:
            if logger is not None:
                logger.warning(
                    "Fabric records validation failed: record=%d field=id "
                    "expected=unique identity or identical duplicate "
                    "observed=conflicting duplicate object",
                    ordinal,
                )
            return None
        indexed[identity] = record
    return list(indexed.values())
