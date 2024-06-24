import asyncio
import json
import logging

from datetime import datetime, timedelta

logging.basicConfig(filename='myapp.log', level=logging.INFO)

async def main(context=None):
    """
    Activity    
    """
    if context is None:
        raise RuntimeError("Context is None")

    if isinstance(context.current_state, str):
        lastRun = json.loads(context.current_state).get("activity").get("lastRun")
    else:
        lastRun = context.current_state.get("activity").get("lastRun")

    # if lastRun is recorded then proceed from there
    lastRun_tm = context.convert_dt_str(lastRun)
    pivotDate = lastRun_tm.replace(hour=0, minute=0, second=0, microsecond=0)
    # Your code here

    async def record_audits(path, audit, pivotDate, pageIndex=1):
        pageIndex = str(pageIndex).zfill(5)
        lakehouseFile = f"{pivotDate.strftime('%Y%m%d')}_{pageIndex}.json"

        await context.fm.save(path=path, file_name=lakehouseFile, content=audit)
        flagNoActivity = False
    

    async def activity_events(url=None, headers=None, pivotDate=None, pageIndex=1):
        audits = list()

        result = await context.invokeAPI(rest_api=url, headers=headers)

        # check the https response code for 200
        if "ERROR" in result:
            logging.error(f"Error: {result}")
            innerLoop = False
        else:
            # this is common to both parts of the if statement
            if result.get("activityEventEntities"):
                audits.append(result.get("activityEventEntities"))

            # create the folder structure for the output path
            lakehousePath = f"activity/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"

            # do a for loop until all json arrays in audits are read and written to storage
            for audit in audits:
                await record_audits(path=lakehousePath, audit=audit, pivotDate=pivotDate, pageIndex=pageIndex)

            try:
                if result.get("continuationUri"):
                    continuationUri = result.get("continuationUri")

                    if "continuationToken" in continuationUri:
                        head = headers
                        head['Content-Type'] = 'application/json'

                        pageIndex+=1
                        await activity_events(url=continuationUri, headers=head, pivotDate=pivotDate, pageIndex=pageIndex)
            except Exception as e:
                print(f"Error: {e}")

    headers = context.clients['pbi'].get_headers()

    async def get_activity(pivotDate=pivotDate):
        while (pivotDate<datetime.now()):
            audits = list()
            pageIndex = 1
            flagNoActivity = True

            

            # keep the start and end time within a 24 hour period by adding 24 hours and removing 1 second 
            nextDate = (pivotDate + timedelta(hours=24)) + timedelta(seconds=-1)
            rest_api = f"admin/activityevents?startDateTime='{pivotDate.strftime('%Y-%m-%dT%H:%M:%SZ')}'&endDateTime='{nextDate.strftime('%Y-%m-%dT%H:%M:%SZ')}'"

            continuationUri=""
            result = None
            innerLoop = True
            # python does not have a do while so this is the best way 
            # just need to break out of the loop when a condition is met

            await activity_events(url=rest_api, headers=headers, pivotDate=pivotDate)                        

            pivotDate += timedelta(days=1)

    await get_activity()



if __name__ == "__main__":
    asyncio.run(main())
