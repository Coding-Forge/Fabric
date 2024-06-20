import asyncio
import requests
import json
import logging
import random
import time
from time import sleep

from datetime import datetime, timedelta
from env.utility.file_management import File_Management
logging.basicConfig(filename='myapp.log', level=logging.INFO)

##### INTIALIZE THE CONFIGURATION #####


##### INTIALIZE THE CONFIGURATION #####




async def main(context=None):
    """
    Roles
    """
    logging.info('Started')

    headers =  context.get_context()
    fm = File_Management()
    fm.content(context=context)


    response = requests.get("https://api.fabric.microsoft.com/v1/admin/workspaces", headers=headers)
    if response.ok:
        results = response.json()

    workspace = results.get("workspaces")

    items = list()

    for item in workspace:
        items.append(item["id"])

    items = set(items)
    workspace_lst = list()

    ceiling = len(items)
    cnt = 0
    for item in items:
        cnt+=1

        if len(workspace_lst) > ceiling:
            break

        if cnt <= ceiling:
            url = f"https://api.powerbi.com/v1.0/myorg/admin/groups/{item}?$expand=users"
        
            response = requests.get(url, headers=headers)
            if response.ok:
                results = response.json()
                workspace_lst.append(results)
            else:
                if response.status_code==429:
                    result = response.json()
                    print(f"Request limit reached. You must wait { int(result.get('message').split('.')[1].split(' ')[3])/60} minutes for the next request")
                    sleep(int(result.get('message').split('.')[1].split(' ')[3]))

    pivotDate = datetime.now()
    content = workspace_lst
    index = str(cnt).zfill(5)

    Path = f"roles/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/"
    await fm.save(path=Path, file_name=f"{datetime.now().strftime('%Y%m%d')}_{index}.roles.json",content=content)


if __name__ == "__main__":
    asyncio.run(main())
