import asyncio
import json
import logging
import random
import time

from datetime import datetime, timedelta
from ..utility.helps import Bob
from env.utility.file_management import File_Management
logging.basicConfig(filename='myapp.log', level=logging.INFO)


async def main(context=None):
    """
    Domains
    """
    
    context = context
    headers = context.get_context()

    logging.info('Started')
    fm = File_Management()
    fm.content(context)

    try:
        config = await fm.read(file_name="state.yaml")
    except Exception as e:
        print(f"Error: {e}")
        return

    if isinstance(config, str):
        config = json.loads(config)
    
    lastRun = config.get("domains",{}).get("lastRun")
    
    if not lastRun:
        lastRun = datetime.now()

    # if lastRun is recorded then proceed from there
    lastRun_tm = context.convert_dt_str(lastRun)
    pivotDate = lastRun_tm.replace(hour=0, minute=0, second=0, microsecond=0)
    # Your code here

    url = "https://api.fabric.microsoft.com/v1/admin/domains"

    response = await context.invokeAPI(url, headers=headers)

    domain_workspaces=[]

    for domain in response.get("domains"):
        domainId = domain['id']

        response = await context.invokeAPI(f"https://api.fabric.microsoft.com/v1/admin/domains/{domainId}/workspaces", headers=headers)
        for value in response.get("value"):
            if len(value) != 0:
                domain["workspace"] = value.get("displayName")
                domain["workspaceId"] = value.get("id")
                domain_workspaces.append(domain)

        domain_workspaces.append(domain)

    Path = f"domains/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/"
    await fm.save(path=Path, file_name="domains.json",content=domain_workspaces)


if __name__ == "__main__":
    asyncio.run(main())
