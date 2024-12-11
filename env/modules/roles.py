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
