import asyncio

from env.context import utc_now
from env.utility.admin_paging import fetch_all_pages


async def main(context=None):
    """
    Git Connections

    Lists the Git connections of workspaces in the tenant (preview admin API,
    1000 items per page, 25 requests per minute) and saves them to
    ``gitconnections/YYYY/MM/DD/gitconnections.json``.

    :param context: Runtime context.
    :return: True on success, False if the request failed (for example when the
        preview API is unavailable or not permitted).
    :raises RuntimeError: If ``context`` is None.
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients["pbi"].get_headers()
    url = "https://api.fabric.microsoft.com/v1/admin/workspaces/discoverGitConnections"

    connections = await fetch_all_pages(
        context, url, headers, "value", "GitConnections"
    )
    if connections is None:
        return False

    today = utc_now()
    path = f"gitconnections/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    await context.fm.save(path, "gitconnections.json", connections)
    return True


if __name__ == "__main__":
    asyncio.run(main())
