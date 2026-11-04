"""Capture tenant-discovered notebook/pipeline definitions and potential notebook I/O."""

import asyncio
import base64
import binascii
import json
import re
from urllib.parse import quote
from uuid import UUID

import aiohttp

from env.context import Context
from env.utility.fabric_collection import (
    FABRIC_ROOT,
    FabricCollection,
    _RequestDeferred,
)
from env.utility.notebook_references import notebook_references


class _Definitions(FabricCollection):
    deferred = False

    async def _observe_response(self, response, attempt):
        if "ERROR" not in response and response.get("retryAfter") is not None:
            return await super()._observe_response(
                {
                    "ERROR": "Operation polling interval",
                    "status": 202,
                    "retryAfter": response["retryAfter"],
                },
                attempt,
            )
        return await super()._observe_response(response, attempt)

    async def request(self, endpoint, method):
        try:
            self._request_delay()
            headers = await asyncio.to_thread(
                self.context.clients["tenant"].get_headers
            )
            result = await self.context.invokeAPI(
                f"{FABRIC_ROOT}/{endpoint}",
                headers=headers,
                request_gate=self._gate,
                response_gate=self._observe_response,
                definition_method=method,
            )
        except _RequestDeferred:
            self.deferred = True
            self.errors.append("Definition request deferred by durable cooldown")
            return None
        except (asyncio.TimeoutError, TimeoutError, aiohttp.ClientError):
            self.deferred = True
            self.errors.append("Definition transport failure")
            return None
        if not isinstance(result, dict) or "ERROR" in result or self.blocked:
            if (
                self.pending
                or self.blocked
                or (
                    isinstance(result, dict) and result.get("status") in (429, 503, 504)
                )
            ):
                self.deferred = True
            self.errors.append("Definition inaccessible, deferred or malformed")
            return None
        return result

    async def definition(self, endpoint, progress, persist):
        operation = progress["operationId"]
        response = None
        if operation is None:
            response = await self.request(endpoint, "POST")
            if response is None:
                return None
            if response.get("status") == 202:
                try:
                    operation = str(UUID(response["operationId"]))
                except (KeyError, ValueError, TypeError, AttributeError):
                    self.errors.append("Missing or invalid definition operation ID")
                    return None
                progress["operationId"] = operation
                await persist()
        if operation is not None:
            for _ in range(60):
                response = await self.request(f"operations/{operation}", "GET")
                if response is None:
                    return None
                body = response.get("body")
                state = body.get("status") if isinstance(body, dict) else None
                if state == "Succeeded":
                    response = await self.request(
                        f"operations/{operation}/result", "GET"
                    )
                    break
                if state not in ("NotStarted", "Running"):
                    self.errors.append(
                        "Definition operation failed or returned invalid state"
                    )
                    return None
            else:
                self.errors.append("Definition operation polling limit exceeded")
                self.deferred = True
                return None
        if response is not None and response.get("status") == 202:
            self.deferred = True
        if response is None or response.get("status") != 200:
            return None
        body = response.get("body")
        return body if isinstance(body, dict) else None


def _inventory(records):
    if records is None:
        return None
    selected = {}
    for record in records:
        kind = record.get("type")
        if not isinstance(kind, str) or not kind:
            raise ValueError("Invalid inventory item type")
        if kind not in ("Notebook", "DataPipeline"):
            continue
        try:
            workspace, item = str(UUID(record["workspaceId"])), str(UUID(record["id"]))
        except (KeyError, ValueError, TypeError, AttributeError):
            raise ValueError("Invalid definition item identity") from None
        parent = {"workspaceId": workspace, "itemId": item, "type": kind}
        key = workspace, item
        if key in selected and selected[key] != parent:
            raise ValueError("Conflicting definition item identities")
        selected[key] = parent
    return [selected[key] for key in sorted(selected)]


def _decode(body, kind):
    definition = body.get("definition")
    parts = definition.get("parts") if isinstance(definition, dict) else None
    if not isinstance(parts, list) or not parts:
        raise ValueError("Missing definition parts")
    decoded = {}
    for part in parts:
        if not isinstance(part, dict):
            raise TypeError("Invalid definition part")
        path, payload = part.get("path"), part.get("payload")
        if (
            not isinstance(path, str)
            or not path
            or path in decoded
            or not isinstance(payload, str)
            or part.get("payloadType") != "InlineBase64"
        ):
            raise ValueError("Invalid definition payload")
        try:
            text = base64.b64decode(payload, validate=True).decode("utf-8-sig")
            decoded[path] = (
                json.loads(text)
                if path.endswith((".json", ".ipynb")) or path == ".platform"
                else text
            )
        except (ValueError, UnicodeError, binascii.Error, RecursionError):
            raise ValueError("Unreadable definition payload") from None
    expected = (
        "notebook-content.ipynb" if kind == "Notebook" else "pipeline-content.json"
    )
    content = decoded.get(expected)
    if not isinstance(content, dict):
        raise TypeError("Missing expected definition content")
    result = {"definition": definition, "decodedParts": decoded}
    if kind == "Notebook":
        result["notebookReferences"] = notebook_references(content)
    return result


def _progress(saved):
    if saved is None or saved == {"finished": True}:
        return {
            "phase": "inventory",
            "items": [],
            "nextItem": 0,
            "continuationToken": None,
            "tokens": [],
            "operationId": None,
            "healthy": True,
            "inventoryFile": None,
            "evidence": [],
        }
    try:
        items = saved["items"]
        normalized = _inventory(
            [
                {"id": i["itemId"], "workspaceId": i["workspaceId"], "type": i["type"]}
                for i in items
            ]
        )
        phase, token, tokens = (
            saved["phase"],
            saved["continuationToken"],
            saved["tokens"],
        )
        if (
            normalized != items
            or phase not in ("inventory", "definitions")
            or type(saved["nextItem"]) is not int
            or not 0 <= saved["nextItem"] <= len(items)
            or type(saved["healthy"]) is not bool
            or not isinstance(tokens, list)
            or len(tokens) != len(set(tokens))
            or any(not isinstance(t, str) or not t for t in tokens)
            or (
                token is not None
                and (not isinstance(token, str) or not token or tokens[-1:] != [token])
            )
            or (token is None and phase == "inventory" and tokens)
            or (
                phase == "inventory"
                and (
                    saved["nextItem"] != 0
                    or saved["operationId"] is not None
                    or saved["inventoryFile"] is not None
                )
            )
            or (phase == "definitions" and token is not None)
            or not isinstance(saved["evidence"], list)
            or any(
                not isinstance(path, str)
                or re.fullmatch(
                    r"fabricitemdefinitions/\d{4}/\d{2}/\d{2}/[0-9a-f]{32}/manifest\.json",
                    path,
                )
                is None
                for path in saved["evidence"]
            )
            or (phase == "definitions" and not isinstance(saved["inventoryFile"], str))
        ):
            raise ValueError
        if saved["operationId"] is not None:
            if saved["nextItem"] >= len(items):
                raise ValueError
            if str(UUID(saved["operationId"])) != saved["operationId"]:
                raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("Invalid definition progress; requests blocked") from None
    return saved


async def main(context: Context | None = None) -> bool:
    """Capture definitions without executing notebooks or starting pipelines.

    Admin inventory is tenant-wide; resource-level read/write permissions are
    still required for exports. Missing/denied/invalid items fail coverage, not
    successful empty observations. Captured code/JSON requires restricted storage.
    """
    if context is None:
        raise RuntimeError("Context is None")
    progress = _progress(
        await context.fm.read_snapshot("fabricitemdefinitions/", "progress.json")
    )
    if progress["evidence"]:
        folder, name = progress["evidence"][-1].rsplit("/", 1)
        previous = await context.fm.read_snapshot(folder + "/", name)
        if not isinstance(previous, dict) or previous.get("finished") is not True:
            progress["healthy"] = False
    collection = _Definitions(
        context,
        "fabricitemdefinitions",
        "Tenant admin inventory of Notebook/DataPipeline; per-item read/write access "
        "required. Static notebook inference only, not actual run I/O. Pipeline JSON "
        "is captured without activity parsing. Definitions can contain sensitive values.",
        interval=19,
    )
    collection.durable_gate = True
    # Leave a request/storage reserve inside a bounded Function invocation slice.
    collection.request_deadline = asyncio.get_running_loop().time() + 85
    await collection.start()

    async def persist():
        await context.fm.save_snapshot(
            "fabricitemdefinitions/", "progress.json", progress
        )

    async def finish(complete):
        await persist()
        collection.execution.update(
            {
                "phase": progress["phase"],
                "nextItem": progress["nextItem"],
                "inventoryFile": progress["inventoryFile"],
                "evidence": progress["evidence"][:-1],
                "sweepComplete": progress["phase"] == "definitions"
                and progress["nextItem"] == len(progress["items"]),
            }
        )
        result = await collection.finish(complete)
        if collection.execution["sweepComplete"]:
            await context.fm.save_snapshot(
                "fabricitemdefinitions/", "progress.json", {"finished": True}
            )
        return result

    progress["evidence"].append(collection.path + "manifest.json")
    await persist()
    while progress["phase"] == "inventory":
        token = progress["continuationToken"]
        endpoint = "admin/items" + (
            f"?continuationToken={quote(token, safe='')}" if token else ""
        )
        response = await collection.page(endpoint, "itemEntities")
        if "ERROR" in response:
            return await finish(False)
        try:
            incoming = _inventory(response["itemEntities"])
            merged = [
                {
                    "id": item["itemId"],
                    "workspaceId": item["workspaceId"],
                    "type": item["type"],
                }
                for item in progress["items"] + incoming
            ]
            selected = _inventory(merged)
        except (ValueError, TypeError):
            collection.errors.append("Invalid definition inventory")
            return await finish(False)
        next_token = response.get("continuationToken")
        if next_token and (
            next_token in progress["tokens"] or len(progress["tokens"]) >= 10000
        ):
            collection.errors.append("Definition discovery pagination safety limit")
            return await finish(False)
        progress["items"] = selected
        progress["continuationToken"] = next_token
        if next_token:
            progress["tokens"].append(next_token)
        else:
            await collection.snapshot("inventory", "admin/items", {}, selected)
            progress["phase"] = "definitions"
            progress["inventoryFile"] = collection.path + "inventory.json"
        await persist()
    collection.execution = {
        "inventoryComplete": True,
        "discoveredItems": len(progress["items"]),
    }
    collection.interval = 1
    while progress["nextItem"] < len(progress["items"]):
        item = progress["items"][progress["nextItem"]]
        endpoint = f"workspaces/{item['workspaceId']}/"
        if item["type"] == "Notebook":
            endpoint += f"notebooks/{item['itemId']}/getDefinition?format=ipynb"
        else:
            endpoint += f"dataPipelines/{item['itemId']}/getDefinition"
        body = await collection.definition(endpoint, progress, persist)
        if collection.deferred:
            return await finish(False)
        records = None
        if body is not None:
            try:
                records = [_decode(body, item["type"])]
            except (ValueError, TypeError, RecursionError):
                collection.errors.append("Invalid definition content")
        success = await collection.snapshot(
            f"{item['workspaceId']}_{item['itemId']}", endpoint, item, records
        )
        progress["healthy"] = success and progress["healthy"]
        progress["nextItem"] += 1
        progress["operationId"] = None
        await persist()
    return await finish(progress["healthy"])
