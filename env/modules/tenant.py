import os
import json

import asyncio
import time
import requests

from datetime import datetime, timedelta

####### CATALOG PRECONFIGURATION #######
catalog_types = ["scan","snapshots"]
today = datetime.now()
reset  = True
####### CATALOG PRECONFIGURATION #######


async def main(context=None):
    """
    Tenant Settings
    """
    if context is None:
        raise RuntimeError("Context is None")
    
##################### INTIALIZE THE CONFIGURATION #####################
    
    # get POWER BI context and settings -- this call must be synchronous
    
    headers = context.clients['tenant'].get_headers()
    headers['Content-Type'] = 'application/json'

    today = datetime.now()

    lakehouse_dir = f"tenant/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"

##################### INTIALIZE THE CONFIGURATION #####################

    url = "https://api.fabric.microsoft.com/v1/admin/tenantsettings"

    response = requests.get(url=url, headers=headers)
    if response.status_code == 200:
        result = response.json()
        await context.fm.save(path=lakehouse_dir, file_name="tenant-settings.json", content=result)
#        dc = await FF.create_directory(file_system_client=FF.fsc, directory_name=lakehouse_dir)
#        await FF.write_json_to_file(directory_client=dc, file_name="tenant-settings.json", json_data=result)

# TODO: Fix error that comes from return application/json
# doesn't kill the job but does throw an error

if __name__ == "__main__":
    asyncio.run(main())

