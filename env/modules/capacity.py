import asyncio
import json
import logging
import random
import time

from datetime import datetime, timedelta
from env.utility.file_management import File_Management
logging.basicConfig(filename='myapp.log', level=logging.INFO)

##### INTIALIZE THE CONFIGURATION #####
fm = File_Management()


##### INTIALIZE THE CONFIGURATION #####

async def get_capacity(url:str, pageCount:int, context=None):
    headers = context.get_context()

    response = await context.invokeAPI(url, headers=headers)
    pivotDate = datetime.now()

    content = response.get("value")

    index = str(pageCount).zfill(5)

    Path = f"capacity/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"
    await fm.save(path=Path, file_name=f"{datetime.now().strftime('%Y%m%d')}_{index}.capacity.json",content=content)

    try:
        continuationUri = response.get("continuationUri")
    except Exception as e:
        pass

    if continuationUri:
        if "continuationToken" in continuationUri:
            pageCount = pageCount + 1
            await get_capacity(url=continuationUri, pageCount=pageCount)



async def main(context=None):
    """
    Capacities
    """

    fm.content(context)

    logging.info('Started')

    url = "admin/capacities"
    # url = "https://api.powerbi.com/v1.0/myorg/admin/capacities"

    await get_capacity(url=url,pageCount=1, context=context)



if __name__ == "__main__":
    asyncio.run(main())
