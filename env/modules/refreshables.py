import os
import json
import asyncio
import time
import requests

from datetime import datetime, timedelta

####### Refresh History PRECONFIGURATION #######
today = datetime.now()
####### CATALOG PRECONFIGURATION #######


async def main(context=None):
    """
    Refreshables
    """
    if context is None:
        raise RuntimeError("Context is None")
    
    # get POWER BI context and settings -- this call must be synchronous
    headers = context.clients['tenant'].get_headers()
    today = datetime.now()

    lakehouse_dir = f"datasetrefreshable/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    file_name = "workspaces.datasets.refreshable.json"

   
    # GET https://api.powerbi.com/v1.0/myorg/admin/capacities/refreshables?$expand=capacity,group
    rest_api = "admin/capacities/refreshables?$expand=capacity,group"

    # get a list of workspaces with datasets that have are refreshable
    result = await context.invokeAPI(rest_api=rest_api, headers=headers)
    
    if "ERROR" in result:
        context.logger.error("ERROR", f"Error: {result}")
    else:
        await context.fm.save(path=lakehouse_dir, file_name=file_name,content=result['value'])

if __name__ == "__main__":
    asyncio.run(main())

