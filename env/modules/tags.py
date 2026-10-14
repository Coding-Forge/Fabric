import asyncio

from env.context import utc_now
from env.utility.admin_paging import fetch_all_pages


async def main(context=None):
    """
    Tags

    Lists the tags defined in the tenant (admin API, 25 requests per minute) and
    saves them to ``tags/YYYY/MM/DD/tags.json``.

    :param context: Runtime context.
    :return: True on success, False if the request failed.
    :raises RuntimeError: If ``context`` is None.
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients["pbi"].get_headers()
    url = "https://api.fabric.microsoft.com/v1/admin/tags"

    tags = await fetch_all_pages(context, url, headers, "value", "Tags")
    if tags is None:
        return False

    today = utc_now()
    path = f"tags/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"
    await context.fm.save(path, "tags.json", tags)
    return True


if __name__ == "__main__":
    asyncio.run(main())
