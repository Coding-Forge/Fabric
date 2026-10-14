"""Graph module: uses context.invokeAPI, honours GraphExtractGroups and reports failures."""
import unittest
from unittest.mock import MagicMock

from env.modules import graph
from tests.helpers import make_context

ROOT = "https://graph.test/v1.0"


def _ctx(routes, groups=False):
    """``routes`` maps a URL prefix to the invokeAPI response."""
    calls = []

    async def invoke(rest_api, headers=None, json=None):
        calls.append((rest_api, headers))
        for prefix, resp in routes.items():
            if rest_api.startswith(prefix):
                return resp
        raise AssertionError(rest_api)

    ctx = make_context(invoke=invoke)
    ctx.GraphExtractGroups = groups
    client = MagicMock()
    client.get_headers.return_value = {"Authorization": "g"}
    client.get_api_root.return_value = ROOT
    ctx.clients["graph"] = client
    return ctx, calls


def _saved(ctx):
    return {c.kwargs["file_name"]: c.kwargs["content"] for c in ctx.fm.save.await_args_list}


class GraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_context(self):
        with self.assertRaises(RuntimeError):
            await graph.main(None)

    async def test_calls_go_through_invoke_api_with_graph_root_and_headers(self):
        ctx, calls = _ctx({f"{ROOT}/users": {"value": [{"id": "u"}]},
                           f"{ROOT}/subscribedSkus": {"value": [{"id": "s"}]}})
        self.assertIs(await graph.main(ctx), True)
        self.assertEqual([c[0].split("?")[0] for c in calls], [f"{ROOT}/users", f"{ROOT}/subscribedSkus"])
        for _, headers in calls:
            self.assertEqual(headers["Authorization"], "g")
            self.assertEqual(headers["Content-Type"], "application/json")
        saved = _saved(ctx)
        self.assertEqual(saved["users.json"], [{"id": "u"}])
        self.assertEqual(saved["subscribedskus.json"], [{"id": "s"}])
        self.assertNotIn("groups.json", saved)
        for c in ctx.fm.save.await_args_list:
            self.assertTrue(c.kwargs["path"].startswith("graph/"))

    async def test_groups_are_fetched_when_enabled(self):
        ctx, calls = _ctx({f"{ROOT}/users": {"value": [1]},
                           f"{ROOT}/subscribedSkus": {"value": [2]},
                           f"{ROOT}/groups": {"value": [3]}}, groups=True)
        self.assertIs(await graph.main(ctx), True)
        self.assertEqual(len(calls), 3)
        self.assertEqual(_saved(ctx)["groups.json"], [3])

    async def test_failed_call_returns_false_but_other_calls_still_saved(self):
        ctx, calls = _ctx({f"{ROOT}/users": {"ERROR": "x"},
                           f"{ROOT}/subscribedSkus": {"value": [2]}})
        self.assertIs(await graph.main(ctx), False)
        self.assertEqual(len(calls), 2)
        self.assertEqual(list(_saved(ctx)), ["subscribedskus.json"])
        ctx.logger.error.assert_called()

    async def test_empty_response_is_a_failure(self):
        ctx, _ = _ctx({f"{ROOT}/users": None, f"{ROOT}/subscribedSkus": {}})
        self.assertIs(await graph.main(ctx), False)
        ctx.fm.save.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
