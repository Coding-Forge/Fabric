import os
import json

import asyncio
import time

#from ..utility.fab2 import File_Table_Management
from datetime import datetime, timedelta

####### CATALOG PRECONFIGURATION #######
catalog_types = ["scan","snapshots"]
today = datetime.now()
getInfoDetails = "lineage=true&datasourceDetails=true&getArtifactUsers=true&datasetSchema=false&datasetExpressions=false"
getModifiedWorkspacesParams = "excludePersonalWorkspaces=False&excludeInActiveWorkspaces=False"
FullScanAfterDays = 30
reset  = True
####### CATALOG PRECONFIGURATION #######

async def main(context=None):
    """
    Catalog Snapshots (Published Apps)
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients['pbi'].get_headers()
    lakehouse_catalog = f"catalog/"

    if isinstance(context.current_state, str):
        LastRun = json.loads(context.current_state).get("activity").get("lastRun")
        LastFullScan = json.loads(context.current_state).get("catalog").get("lastFullScan")
    else:
        LastRun = context.current_state.get("catalog").get("lastRun")
        LastFullScan = context.current_.get("catalog").get("lastFullScan")

    if LastRun is None:
        LastRun = datetime.now()

    if LastFullScan is None:
        LastFullScan = datetime.now()        

    lastRun_tm = context.convert_dt_str(LastRun)
    lastFullScan_tm = context.convert_dt_str(LastFullScan)

    pivotScan = lastRun_tm + timedelta(days=-30)
    pivotFullScan = lastFullScan_tm + timedelta(days=-30)    

# create a file structure for the api results
    #scans = f"scan/{today.strftime('%Y')}/{today.strftime('%m')}"
    snapshots =f"snapshots/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"

    snapshotFiles = list()

    # TODO: get all the scans for apps
    filePath = f"{snapshots}apps.json"
    snapshotFiles.append(filePath)
    
    rest_api = "admin/apps?$top=5000&$skip=0"
    try:
        result = await context.invokeAPI(rest_api=rest_api, headers=headers)
    except Exception as e:
        context.logger.error(f"Error: {e}")
    
    # check to see if the filepath already exists
    if "ERROR" not in result:

        ## check if file already exists
        path = f"{lakehouse_catalog}{snapshots}"

        try:

            #only grab the value section from result
            info=result.get("value")
            await context.fm.save(path=path, file_name="apps.json", content=info)

            #await FF.write_json_to_file(directory_client=dc, file_name="apps.json", json_data=result)
        except TypeError as e:
            context.logger.error(f"Please fix the async to handle the Error: {e} -- is this the issue")
    else:
        context.logger.error(f"Error: {result}")
    
    
if __name__ == "__main__":
    asyncio.run(main() )


