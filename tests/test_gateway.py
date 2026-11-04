"""B5: gateway status entries are independent; non-200 handled."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from env.modules import gateway
from tests.helpers import make_context

BASE = "https://api.powerbi.com/v1.0/myorg/gateways"


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body) if not isinstance(self._body, str) else self._body

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


def _router(routes):
    async def get(url, headers):
        r = routes.get(url)
        if r is None:
            raise AssertionError(f"unexpected url {url}")
        return r
    return get


def _saved(ctx):
    return {c.kwargs["file_name"]: json.loads(c.kwargs["content"]) for c in ctx.fm.save.await_args_list}


def _happy_routes(status_overrides=None):
    routes = {
        BASE: _Resp(200, {"value": [{"id": "g1"}]}),
        f"{BASE}/g1/datasources": _Resp(200, {"value": [{"id": "d1", "gatewayId": "g1"},
                                                       {"id": "d2", "gatewayId": "g1"}]}),
        f"{BASE}/g1/datasources/d1/users": _Resp(200, {"value": [{"emailAddress": "a"}]}),
        f"{BASE}/g1/datasources/d2/users": _Resp(200, {"value": []}),
        f"{BASE}/g1/datasources/d1/status": _Resp(200, {}),
        f"{BASE}/g1/datasources/d2/status": _Resp(200, {}),
        f"{BASE}/g1/datasources/d1": _Resp(200, {"id": "d1", "@odata.context": "x"}),
        f"{BASE}/g1/datasources/d2": _Resp(200, {"id": "d2", "@odata.context": "x"}),
    }
    routes.update(status_overrides or {})
    return routes


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, routes):
        ctx = make_context()
        with patch.object(gateway, "_get", _router(routes)):
            result = await gateway.main(ctx)
        return ctx, result

    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await gateway.main(None)

    async def test_status_entries_are_independent_copies(self):
        template_before = json.dumps(gateway.STATUS_TEMPLATE, sort_keys=True)
        ctx, result = await self._run(_happy_routes())
        self.assertTrue(result)
        status = _saved(ctx)["status.json"]
        self.assertEqual([(s["gatewayId"], s["datasourceId"]) for s in status],
                         [("g1", "d1"), ("g1", "d2")])
        for s in status:
            # exactly one detail each: no accumulation across entries
            self.assertEqual(len(s["error"]["pbi.error"]["details"]), 1)
            self.assertEqual(s["error"]["code"], "success")
        # the module-level template is never mutated
        self.assertEqual(json.dumps(gateway.STATUS_TEMPLATE, sort_keys=True), template_before)
        self.assertEqual(gateway.STATUS_TEMPLATE["datasourceId"], "")
        self.assertEqual(gateway.STATUS_TEMPLATE["error"]["pbi.error"]["details"], [])

    async def test_mixed_status_results_keep_their_own_outcome(self):
        routes = _happy_routes({
            f"{BASE}/g1/datasources/d2/status": _Resp(400, {"error": {"code": "DM_GWPipeline"}}),
        })
        ctx, _ = await self._run(routes)
        status = _saved(ctx)["status.json"]
        self.assertEqual(status[0]["error"]["code"], "success")
        self.assertEqual(status[1]["error"]["code"], "DM_GWPipeline")
        self.assertEqual(status[1]["error"]["pbi.error"]["details"][0]["message"], "cannot connect")
        self.assertEqual(status[1]["datasourceId"], "d2")

    async def test_non_json_failure_status_body_is_tolerated(self):
        routes = _happy_routes({f"{BASE}/g1/datasources/d1/status": _Resp(500, "<html>")})
        ctx, _ = await self._run(routes)
        entry = _saved(ctx)["status.json"][0]
        self.assertEqual(entry["datasourceId"], "d1")
        self.assertEqual(entry["error"]["pbi.error"]["details"][0]["detail"], 500)

    async def test_gateways_list_non_200_returns_false_without_keyerror(self):
        ctx, result = await self._run({BASE: _Resp(401, {"error": "x"})})
        self.assertIs(result, False)
        ctx.fm.save.assert_not_awaited()
        ctx.logger.error.assert_called()

    async def test_datasource_failures_return_false_but_save_outputs(self):
        routes = _happy_routes({
            f"{BASE}/g1/datasources/d1/users": _Resp(500, {}),
        })
        ctx, result = await self._run(routes)
        self.assertIs(result, False)
        saved = _saved(ctx)
        self.assertEqual(saved["users.json"], [])
        self.assertEqual(len(saved["datasource_details.json"]), 2)
        self.assertNotIn("@odata.context", saved["datasource_details.json"][0])

    async def test_per_gateway_datasource_failure_is_skipped(self):
        routes = _happy_routes({f"{BASE}/g1/datasources": _Resp(403, {})})
        ctx, result = await self._run(routes)
        self.assertIs(result, False)
        self.assertEqual(_saved(ctx)["status.json"], [])

    async def test_users_are_annotated_with_ids(self):
        ctx, _ = await self._run(_happy_routes())
        users = _saved(ctx)["users.json"]
        self.assertEqual(users, [{"emailAddress": "a", "datasourceId": "d1", "gatewayId": "g1"}])


if __name__ == "__main__":
    unittest.main()
