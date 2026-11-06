import asyncio
import copy
import json
import requests

from env.context import utc_now
from env.utility import http_retry

REQUEST_TIMEOUT_SECONDS = 120

# Template for a successful datasource status; deep-copied per entry
STATUS_TEMPLATE = {
    "datasourceId": "",
    "gatewayId": "",
    "error": {
        "code": "success",
        "pbi.error": {
            "code": "0",
            "parameters": {},
            "details": [],
            "exceptionCulprit": 0
        }
    }
}


async def _get(url, headers, *, context):
    """Run a blocking ``requests.get`` in a worker thread so the event loop is not blocked.

    Throttled (429) and transient (503/504) responses are retried, waiting for
    ``Retry-After`` when present and backing off exponentially otherwise.

    :param url: Absolute URL to request.
    :param headers: Request headers.
    :param context: Runtime owning the shared legacy concurrency/cooldown state.
    :return: The last ``requests.Response``.
    """
    retries = http_retry.max_retries()
    attempt = 0
    auth_retried = False
    force_refresh = False
    while True:
        async with context.legacy_api_slot(url):
            request_headers = await http_retry.resolve_headers(
                headers, force_refresh=force_refresh
            )
            force_refresh = False
            if context._api_cooldowns.remaining(url) > 0:
                continue
            response = await asyncio.to_thread(
                requests.get, url, headers=request_headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
        if response.status_code == 401 and callable(headers) and not auth_retried:
            response.close()
            auth_retried, force_refresh = True, True
            context.logger.warning("Gateway HTTP 401; reacquiring authentication once")
            continue
        server_delay = None
        if response.status_code in http_retry.RETRYABLE_STATUSES:
            server_delay = http_retry.parse_retry_after(response.headers.get("Retry-After"))
            if server_delay is not None:
                context._api_cooldowns.reserve(url, server_delay)
        if response.status_code not in http_retry.RETRYABLE_STATUSES or attempt >= retries:
            return response
        delay = http_retry.retry_delay(attempt, response.headers.get("Retry-After"))
        context.logger.warning(
            "Gateway HTTP %d; retrying in %.0fs (%d/%d)",
            response.status_code, delay, attempt + 1, retries,
        )
        response.close()
        if server_delay is None:
            await asyncio.sleep(delay)
        attempt += 1


async def main(context=None):
    """
    Gateways
    """

    if not context:
        raise RuntimeError("Context is None")

    def headers(**kwargs):
        return {
            **context.clients['pbi'].get_headers(**kwargs),
            'content-type': 'application/json',
            'pragma': 'no-cache',
        }


# GET https://api.powerbi.com/v1.0/myorg/gateways

    api_url = context.get_powerbi_url("gateways")
    response = await _get(api_url, headers, context=context)
    if response.status_code != 200:
        context.logger.error(f"Gateways request failed: HTTP {response.status_code}")
        return False
    results = response.json()

    gateways = list()
    for gateway in results.get('value', []):
        gateways.append(gateway.get("id"))

    today = utc_now()
    path = f'gateways/{today.strftime("%Y")}/{today.strftime("%m")}/{today.strftime("%d")}/'

    await context.fm.save(path=path, file_name='gateways.json', content=json.dumps(results['value']))

    status = list()
    users = list()
    datasources = list()
    datasource_details = list()
    failures = 0

    r = list()
    for id in gateways:
        response = await _get(f'{api_url}/{id}/datasources', headers, context=context)
        if response.status_code != 200:
            failures += 1
            context.logger.error(f"Datasources request failed for gateway {id}: HTTP {response.status_code}")
            continue
        r.append(response.json().get('value', []))
    gateways = list()

    for i in range(0, len(r)):
        if isinstance(r[i], list):
            for j in range(0, len(r[i])):
                gateways.append(r[i][j])
        else:
            gateways.append(r[i])


    for i in range(0,len(gateways)):
        api_users = f'{api_url}/{gateways[i]["gatewayId"]}/datasources/{gateways[i]["id"]}/users'
        response = await _get(api_users, headers, context=context)
        if response.status_code != 200:
            failures += 1
            context.logger.error(f"Users request failed for datasource {gateways[i]['id']}: HTTP {response.status_code}")
            continue
        results = response.json()

        if "value" in results:
            for l in range(0,len(results['value'])):
                results['value'][l]['datasourceId'] = gateways[i]["id"]
                results['value'][l]['gatewayId'] = gateways[i]["gatewayId"]
                users.append(results['value'][l])

    for i in range(0,len(gateways)):
        api_status = f'{api_url}/{gateways[i]["gatewayId"]}/datasources/{gateways[i]["id"]}/status'

        response = await _get(api_status, headers, context=context)
        if response.ok:
            # response.json() is actually empty when it is a success
            # copy the template so every entry is independent
            entry = copy.deepcopy(STATUS_TEMPLATE)
            entry['datasourceId'] = gateways[i]["id"]
            entry['gatewayId'] = gateways[i]["gatewayId"]
            entry["error"]["pbi.error"]["details"].append({"message":"success","detail":response.status_code})
            status.append(entry)
        else:
            if response.status_code in (401, 403, 429, 503, 504):
                # Authentication/throttling/unavailability leaves connectivity unknown.
                failures += 1
            try:
                results = json.loads(response.text)
            except ValueError:
                results = {}
            if not isinstance(results, dict):
                results = {}
            results["datasourceId"] = gateways[i]["id"]
            results["gatewayId"] = gateways[i]["gatewayId"]
            error = results.setdefault("error", {})
            pbi_error = error.setdefault("pbi.error", {})
            pbi_error.setdefault("details", []).append({"message":"cannot connect","detail":response.status_code})
            status.append(results)

    for i in range(0,len(gateways)):
        api_datasource = f'{api_url}/{gateways[i]["gatewayId"]}/datasources/{gateways[i]["id"]}'
        response = await _get(api_datasource, headers, context=context)
        if response.status_code != 200:
            failures += 1
            context.logger.error(f"Datasource detail request failed for {gateways[i]['id']}: HTTP {response.status_code}")
            continue
        results = response.json()
        results.pop('@odata.context', None)
        datasource_details.append(results)

    await context.fm.save(path=path, file_name='status.json', content=json.dumps(status))
    await context.fm.save(path=path, file_name='users.json', content=json.dumps(users))
    await context.fm.save(path=path, file_name='datasources.json', content=json.dumps(gateways))
    await context.fm.save(path=path, file_name='datasource_details.json', content=json.dumps(datasource_details))

    return failures == 0


if __name__ == "__main__":
    asyncio.run(main())