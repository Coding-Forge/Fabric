import os
import json

import asyncio
import time
import requests

from datetime import datetime, timedelta

####### Refresh History PRECONFIGURATION #######
today = datetime.now()
####### CATALOG PRECONFIGURATION #######


async def main(context=None):
    """
    Refresh history
    """
    if context is None:
        raise RuntimeError("Context is None")
    
    # get POWER BI context and settings -- this call must be synchronous
    
    headers = context.clients['tenant'].get_headers()
    #headers['Content-Type'] = 'application/json'

    today = datetime.now()

    lakehouse_dir = f"datasetrefresh/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    file_name = "workspaces.datasets.refreshes.json"


    # GET https://api.powerbi.com/v1.0/myorg/admin/groups?$expand=datasets
    rest_api = "admin/groups?$expand=datasets&$top=5000"

    # get a list of workspaces with datasets that have are refreshable
    result = await context.invokeAPI(rest_api=rest_api, headers=headers)
    
    if "ERROR" in result:
        context.logger.error(f"Error: {result}")
    else:

        # GET https://api.powerbi.com/v1.0/myorg/groups/{groupId}/datasets/{datasetId}/refreshes

        resfresh_history = list()

        # A dataset may not have refresh history even though it is refreshable (marked as isRefreshable=True)
        # any dataset that does not have a refresh history will return a 404 error
        for item in result['value']:
            for dataset in item['datasets']:
                if dataset['isRefreshable']==True and dataset['addRowsAPIEnabled']==False:
                    rest_api = f"groups/{item['id']}/datasets/{dataset['id']}/refreshes"
                    try:
                        refreshes = await context.invokeAPI(rest_api=rest_api, headers=headers)
                        for refresh in refreshes['value']:
                            if len(refresh)>0:
                                resfresh_history.append(refresh)
                        
                        await context.fm.save(path=lakehouse_dir, file_name=file_name,content=resfresh_history)
                    except Exception as e:
                        pass
                        # This is basically a 404 error because there isn't any refresh history for this dataset


if __name__ == "__main__":
    asyncio.run(main())

