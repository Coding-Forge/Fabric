import asyncio
import json
import random
import time

from datetime import datetime, timedelta


async def main(context=None):
    """
    Workspaces in tenant
    """
    if context is None: 
        raise RuntimeError("Context is None")


    headers =  context.clients['pbi'].get_headers()

    url = "https://api.fabric.microsoft.com/v1/admin/workspaces"

    async def get_workspaces(url:str, pageCount:int):


        response = await context.invokeAPI(url, headers=headers)
        pivotDate = datetime.now()

        workspaces = response.get("workspaces")

        index = str(pageCount).zfill(5)

        Path = f"workspaces/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"
        await context.fm.save(path=Path, file_name=f"{datetime.now().strftime('%Y%m%d')}_{index}.workspaces.json",content=workspaces)

        try:
            continuationUri = response.get("continuationUri")
        except Exception as e:
            context.logger.error("ERROR", f"Error: {e}")
            pass

        if continuationUri:
            if "continuationToken" in continuationUri:
                pageCount = pageCount + 1
                await get_workspaces(url=continuationUri, pageCount=pageCount)

    await get_workspaces(url=url,pageCount=1)


if __name__ == "__main__":
    asyncio.run(main())
