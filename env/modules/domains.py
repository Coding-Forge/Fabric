import asyncio

from env.context import utc_now


async def main(context=None):
    """
    Domains
    """
    if context is None:
        raise RuntimeError("Context is None")

    headers = context.clients["tenant"].get_headers()

    # Use the current run date so a snapshot never lands in a prior day's folder.
    pivotDate = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)

    url = context.get_fabric_url("v1/admin/domains")

    response = await context.invokeAPI(url, headers=headers)

    if not response or "ERROR" in response:
        context.logger.error(f"Domains request failed: {response}")
        return False

    domain_workspaces = []

    domains = response.get("domains", [])
    if len(domains) == 0:
        return

    for domain in domains:
        domainId = domain["id"]

        response = await context.invokeAPI(
            context.get_fabric_url(f"v1/admin/domains/{domainId}/workspaces"),
            headers=headers,
        )

        if not response or "ERROR" in response:
            context.logger.error(
                f"Domain workspaces request failed for {domainId}: {response}"
            )
            return False

        values = response.get("value", [])

        # one row per workspace; copy the domain so rows do not share state
        for value in values:
            if len(value) != 0:
                row = dict(domain)
                row["workspace"] = value.get("displayName")
                row["workspaceId"] = value.get("id")
                domain_workspaces.append(row)

    Path = f"domains/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"
    await context.fm.save(
        path=Path, file_name="domains.json", content=domain_workspaces
    )


if __name__ == "__main__":
    asyncio.run(main())
