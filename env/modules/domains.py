import asyncio
import json
import logging
import random
import time

from datetime import datetime, timedelta
logging.basicConfig(filename='myapp.log', level=logging.INFO)


async def main(context=None):
    """
    Domains
    """
    if context is None:
        raise RuntimeError("Context is None")
    
    headers = context.clients['pbi'].get_headers()

    logging.info('Started')

    if isinstance(context.current_state, str):
        lastRun = json.loads(context.current_state).get("activity").get("lastRun")
    else:
        lastRun = context.current_state.get("activity").get("lastRun")
    
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

    Path = f"domains/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"
    await context.fm.save(path=Path, file_name="domains.json",content=domain_workspaces)


if __name__ == "__main__":
    asyncio.run(main())
