import asyncio
import json
from datetime import datetime, timedelta
import random
import time

import requests

async def main(context=None):
    """
    Capacity Metrics
    """

    continuationUri = None
    if context is None:
        raise RuntimeError("Context is None")

    impersonatedUserName = context.impersonatedUserName
    headers = context.clients['pbi'].get_headers()

    url = "admin/capacities/metrics"
    # url = "https://api.powerbi.com/v1.0/myorg/admin/capacities/metrics"

    async def get_capacity_metrics(url: str, pageCount: int):
        


        query = '''EVALUATE SUMMARIZECOLUMNS('CUDetail'[AutoScaleCapacityUnits], 'CUDetail'[Background], 'CUDetail'[Background Rejection %], 'CUDetail'[BackgroundPreview], 'CUDetail'[CU Limit], 'CUDetail'[CUs], 'CUDetail'[Interactive], 'CUDetail'[Interactive Delay %], 'CUDetail'[Interactive Rejection %], 'CUDetail'[InteractivePreview], 'CUDetail'[Peak6min Background Rejection %], 'CUDetail'[Peak6min Interactive Delay %], 'CUDetail'[SKU], 'CUDetail'[Start of Hour], 'CUDetail'[StartOf6min], 'CUDetail'[StartOfHour], 'CUDetail'[Threshold], 'CUDetail'[WindowEndTime], 'CUDetail'[WindowStartTime])'''        
        # results = get_fabric_capacity_metrics_data(context.capacity_metrics_dataset_id, query)

        payload = {
            "queries": [
                {
                "query": query,
                }
            ],
            "serializerSettings": {
                "includeNulls": "true"
            },
            "impersonatedUserName": impersonatedUserName
        }        
        datasetId = context.capacity_metrics_dataset_id
        url = f"datasets/{datasetId}/executeQueries"
   
        response = await context.invokeAPI(url, headers=headers, json=payload)

        if response is None:
            context.logger.error("ERROR", "Response is None")
            return

        content = response
        pivotDate = datetime.now()
        index = str(pageCount).zfill(5)

        Path = f"capacity_metrics/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"
        await context.fm.save(path=Path, file_name=f"{datetime.now().strftime('%Y%m%d')}_{index}.capacity_metrics.json", content=content)

        try:
            continuationUri = response.get("continuationUri")
        except Exception as e:
            context.logger.error("ERROR", f"Error: {e}")
            pass

        if continuationUri:
            if "continuationToken" in continuationUri:
                pageCount += 1
                await get_capacity_metrics(url=continuationUri, pageCount=pageCount)

    await get_capacity_metrics(url=url, pageCount=1)

if __name__ == "__main__":
    asyncio.run(main())