import asyncio

from env.context import utc_now
from env.utility.admin_paging import fetch_all_pages

_ENDPOINTS = {
    "linksSharedToWholeOrganization": "widelysharedlinks_organization.json",
    "publishedToWeb": "widelysharedlinks_publishedtoweb.json",
}


async def main(context=None):
    """
    Widely Shared Links

    Reads artifacts shared with the whole organization and published to the web
    (Power BI admin API, 200 requests per hour) and saves each to
    ``widelysharedlinks/YYYY/MM/DD/``. A failure of one endpoint does not prevent
    the other from being saved.

    :param context: Runtime context.
    :return: True if both endpoints were saved, otherwise False.
    :raises RuntimeError: If ``context`` is None.
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients["pbi"].get_headers
    today = utc_now()
    path = f"widelysharedlinks/{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"

    success = True
    for endpoint, file_name in _ENDPOINTS.items():
        entities = await fetch_all_pages(
            context,
            context.get_powerbi_url(f"admin/widelySharedArtifacts/{endpoint}"),
            headers,
            "artifactAccessEntities",
            f"WidelySharedLinks ({endpoint})",
        )
        if entities is None:
            success = False
            continue
        await context.fm.save(path, file_name, entities)

    return success


if __name__ == "__main__":
    asyncio.run(main())
