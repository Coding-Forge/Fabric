import asyncio
import json

import random
import time

from datetime import datetime, timedelta


async def main(context=None):
    """
    Fabric Items
    """


    headers = context.clients['tenant'].get_headers()

    today = datetime.now()
    async def get_data(url, pageIndex=1):
        file_index = str(pageIndex).zfill(5)
        response = await context.invokeAPI(url, headers=headers)
        Path = f"items/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
        await context.fm.save(path=Path, file_name=f"fabricitems_{file_index}.json", content=response.get("itemEntities"))

        try:
            continuationUri = response.get("continuationUri")
            if continuationUri:
                await get_data(continuationUri, pageIndex=pageIndex + 1)
        except Exception as e:
            context.logger.error(f"Error paginating fabricitems: {e}")
            return

    url = context.get_fabric_url("v1/admin/items")
    await get_data(url)

    try:
        await get_lineage(context, headers, today)
    except Exception as e:
        context.logger.error(f"Error collecting item lineage: {e}")
        print(f"Lineage collection failed: {e}")


async def get_lineage(context, headers, today):
    """
    Upstream/downstream relations per item (Fabric Core beta API), saved as flat edge rows.
    """
    import requests

    items = []
    url = context.get_fabric_url("v1/admin/items")
    while url:
        for attempt in range(6):
            response = await context.invokeAPI(url, headers=headers)
            if "ERROR" not in response:
                break
            await asyncio.sleep(10 * (attempt + 1))
        else:
            break
        items.extend(response.get("itemEntities") or [])
        url = response.get("continuationUri")

    sem = asyncio.Semaphore(5)
    stats = {"ok": 0, "skipped": 0}
    stats_msg = {}

    def call(item_url):
        for _ in range(5):
            r = requests.get(item_url, headers=headers, timeout=60)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "5")))
                continue
            return r
        return r

    async def fetch(item, direction):
        item_id, ws_id = item.get("id"), item.get("workspaceId")
        if not item_id or not ws_id:
            return []
        endpoint = f"v1/workspaces/{ws_id}/items/{item_id}/relations/{direction}?beta=true"
        async with sem:
            r = await asyncio.to_thread(call, context.get_fabric_url(endpoint))
        if r.status_code != 200:
            stats["skipped"] += 1
            key = f"{item.get('type')}:{r.status_code}"
            stats[key] = stats.get(key, 0) + 1
            if key not in stats_msg:
                stats_msg[key] = r.text[:200]
            return []
        stats["ok"] += 1
        body = r.json()
        related = {i["id"]: i for i in body.get("items", [])}
        workspaces = {w["id"]: w.get("displayName") for w in body.get("workspaces", [])}
        rows = []
        for rel in body.get("relations", []):
            other = related.get(rel.get("dependentOnItemId")) if direction == "upstream" else related.get(rel.get("itemId"))
            other = other or {}
            rows.append({
                "QueryItemId": item_id,
                "QueryItemType": item.get("type"),
                "QueryWorkspaceId": ws_id,
                "Direction": direction,
                "ItemId": rel.get("itemId"),
                "DependentOnItemId": rel.get("dependentOnItemId"),
                "RelationType": rel.get("relationType"),
                "RelatedItemId": other.get("id"),
                "RelatedItemName": other.get("displayName"),
                "RelatedItemType": other.get("type"),
                "RelatedWorkspaceId": other.get("workspaceId"),
                "RelatedWorkspaceName": workspaces.get(other.get("workspaceId")),
            })
        return rows

    results = await asyncio.gather(*[fetch(i, d) for i in items for d in ("upstream", "downstream")])
    edges = [row for rows in results for row in rows]

    Path = f"lineage/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    await context.fm.save(path=Path, file_name="lineage_00001.json", content=edges)
    print(f"Lineage: {len(edges)} edges from {stats['ok']} calls ({stats['skipped']} unsupported/failed)")
    print({k: v for k, v in stats.items() if ":" in k})
    for k, v in stats_msg.items():
        context.logger.info(f"Lineage {k}: {v}")
        print(f"  {k}: {v}")

if __name__ == "__main__":
    asyncio.run(main())
