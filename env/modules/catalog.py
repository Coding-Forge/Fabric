import os
import json
import time
import asyncio
import argparse

# from codetiming import Timer
import sys

from datetime import datetime, timedelta
# from env.utility.helps import Bob

####### CATALOG PRECONFIGURATION #######
catalog_types = ["scan","snapshots"]
today = datetime.now()
getInfoDetails = "lineage=true&datasourceDetails=true&getArtifactUsers=true&datasetSchema=false&datasetExpressions=false"
getModifiedWorkspacesParams = "excludePersonalWorkspaces=False&excludeInActiveWorkspaces=False"
FullScanAfterDays = 30
reset  = True

throttleErrorSleepSeconds = 3700
scanStatusSleepSeconds = 15
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

    getModifiedWorkspacesParams = f"excludePersonalWorkspaces={context.include_personal_workspaces}&excludeInActiveWorkspaces={context.exclude_inactive_workspaces}"     # context.CatalogGetModifiedParameters
    getInfoDetails = context.CatalogGetInfoParameters

    if isinstance(context.current_state, str):
        LastRun = json.loads(context.current_state).get("activity").get("lastRun")
        LastFullScan = json.loads(context.current_state).get("catalog").get("lastFullScan")
    else:
        LastRun = context.current_state.get("catalog").get("lastRun")
        LastFullScan = context.current_state.get("catalog").get("lastFullScan")

    if LastRun is None:
        LastRun = datetime.now()

    if LastFullScan is None:
        LastFullScan = datetime.now() - timedelta(days=30)
        FullScan = True     

    lastRun_tm = context.convert_dt_str(LastRun)
    lastFullScan_tm = context.convert_dt_str(LastFullScan)

    # pivotScan = lastRun_tm + timedelta(days=-30)
    # pivotFullScan = lastFullScan_tm + timedelta(days=-30)    

    if abs(lastFullScan_tm - lastRun_tm) >= timedelta(days=30):
        FullScan = True
        LastRun = (datetime.now()-timedelta(days=30)).strftime("%Y-%m-%d")
    else:
        LastRun = lastRun_tm.strftime("%Y-%m-%d")

    #GET https://api.powerbi.com/v1.0/myorg/admin/workspaces/modified?modifiedSince={modifiedSince}&excludePersonalWorkspaces={excludePersonalWorkspaces}&excludeInActiveWorkspaces={excludeInActiveWorkspaces}

    ## if you do not pass the modifiedsince argument then all workspaces will be returned
    if allWorkspaces:
        # getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True&getArtifactUsers=true', data=batchBody, additional_headers={"Content-Type": "application/json"})
        rest_api = f"admin/workspaces/modified"
        # rest_api = f"admin/workspaces"
        # rest_api = f"admin/workspaces/getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True&getArtifactUsers=true', data=batchBody, additional_headers={'Content-Type': 'application/json'}"
    else:
        rest_api = f"admin/workspaces/modified?modifiedSince={LastRun}T00:00:00.0000000Z&{getModifiedWorkspacesParams}"
    result = await context.invokeAPI(rest_api=rest_api, headers=headers)

    workspaces = list()

    if result and "error" not in result:
        # Convert the JSON response to a pandas DataFrame
        for workspace in result:
            workspaces.append(workspace.get("id"))
    elif "error" in result:
        # Handle the error case
        context.logger.error(f"Error was thrown: {result}")
        return
    else:
        context.logger.info("No modified workspaces found for the time period searched")
        return
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

    async def get_workspace_info(workspace_groups, FullScan=False,fileIndex=0, headers=None):
        workspaceScanResults = []
        
        body = {
            "workspaces":workspace_groups
        }

        rest_api = "admin/workspaces/getInfo?lineage=True&datasourceDetails=True&datasetSchema=True&datasetExpressions=True"
        
        result = None
        try:
            # print(f"Getting lineage for {len(workspace_groups)} workspaces and the body is {body}")
            result = await context.invokeAPI(rest_api=rest_api, headers=headers, json=body)
        except Exception as e:
            print(f"Error getting lineage: {e} with result: {result}")
            time.sleep(60*3)


        if result is None:
             return "Result for getInfo is none {body}"
        elif "ERROR" in result:
            context.logger.error(f"Error: {result}")
        else:
            # print(f"what is the result: {result}")

            workspaceScanResults.append(result)
            for workspaceScanResult in workspaceScanResults:
                # print(f"Sleeping for {scanStatusSleepSeconds} seconds to prevent overloading the API with requests")
                # time.sleep(scanStatusSleepSeconds)
                while(workspaceScanResult.get("status") in ["Running", "NotStarted"]):
                    try:
                        # print(f"Getting scan status for workspace {workspaceScanResult.get('id')}")
                        rest_api = f"admin/workspaces/scanStatus/{workspaceScanResult.get('id')}"
                        result = await context.invokeAPI(rest_api=rest_api, headers=headers)
                    except Exception as e:
                        context.logger.error(f"Scan status Error: {e} - sleeping for {throttleErrorSleepSeconds} seconds")
                        await asyncio.sleep(throttleErrorSleepSeconds)


                    if "ERROR" in result:
                        context.logger.error(f"Error: {result}")
                    else:
                        workspaceScanResult["status"] = result.get("status")

                if workspaceScanResult is not None and  "status" in workspaceScanResult and "Succeeded" in workspaceScanResult["status"]:
                    id = workspaceScanResult.get("id")

                    # print(f"Getting scan results for scan {id}")
                    rest_api = f"admin/workspaces/scanResult/{id}"
                    scanResult = await context.invokeAPI(rest_api=rest_api, headers=headers)

                    # TODO: create a better check on whether scan results were returned or error thrown
                    if "ERRORs" in scanResult:
                        context.logger.error(f"Error: Did not get scan results for workspace {id}")
                    else:
                        today = datetime.now()
                        path = f"catalog/scans/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
                        #dc = await FF.create_directory(file_system_client=FF.fsc, directory_name=path)
                        try:
                            if FullScan:
                                file_name=f"scanResults.fullscan.json"
                            else:
                                file_name=f"scanResults.json"
                            
                            index = str(fileIndex).zfill(5)
                            file_name = f"{today.strftime('%Y%m%d')}_{index}.{file_name}"
                            print(f"Saving scan results to {file_name}")
                            
                            await context.fm.save(path=path, file_name=file_name, content=scanResult)
                            return "Saved"
                            #await FF.write_json_to_file(directory_client=dc, file_name="scanResults.json", json_data=scanResult)
                        except TypeError as e:
                            context.logger.error(f"Please fix the async to handle the Error: {e} -- is this the issue")
                else:
                    context.logger.error(f"Error: Did not get scan results for workspace")



    counter = int()
    batch_number = int()
    for i in range(0, len(groups), 16):
        batch_number += 1
        print(f"Processing batch number {batch_number} of {len(groups)//16} batches")

        batch = groups[i:i+16]
        item_number = int()
        
        # Process the batch
        for item in batch:
            counter += 1
            item_number += 1
            print(f"Processing item number {item_number}")
            output = await get_workspace_info(workspace_groups=item, FullScan=FullScan,fileIndex=counter, headers=headers)
            print(output)

        print("I sleeping")
        time.sleep(30)  # Pause for 10 minutes

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