import asyncio
import requests
import json

import random
import time
from time import sleep

from datetime import datetime, timedelta


async def main(context=None):
    """
    Roles
    """
    if context is None:
        raise RuntimeError("Context is None")


    headers =  context.clients['pbi'].get_headers()


    items = set()
    continuationToken = None
    while True:

        if continuationToken == None:
            response = requests.get("https://api.fabric.microsoft.com/v1/admin/workspaces", headers=headers)
        else:
            response = requests.get(f"https://api.fabric.microsoft.com/v1/admin/workspaces?continuationToken='{continuationToken}'",headers=headers)

        if response.ok:
            results = response.json()

            workspace = results.get("workspaces")

            for item in workspace:
                items.add(item["id"])

            continuationToken =  results.get("continuationToken",[])

            if continuationToken == None:
                break

    ceiling = len(items)
    cnt = 0

    base_url = 'https://api.powerbi.com/v1.0/myorg/admin/groups?$expand=users&$top=5000'

    all_groups = []
    for i in range(0, ceiling, 5000):
        url = f'{base_url}&$skip={i}'
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            groups = response.json().get('value', [])
            all_groups.extend(groups)
        else:
            print(f'Error: {response.status_code}')
            break

    print(f'Total groups retrieved: {len(all_groups)}')
    
    
    pivotDate = datetime.now()
    content = all_groups
    index = str(cnt).zfill(5)

    Path = f"roles/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"
    await context.fm.save(path=Path, file_name=f"{datetime.now().strftime('%Y%m%d')}_{index}.roles.json",content=content)


if __name__ == "__main__":
    asyncio.run(main())
