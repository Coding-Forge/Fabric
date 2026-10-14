import asyncio
import json

from datetime import datetime, timedelta

from env.context import utc_now, utc_stamp

# The Power BI activity events API only retains 30 days of data
MAX_LOOKBACK_DAYS = 30


async def main(context=None):
    """
    Activity    
    """
    if context is None:
        raise RuntimeError("Context is None")

    print(f"What is current state {context.current_state}")

    if isinstance(context.current_state, str):
        lastRun = json.loads(context.current_state).get("activity", {}).get("lastRun")
    else:
        lastRun = (context.current_state.get("activity") or {}).get("lastRun")

    # if lastRun is recorded then proceed from there
    lastRun_tm = context.convert_dt_str(lastRun)
    pivotDate = lastRun_tm.replace(hour=0, minute=0, second=0, microsecond=0)

    # The activity events API only retains 30 days, so never start further back than that
    earliest = (utc_now() - timedelta(days=MAX_LOOKBACK_DAYS)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if pivotDate < earliest:
        context.logger.warning(f"Activity start {pivotDate} is older than {MAX_LOOKBACK_DAYS} days; clamping to {earliest}")
        pivotDate = earliest

    async def record_audits(path, audit, pivotDate, pageIndex=1):
        pageIndex = str(pageIndex).zfill(5)
        lakehouseFile = f"{pivotDate.strftime('%Y%m%d')}_{pageIndex}.json"

        await context.fm.save(path=path, file_name=lakehouseFile, content=audit)

    async def activity_events(url=None, headers=None, pivotDate=None, pageIndex=1) -> bool:
        """Fetch one page of activity events (and follow continuation URIs).

        :return: True when every page was retrieved, False when any request failed.
        """
        audits = list()

        result = await context.invokeAPI(rest_api=url, headers=headers)

        if not result or "ERROR" in result:
            context.logger.error(f"Activity events request failed for {pivotDate:%Y-%m-%d}: {result}")
            return False

        if result.get("activityEventEntities"):
            audits.append(result.get("activityEventEntities"))

        # create the folder structure for the output path
        lakehousePath = f"activity/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"

        # do a for loop until all json arrays in audits are read and written to storage
        for audit in audits:
            await record_audits(path=lakehousePath, audit=audit, pivotDate=pivotDate, pageIndex=pageIndex)

        continuationUri = result.get("continuationUri")
        if continuationUri and "continuationToken" in continuationUri:
            head = dict(headers)
            head['Content-Type'] = 'application/json'

            return await activity_events(url=continuationUri, headers=head, pivotDate=pivotDate, pageIndex=pageIndex + 1)

        return True

    headers = context.clients['pbi'].get_headers()

    async def get_activity(pivotDate=pivotDate) -> bool:
        while (pivotDate<utc_now()):
            # keep the start and end time within a 24 hour period by adding 24 hours and removing 1 second 
            nextDate = (pivotDate + timedelta(hours=24)) + timedelta(seconds=-1)
            rest_api = f"admin/activityevents?startDateTime='{pivotDate.strftime('%Y-%m-%dT%H:%M:%SZ')}'&endDateTime='{nextDate.strftime('%Y-%m-%dT%H:%M:%SZ')}'"

            # Stop at the first failed day so the caller does not advance lastRun past it
            if not await activity_events(url=rest_api, headers=headers, pivotDate=pivotDate):
                return False

            pivotDate += timedelta(days=1)

            # Per-day checkpoint: a later failure resumes at the first unfinished day
            if pivotDate < utc_now() and isinstance(context.current_state, dict):
                entry = context.current_state.get("activity")
                if not isinstance(entry, dict):
                    entry = {}
                    context.current_state["activity"] = entry
                entry["lastRun"] = utc_stamp(pivotDate)

        return True

    return await get_activity()



if __name__ == "__main__":
    asyncio.run(main())
