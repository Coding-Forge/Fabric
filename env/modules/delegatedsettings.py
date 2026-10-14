import asyncio

from env.context import utc_now
from env.utility.admin_paging import fetch_all_pages

_BASE_URL = "https://api.fabric.microsoft.com/v1/admin"
_SCOPES = ("capacities", "domains", "workspaces")


async def main(context=None):
    """
    Delegated Settings

    Reads the delegated tenant setting overrides of capacities, domains and
    workspaces (admin API, 10000 items per page, 25 requests per minute) and saves
    each to ``delegatedsettings/<scope>/YYYY/MM/DD/<scope>.json``. A failure of one
    scope does not prevent the others from being saved.

    :param context: Runtime context.
    :return: True if all three scopes were saved, otherwise False.
    :raises RuntimeError: If ``context`` is None.
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients["pbi"].get_headers()
    today = utc_now()
    date_path = f"{today.strftime('%Y')}/{today.strftime('%m')}/{today.strftime('%d')}/"

    success = True
    for scope in _SCOPES:
        url = f"{_BASE_URL}/{scope}/delegatedTenantSettingOverrides"
        overrides = await fetch_all_pages(
            context, url, headers, "value", f"DelegatedSettings ({scope})"
        )
        if overrides is None:
            success = False
            continue
        await context.fm.save(
            f"delegatedsettings/{scope}/{date_path}", f"{scope}.json", overrides
        )

    return success


if __name__ == "__main__":
    asyncio.run(main())
