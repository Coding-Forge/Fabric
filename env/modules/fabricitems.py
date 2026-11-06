import asyncio

from env.context import utc_now


async def main(context=None):
    """
    Fabric Items
    """


    if context is None:
        raise RuntimeError("Context is None")
    headers = context.clients['tenant'].get_headers

    today = utc_now()
    url = context.get_fabric_url("v1/admin/items")
    pageIndex = 1
    seen_urls = set()
    while url:
        if not isinstance(url, str) or url in seen_urls:
            context.logger.error("FabricItems pagination is invalid or repeated")
            return False
        seen_urls.add(url)
        file_index = str(pageIndex).zfill(5)
        response = await context.invokeAPI(url, headers=headers)
        if (
            not isinstance(response, dict)
            or "ERROR" in response
            or "error" in response
            or not isinstance(response.get("itemEntities"), list)
        ):
            context.logger.error("FabricItems page failed; inventory is incomplete")
            return False
        Path = f"items/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
        await context.fm.save(path=Path, file_name=f"fabricitems_{file_index}.json", content=response.get("itemEntities"))

        url = response.get("continuationUri")
        if url is not None and not isinstance(url, str):
            context.logger.error("FabricItems returned an invalid continuation URI")
            return False
        pageIndex += 1
    return True

if __name__ == "__main__":
    asyncio.run(main())
