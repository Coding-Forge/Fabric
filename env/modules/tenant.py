import asyncio

from env.context import utc_now


async def main(context=None):
    """
    Tenant Settings
    """
    if context is None:
        raise RuntimeError("Context is None")
    
##################### INTIALIZE THE CONFIGURATION #####################
    
    # get POWER BI context and settings -- this call must be synchronous
    
    headers = context.clients['tenant'].get_headers()
    headers['Content-Type'] = 'application/json'

    today = utc_now()

    lakehouse_dir = f"tenant/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"

##################### INTIALIZE THE CONFIGURATION #####################

    url = context.get_fabric_url("v1/admin/tenantsettings")

    result = await context.invokeAPI(rest_api=url, headers=headers)
    if not result or "ERROR" in result:
        context.logger.error(f"Tenant settings request failed: {result}")
        return False

    await context.fm.save(path=lakehouse_dir, file_name="tenant-settings.json", content=result)

# TODO: Fix error that comes from return application/json
# doesn't kill the job but does throw an error

if __name__ == "__main__":
    asyncio.run(main())

