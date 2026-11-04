import asyncio
from urllib.parse import quote

from env.context import utc_now

MAX_ATTEMPTS = 3
DEFAULT_RETRY_SECONDS = 30
WORKSPACES_URL = "https://api.fabric.microsoft.com/v1/admin/workspaces"


async def _get_with_retry(context, rest_api, headers):
    """Call ``context.invokeAPI`` and retry transient failures a bounded number of times.

    :param context: The application context.
    :param rest_api: Relative or absolute API URL.
    :param headers: Request headers.
    :return: The decoded JSON response.
    :raises RuntimeError: If the request still fails after ``MAX_ATTEMPTS`` attempts.
    """
    result = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = await context.invokeAPI(rest_api=rest_api, headers=headers)
        if isinstance(result, dict) and "ERROR" not in result:
            return result

        status = result.get("status") if isinstance(result, dict) else None
        context.logger.error(f"Roles request failed (attempt {attempt}/{MAX_ATTEMPTS}): {rest_api} -> {status}")
        if attempt < MAX_ATTEMPTS:
            retry_after = result.get("retryAfter") if isinstance(result, dict) else None
            delay = int(retry_after) if retry_after and str(retry_after).isdigit() else DEFAULT_RETRY_SECONDS
            await asyncio.sleep(delay)

    raise RuntimeError(f"Roles request failed after {MAX_ATTEMPTS} attempts: {rest_api}: {result}")


async def main(context=None):
    """
    Roles
    """
    if context is None:
        raise RuntimeError("Context is None")


    headers = context.clients["tenant"].get_headers()
    powerbi_headers = context.clients["pbi"].get_headers()


    items = set()
    workspaces_url = context.get_fabric_url("v1/admin/workspaces")
    next_url = workspaces_url
    while next_url:
        results = await _get_with_retry(context, next_url, headers)

        for item in results.get("workspaces") or []:
            items.add(item["id"])

        continuationToken = results.get("continuationToken")
        next_url = f"{workspaces_url}?continuationToken={quote(continuationToken)}" if continuationToken else None

    ceiling = len(items)
    cnt = 0

    base_url = 'admin/groups?$expand=users&$top=5000'

    all_groups = []
    for i in range(0, ceiling, 5000):
        results = await _get_with_retry(context, f'{base_url}&$skip={i}', powerbi_headers)
        all_groups.extend(results.get('value', []))
    print(f'Total groups retrieved: {len(all_groups)}')


    pivotDate = utc_now()
    content = all_groups
    index = str(cnt).zfill(5)

    Path = f"roles/{pivotDate.strftime('%Y')}/{pivotDate.strftime('%m')}/{pivotDate.strftime('%d')}/"
    await context.fm.save(path=Path, file_name=f"{pivotDate.strftime('%Y%m%d')}_{index}.roles.json",content=content)


if __name__ == "__main__":
    asyncio.run(main())
