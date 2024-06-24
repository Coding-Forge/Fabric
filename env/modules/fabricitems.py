import asyncio
import json
import logging
import random
import time

from datetime import datetime, timedelta
logging.basicConfig(filename='myapp.log', level=logging.INFO)


async def main(context=None):
    """
    Fabric Items
    """

    logging.info('Started')

    headers = context.clients['pbi'].get_headers()

    today = datetime.now()
    async def get_data(url,pageIndex=1):
        pageIndex = str(pageIndex).zfill(5)
        response = await context.invokeAPI(url, headers=headers)
        Path = f"items/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
        await context.fm.save(path=Path, file_name=f"fabricitems_{pageIndex}.json",content=response.get("itemEntities"))

        try:
            continuationUri = response.get("continuationUri")
            if continuationUri:
                await get_data(continuationUri)
        except Exception as e:
            logging.info("No continuation uri")
            return

    url = "https://api.fabric.microsoft.com/v1/admin/items"
    await get_data(url)

    


if __name__ == "__main__":
    asyncio.run(main())
