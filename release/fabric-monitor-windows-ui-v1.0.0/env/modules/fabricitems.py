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

if __name__ == "__main__":
    asyncio.run(main())
