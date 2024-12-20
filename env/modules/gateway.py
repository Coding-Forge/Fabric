import asyncio
import json
import requests
from datetime import datetime

async def main(context=None):
    """
    Gateways
    """
    
    if not context:
        raise RuntimeError("Context is None")
    
    headers = context.clients['pbi'].get_headers()
    headers['content-type'] = 'application/json'
    headers['pragma'] = 'no-cache'

    
# GET https://api.powerbi.com/v1.0/myorg/gateways
    
    api_url = 'https://api.powerbi.com/v1.0/myorg/gateways'
    response = requests.get(url=api_url, headers=headers)
    results = response.json()

    gateways = list()
    for gateway in results['value']:
        gateways.append(gateway.get("id"))

    today = datetime.today()
    path = f'gateways/{today.strftime("%Y")}/{today.strftime("%m")}/{today.strftime("%d")}/'

    await context.fm.save(path=path, file_name='gateways.json', content=json.dumps(results['value']))

    status = list()
    users = list()
    datasources = list()
    datasource_details = list()
    status_base = {   
        "datasourceId":"",
        "gatewayId":"",
        "error":
        {
            "code":"success",
            "pbi.error":{ 
                "code":"0",
                "parameters":{},
                "details":[],
                "exceptionCulprit":0
            }
        }
    }

    r = list()
    for id in gateways:
        response = requests.get(f'https://api.powerbi.com/v1.0/myorg/gateways/{id}/datasources', headers=headers)
        doc_results = response.json()
        r.append(doc_results['value'])   

    gateways = list()

    for i in range(0, len(r)):
        if isinstance(r[i], list):
            for j in range(0, len(r[i])):
                gateways.append(r[i][j])
        else:
            gateways.append(r[i])


    for i in range(0,len(gateways)):
        api_users = f'https://api.powerbi.com/v1.0/myorg/gateways/{gateways[i]["gatewayId"]}/datasources/{gateways[i]["id"]}/users'
        response = requests.get(api_users, headers=headers)
        results = response.json()

        if "value" in results:
            for l in range(0,len(results['value'])):
                results['value'][l]['datasourceId'] = gateways[i]["id"]
                results['value'][l]['gatewayId'] = gateways[i]["gatewayId"]
                users.append(results['value'][l])

    for i in range(0,len(gateways)):
        api_status = f'https://api.powerbi.com/v1.0/myorg/gateways/{gateways[i]["gatewayId"]}/datasources/{gateways[i]["id"]}/status'
        
        response = requests.get(api_status, headers=headers)
        if response.ok:
            # response.json() is actually empty when it is a success
            
            status_base['datasourceId'] = gateways[i]["id"]
            status_base['gatewayId'] = gateways[i]["gatewayId"]
            status_base.get("error").get("pbi.error").get("details").append({"message":"success","detail":response.status_code})    
            status.append(status_base)
        else:
            results = json.loads(response.text)
            results["datasourceId"] = gateways[i]["id"]
            results["gatewayId"] = gateways[i]["gatewayId"]
            results.get("error").get("pbi.error").get("details").append({"message":"cannot connect","detail":response.status_code})    
            status.append(results)

    for i in range(0,len(gateways)):
        api_datasource = f'https://api.powerbi.com/v1.0/myorg/gateways/{gateways[i]["gatewayId"]}/datasources/{gateways[i]["id"]}'
        response = requests.get(api_datasource, headers=headers)
        results = response.json()
        results.pop('@odata.context')
        datasource_details.append(results)

    await context.fm.save(path=path, file_name='status.json', content=json.dumps(status))
    await context.fm.save(path=path, file_name='users.json', content=json.dumps(users))
    await context.fm.save(path=path, file_name='datasources.json', content=json.dumps(gateways))
    await context.fm.save(path=path, file_name='datasource_details.json', content=json.dumps(datasource_details))


if __name__ == "__main__":
    asyncio.run(main())