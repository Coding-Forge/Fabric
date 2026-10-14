import asyncio

from env.context import utc_now


async def main(context=None):
    """
    Graph
    """
    if context is None:
        raise RuntimeError("Context is None")

##################### INTIALIZE THE CONFIGURATION #####################
    # get POWER BI context and settings -- this call must be synchronous

    headers = context.clients['graph'].get_headers()
    headers['Content-Type'] = 'application/json'

    today = utc_now()

    lakehouse_catalog = f"graph/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    Groups = bool(context.GraphExtractGroups)
    
##################### INTIALIZE THE CONFIGURATION #####################

    graphUrl = context.clients['graph'].get_api_root()
    outputPath = f"{lakehouse_catalog}"
    graphCalls = [
        {'users':
            { 
                'GraphURL': f'{graphUrl}/users?$select=id,displayName,assignedLicenses,UserPrincipalName',
                'FilePath': 'users.json'
            }
        },
        {"subscribedSkus":
            {
            'GraphURL': f'{graphUrl}/subscribedSkus?$select=id,capabilityStatus,consumedUnits,prepaidUnits,skuid,skupartnumber,prepaidUnits',
            'FilePath': 'subscribedskus.json'
            }
        }
    ]

    if Groups:
        graphCalls.append(
            {"groups":
                {
                    'GraphURL': f'{graphUrl}/groups?$filter=securityEnabled eq true&$select=id,displayName',
                    'FilePath': 'groups.json'
                }
            }
        )

    failures = 0
    for call in graphCalls:
        for key, value in call.items():

            result = await context.invokeAPI(rest_api=value['GraphURL'], headers=headers)
            if not result or "ERROR" in result:
                failures += 1
                context.logger.error(f"Graph call {key} failed: {result}")
                continue

            info = result.get("value")

            await context.fm.save(path=lakehouse_catalog, file_name=value['FilePath'], content=info)

    return failures == 0
# TODO: Fix error that comes from return application/json
# doesn't kill the job but does throw an error

if __name__ == "__main__":
    asyncio.run(main())
