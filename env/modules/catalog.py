import os
import json
import asyncio
import argparse

# from codetiming import Timer
import sys

from datetime import timedelta

from env.context import utc_now, utc_stamp
# from env.utility.helps import Bob

####### CATALOG PRECONFIGURATION #######
catalog_types = ["scan","snapshots"]
getInfoDetails = "lineage=true&datasourceDetails=true&getArtifactUsers=true&datasetSchema=false&datasetExpressions=false"
getModifiedWorkspacesParams = "excludePersonalWorkspaces=False&excludeInActiveWorkspaces=False"
FullScanAfterDays = 30
reset  = True

throttleErrorSleepSeconds = 3700
scanStatusSleepSeconds = 15
MAX_SCAN_STATUS_ATTEMPTS = 120   # 120 polls * 15s = 30 minutes per scan
MAX_SCAN_STATUS_ERRORS = 5       # consecutive status errors before the batch is failed
getInfoOuterBatchCount = 1500
getInfoInnerBatchCount = 100
runsInParallel = 16       


def RunFullScan(value=False):
    FullScan = value

async def main(context=None):
    """
    Catalog Scans (Catalog meta data)
    """

    if not context:
        raise RuntimeError("Context is None")
        return
    
    FullScan = False
    allWorkspaces = context.all_workspaces

    headers = context.clients['pbi'].get_headers()

    getModifiedWorkspacesParams = f"excludePersonalWorkspaces={context.exclude_personal_workspaces}&excludeInActiveWorkspaces={context.exclude_inactive_workspaces}"     # context.CatalogGetModifiedParameters
    getInfoDetails = context.CatalogGetInfoParameters

    if isinstance(context.current_state, str):
        LastRun = json.loads(context.current_state).get("catalog", {}).get("lastRun")
        LastFullScan = json.loads(context.current_state).get("catalog", {}).get("lastFullScan")
    else:
        LastRun = (context.current_state.get("catalog") or {}).get("lastRun")
        LastFullScan = (context.current_state.get("catalog") or {}).get("lastFullScan")

    if LastRun is None:
        LastRun = utc_stamp()

    if LastFullScan is None:
        LastFullScan = utc_stamp(utc_now() - timedelta(days=FullScanAfterDays))
        FullScan = True     

    lastRun_tm = context.convert_dt_str(LastRun)
    lastFullScan_tm = context.convert_dt_str(LastFullScan)

    # A full scan is due when the last one is at least FullScanAfterDays old
    if utc_now() - lastFullScan_tm >= timedelta(days=FullScanAfterDays):
        FullScan = True

    if FullScan:
        LastRun = (utc_now()-timedelta(days=30)).strftime("%Y-%m-%d")
    else:
        LastRun = lastRun_tm.strftime("%Y-%m-%d")

    #GET https://api.powerbi.com/v1.0/myorg/admin/workspaces/modified?modifiedSince={modifiedSince}&excludePersonalWorkspaces={excludePersonalWorkspaces}&excludeInActiveWorkspaces={excludeInActiveWorkspaces}

    ## if you do not pass the modifiedsince argument then all workspaces will be returned
    if allWorkspaces:
        # getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True&getArtifactUsers=true', data=batchBody, additional_headers={"Content-Type": "application/json"})
        rest_api = f"admin/workspaces/modified?{getModifiedWorkspacesParams}"
        # rest_api = f"admin/workspaces"
        # rest_api = f"admin/workspaces/getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True&getArtifactUsers=true', data=batchBody, additional_headers={'Content-Type': 'application/json'}"
    else:
        rest_api = f"admin/workspaces/modified?modifiedSince={LastRun}T00:00:00.0000000Z&{getModifiedWorkspacesParams}"


    print(f"using the following url: {rest_api}")

    result = await context.invokeAPI(rest_api=rest_api, headers=headers)

    workspaces = list()

    if not result or "ERROR" in result or "error" in result:
        context.logger.error(f"Error was thrown: {result}")
        return False

    # The API returns {"value": [...]} — unwrap the list
    workspace_list = result.get("value", result) if isinstance(result, dict) else result
    for workspace in workspace_list:
        if isinstance(workspace, dict):
            workspaces.append(workspace.get("id"))

    if not workspaces:
        context.logger.info("No modified workspaces found for the time period searched")
        return True
    # The first thing is to get all the workspaces that have been modified
    # Split into groups of 500
    # scroll through the list of workspaces and get the scan results for each workspace
        # and split each group as evenly as possible into 16 groups
        # and then run the scan results for each group of 500 workspaces
    # Split workspaceScanResults into groups of 500
    # The list is now a list of lists of up to 500 workspaces each that is partitioned into 16 subgroups
    # Split each group into 16 subgroups as evenly as possible
    # Each of the 16 subgroups is then run in parallel
    # Access the groups by using subgroups[][] and then run the scan results for each group of 500 workspaces

    # NOTE: 'ValidateInput does not support more then 100 workspace Ids in one call'

    def create_groups(input_list, group_size):
        # Create groups of the specified size
        groups = [input_list[i:i + group_size] for i in range(0, len(input_list), group_size)]
        return groups

    # Example usage
    input_list = workspaces
    group_size = 100
    groups = create_groups(input_list, group_size)

    # return groups

    # subgroups = []
    # for group in groups_of_500:
    #     items_per_subgroup = len(group) // runsInParallel
    #     remainder = len(group) % runsInParallel
    #     start_index = 0
    #     subgroup = []
    #     for i in range(runsInParallel):
    #         end_index = start_index + items_per_subgroup
    #         if i < remainder:
    #             end_index += 1
    #         subgroup.append(group[start_index:end_index])
    #         start_index = end_index
    #     subgroups.append(subgroup)

    # for groups in subgroups:
    #     for subgroup in groups:
    #         await work_queue.put(subgroup)

    work_queue = asyncio.Queue()
    for i, group in enumerate(groups):
        # print(f"Group {i+1}: {len(group)} items")
        await work_queue.put(group)

    # put all groups into the queue
    # build in a sleep for 10 seconds every 15 groups
    # to avoid throttling

    async def get_workspace_info(workspace_groups, FullScan=False,fileIndex=0, headers=None) -> bool:
        """Start a scan for a group of workspaces, poll until done and save the result.

        :return: True when the scan result was saved, False on any failure.
        """
        body = {
            "workspaces":workspace_groups
        }

        rest_api = "admin/workspaces/getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True"
        
        result = None
        try:
            result = await context.invokeAPI(rest_api=rest_api, headers=headers, json=body)
        except Exception as e:
            context.logger.error(f"Error getting lineage: {e} with result: {result}")
            await asyncio.sleep(60*3)
            return False

        if result is None or "ERROR" in result:
            context.logger.error(f"getInfo failed for batch {fileIndex}: {result}")
            return False

        workspaceScanResult = result
        scanId = workspaceScanResult.get("id")
        attempts = 0
        consecutiveErrors = 0

        while workspaceScanResult.get("status") in ["Running", "NotStarted"]:
            if attempts >= MAX_SCAN_STATUS_ATTEMPTS:
                context.logger.error(f"Scan {scanId} did not finish after {attempts} status checks; failing the batch")
                return False
            attempts += 1

            await asyncio.sleep(scanStatusSleepSeconds)

            statusResult = await context.invokeAPI(rest_api=f"admin/workspaces/scanStatus/{scanId}", headers=headers)

            if not statusResult or "ERROR" in statusResult:
                consecutiveErrors += 1
                context.logger.error(f"Scan status error for {scanId} ({consecutiveErrors}/{MAX_SCAN_STATUS_ERRORS}): {statusResult}")
                if consecutiveErrors >= MAX_SCAN_STATUS_ERRORS:
                    return False
                continue

            consecutiveErrors = 0
            workspaceScanResult["status"] = statusResult.get("status")

        if workspaceScanResult.get("status") != "Succeeded":
            context.logger.error(f"Scan {scanId} ended with status {workspaceScanResult.get('status')}")
            return False

        scanResult = await context.invokeAPI(rest_api=f"admin/workspaces/scanResult/{scanId}", headers=headers)

        if not scanResult or "ERROR" in scanResult:
            context.logger.error(f"Did not get scan results for scan {scanId}: {scanResult}")
            return False

        today = utc_now()
        path = f"catalog/scans/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
        file_name = "scanResults.fullscan.json" if FullScan else "scanResults.json"
        index = str(fileIndex).zfill(5)
        file_name = f"{today.strftime('%Y%m%d')}_{index}.{file_name}"
        print(f"Saving scan results to {file_name}")

        await context.fm.save(path=path, file_name=file_name, content=scanResult)
        return True

    failures = 0
    counter = int()
    batch_number = int()
    for i in range(0, len(groups), 16):
        batch_number += 1
        print(f"Processing batch number {batch_number} of {-(-len(groups)//16)} batches")

        batch = groups[i:i+16]

        # Refresh the token per batch (MSAL caches it) so long runs do not hit 401
        headers = context.clients['pbi'].get_headers()

        # Run up to 16 scans concurrently; each polls scanStatus with sleeps
        first_index = counter + 1
        counter += len(batch)
        outcomes = await asyncio.gather(
            *(
                get_workspace_info(workspace_groups=item, FullScan=FullScan, fileIndex=first_index + offset, headers=headers)
                for offset, item in enumerate(batch)
            ),
            return_exceptions=True,
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                context.logger.error(f"Scan group raised: {outcome}")
            if outcome is not True:
                failures += 1

        # pause between batches to avoid throttling, without blocking the event loop;
        # no pause is needed after the final batch
        if i + 16 < len(groups):
            await asyncio.sleep(30)

    if failures:
        context.logger.error(f"Catalog finished with {failures} failed scan group(s); lastFullScan not updated")
        return False

    # Persist lastFullScan so the next run is incremental until the full-scan interval elapses
    if FullScan and isinstance(context.current_state, dict):
        context.current_state.setdefault("catalog", {})["lastFullScan"] = utc_stamp()

    return True

    # while not work_queue.empty():
    #     counter += 1
    #     # a max of 16 parallel runs
    #     if counter % 17 == 0:
    #         print(f"Sleeping for {60} seconds to avoid throttling")
    #         time.sleep(60)

    #     subgroup = await work_queue.get()
    #     try:
    #         print(f"Processing subgroup {counter} of {len(groups)} groups of workspaces that contain {len(subgroup)} workspaces")
    #         if len(subgroup) > 0:
    #             await get_workspace_info(workspace_groups=subgroup, FullScan=FullScan,fileIndex=counter, headers=headers)
    #     # Try to catch any 429 errors
    #     except Exception as e:
    #         context.logger.error(f"Getting workspace info Error: {e} - sleeping for {throttleErrorSleepSeconds} seconds")
    #         current_time = datetime.now()
    #         duration = current_time - process_time

    #         # Calculate the difference
    #         difference = one_hour - duration

    #         # Ensure the difference is not negative
    #         if difference.total_seconds() > 0:
    #             # Sleep for the difference duration
    #             print(f"Sleeping for {difference.total_seconds()} seconds to avoid throttling due to a maximum of 500 reqeusts per hour")
    #             time.sleep(difference.total_seconds())
    #             # should sleep for the difference of the hour and resume with the same group
    #             await get_workspace_info(workspace_groups=subgroup, FullScan=FullScan,fileIndex=counter, headers=headers)
    #         else:
    #             print("The duration between the two datetimes is greater than or equal to one hour.")

    #         process_time = current_time
    #         print(f"Sleeping for {60*3} seconds to avoid throttling due to a maximum of 500 reqeusts per hour")
    #         # time.sleep(60*3)
            



if __name__ == "__main__":
    asyncio.run(main())