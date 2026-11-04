import asyncio

from env.context import utc_now


async def main(context=None):
    """
    Refresh history
    """
    if context is None:
        raise RuntimeError("Context is None")
    
    # get POWER BI context and settings -- this call must be synchronous
    
    headers = context.clients['pbi'].get_headers()
    #headers['Content-Type'] = 'application/json'

    today = utc_now()

    lakehouse_dir = f"datasetrefresh/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    file_name = "workspaces.datasets.refreshes.json"


    # GET https://api.powerbi.com/v1.0/myorg/admin/groups?$expand=datasets
    rest_api = "admin/groups?$expand=datasets&$top=5000"

    # get a list of workspaces with datasets that have are refreshable
    result = await context.invokeAPI(rest_api=rest_api, headers=headers)
    
    if not result or "ERROR" in result:
        context.logger.error(f"Error: {result}")
        return False

    # GET https://api.powerbi.com/v1.0/myorg/groups/{groupId}/datasets/{datasetId}/refreshes

    resfresh_history = list()
    failures = 0

    for item in result.get('value', []):
        for dataset in item.get('datasets', []):
            if dataset.get('isRefreshable') is True and dataset.get('addRowsAPIEnabled') is False:
                rest_api = f"groups/{item['id']}/datasets/{dataset['id']}/refreshes"
                refreshes = await context.invokeAPI(rest_api=rest_api, headers=headers)

                if not refreshes or "ERROR" in refreshes:
                    # A dataset may be refreshable yet have no history, which returns 404
                    if refreshes and refreshes.get("status") == 404:
                        continue
                    failures += 1
                    context.logger.error(f"Refresh history failed for dataset {dataset['id']}: {refreshes}")
                    continue

                for refresh in refreshes.get('value', []):
                    if len(refresh)>0:
                        refresh['workspace_name'] = item['name']
                        refresh['workspace_id'] = item['id']
                        refresh['dataset_name'] = dataset['name']
                        refresh['dataset_id'] = dataset['id']
                        resfresh_history.append(refresh)

    # Save once after all datasets are processed
    await context.fm.save(path=lakehouse_dir, file_name=file_name, content=resfresh_history)

    # Report failure so the caller does not advance lastRun and the days are retried
    return failures == 0


if __name__ == "__main__":
    asyncio.run(main())

